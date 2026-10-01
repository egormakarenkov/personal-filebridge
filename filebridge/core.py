"""Validated local filesystem operations; independent of MCP transport."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import shutil
import stat
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable


class FileBridgeError(ValueError):
    """A request was invalid or could not be safely applied."""


class FileBridge:
    MAX_TEXT_BYTES = 4 * 1024 * 1024
    MAX_LIST_ENTRIES = 500
    MAX_DELETE_PREVIEW_ENTRIES = 100_000
    MAX_PENDING_OPERATIONS = 64
    OPERATION_TTL_SECONDS = 600

    def __init__(
        self, state_dir: Path, recovery_dir: Path,
        allowed_roots: list[Path] | None = None,
        approver: Callable[[dict[str, Any]], bool] | None = None,
    ):
        self.state_dir = Path(state_dir).absolute()
        self.recovery_dir = Path(recovery_dir).absolute()
        if self.state_dir == self.recovery_dir:
            raise FileBridgeError("State and recovery directories must differ")
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.recovery_dir.mkdir(parents=True, exist_ok=True)
        requested_roots = tuple(Path(root) for root in (allowed_roots or []))
        if any(not root.is_absolute() for root in requested_roots):
            raise FileBridgeError("Allowed roots must be absolute paths")
        self.allowed_roots = tuple(root.absolute() for root in requested_roots)
        for root in self.allowed_roots:
            if not root.is_absolute() or not root.is_dir():
                raise FileBridgeError(f"Allowed root must be an existing directory: {root}")
            if self._inside(root, self.state_dir) or self._inside(root, self.recovery_dir):
                raise FileBridgeError("State and recovery directories cannot be allowed roots")
        self.approver = approver
        self.operations: dict[str, dict[str, Any]] = {}
        self.audit_path = self.state_dir / "audit.jsonl"
        self.lock = threading.RLock()

    def _cleanup_expired_ops(self) -> None:
        now = time.time()
        for operation_id, operation in list(self.operations.items()):
            if operation["expires_at"] <= now:
                del self.operations[operation_id]

    @staticmethod
    def _inside(path: Path, parent: Path) -> bool:
        try:
            return os.path.commonpath([os.path.normcase(str(path)), os.path.normcase(str(parent))]) == os.path.normcase(str(parent))
        except ValueError:
            return False

    def _path(self, value: str, *, allow_missing: bool = False) -> Path:
        if not isinstance(value, str) or not value or "\x00" in value:
            raise FileBridgeError("A nonempty absolute path is required")
        if value.startswith(("\\\\", "//")):
            raise FileBridgeError("UNC and device paths are not supported")
        path = Path(value)
        if not path.is_absolute() or ".." in path.parts:
            raise FileBridgeError("Only absolute paths without '..' are supported")
        if str(path) == path.anchor:
            raise FileBridgeError("Drive roots cannot be used")
        if os.name == "nt" and ":" in str(path)[len(path.drive):]:
            raise FileBridgeError("Alternate data stream paths are not supported")
        path = path.absolute()
        if not any(self._inside(path, root) for root in self.allowed_roots):
            raise FileBridgeError("Path is outside the configured allowed roots")
        for protected in (self.state_dir, self.recovery_dir):
            if self._inside(path, protected):
                raise FileBridgeError("The service state and recovery trees are protected")
        current = Path(path.anchor)
        for part in path.parts[1:]:
            current = current / part
            try:
                entry = current.lstat()
            except FileNotFoundError:
                if not allow_missing:
                    raise FileBridgeError(f"Path does not exist: {current}") from None
                continue
            if stat.S_ISLNK(entry.st_mode) or bool(getattr(entry, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)):
                raise FileBridgeError(f"Symlinks and reparse points are not supported: {current}")
        if not allow_missing and not path.exists():
            raise FileBridgeError(f"Path does not exist: {path}")
        return path

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _walk_error(error: OSError) -> None:
        raise FileBridgeError(f"Cannot fully inspect directory: {error}")

    @staticmethod
    def _metadata(path: Path) -> dict[str, Any]:
        info = path.stat()
        return {
            "path": str(path),
            "kind": "directory" if path.is_dir() else "file",
            "size_bytes": info.st_size if path.is_file() else None,
            "modified_ns": info.st_mtime_ns,
        }

    def _audit(self, action: str, path: Path | str, result: str, **extra: Any) -> None:
        entry = {"time_utc": time.time(), "action": action, "path": str(path), "result": result, **extra}
        with self.audit_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def inspect_path(self, path: str) -> dict[str, Any]:
        return self._metadata(self._path(path))

    def list_directory(self, path: str, *, recursive: bool = False, limit: int = 200) -> dict[str, Any]:
        target = self._path(path)
        if not target.is_dir():
            raise FileBridgeError("Path is not a directory")
        if not 1 <= limit <= self.MAX_LIST_ENTRIES:
            raise FileBridgeError(f"Limit must be 1..{self.MAX_LIST_ENTRIES}")
        entries: list[dict[str, Any]] = []
        pending = [target]
        truncated = False
        while pending:
            folder = pending.pop()
            for entry in sorted(folder.iterdir(), key=lambda item: item.name.casefold()):
                if len(entries) == limit:
                    truncated = True
                    break
                try:
                    safe = self._path(str(entry))
                    entries.append(self._metadata(safe))
                    if recursive and safe.is_dir():
                        pending.append(safe)
                except (FileBridgeError, PermissionError, OSError) as error:
                    entries.append({"path": str(entry), "error": str(error)})
            if truncated:
                break
        return {"path": str(target), "entries": entries, "truncated": truncated}

    def read_text(self, path: str, *, max_bytes: int = MAX_TEXT_BYTES) -> dict[str, Any]:
        target = self._path(path)
        if not target.is_file():
            raise FileBridgeError("Path is not a file")
        if not 1 <= max_bytes <= self.MAX_TEXT_BYTES:
            raise FileBridgeError(f"Read limit must be 1..{self.MAX_TEXT_BYTES}")
        with target.open("rb") as stream:
            data = stream.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise FileBridgeError("File exceeds read limit")
        try:
            decoded = data.decode("utf-8")
        except UnicodeDecodeError:
            raise FileBridgeError("File is not UTF-8 text") from None
        return {"path": str(target), "text": decoded, "sha256": hashlib.sha256(data).hexdigest(), "size_bytes": len(data)}

    def read_base64(self, path: str, *, max_bytes: int = MAX_TEXT_BYTES) -> dict[str, Any]:
        target = self._path(path)
        if not target.is_file():
            raise FileBridgeError("Path is not a file")
        if not 1 <= max_bytes <= self.MAX_TEXT_BYTES:
            raise FileBridgeError(f"Read limit must be 1..{self.MAX_TEXT_BYTES}")
        with target.open("rb") as stream:
            data = stream.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise FileBridgeError("File exceeds read limit")
        return {"path": str(target), "base64": base64.b64encode(data).decode("ascii"), "sha256": hashlib.sha256(data).hexdigest(), "size_bytes": len(data)}

    def _save_op(self, operation: dict[str, Any]) -> None:
        if len(self.operations) >= self.MAX_PENDING_OPERATIONS:
            raise FileBridgeError("Too many pending operations; commit or wait for expiry")
        self.operations[operation["operation_id"]] = operation

    def _load_op(self, operation_id: str, action: str) -> dict[str, Any]:
        try:
            operation_uuid = str(uuid.UUID(operation_id))
        except (ValueError, AttributeError):
            raise FileBridgeError("Invalid operation ID") from None
        operation = self.operations.get(operation_uuid)
        if operation is None:
            raise FileBridgeError("Operation not found or already committed") from None
        if operation.get("action") != action:
            raise FileBridgeError("Operation type mismatch")
        if time.time() > operation["expires_at"]:
            self.operations.pop(operation_uuid, None)
            raise FileBridgeError("Operation expired; prepare it again")
        return operation

    def _approve(self, operation: dict[str, Any]) -> None:
        if self.approver is None:
            raise FileBridgeError("Local owner approval is unavailable")
        preview = {
            key: operation[key]
            for key in ("operation_id", "action", "path", "permanent", "entries", "estimated_bytes", "size_bytes", "recovery_id")
            if key in operation
        }
        preview["expires_in_seconds"] = max(0, int(operation["expires_at"] - time.time()))
        try:
            accepted = self.approver(preview)
        except Exception as error:
            raise FileBridgeError(f"Local owner approval failed: {type(error).__name__}") from None
        if not accepted:
            raise FileBridgeError("Local owner denied the operation")
        if time.time() > operation["expires_at"]:
            self.operations.pop(operation["operation_id"], None)
            raise FileBridgeError("Operation expired during approval; prepare it again")

    def _prepare_write(self, path: str, data: bytes, expected_sha256: str | None) -> dict[str, Any]:
        target = self._path(path, allow_missing=True)
        if not target.parent.is_dir() or target.is_dir():
            raise FileBridgeError("Target must be a file in an existing directory")
        if len(data) > self.MAX_TEXT_BYTES:
            raise FileBridgeError("Content exceeds write limit")
        existed = target.exists()
        if existed:
            current_hash = self._sha256(target)
            if expected_sha256 != current_hash:
                raise FileBridgeError("Expected SHA-256 does not match the current file")
        elif expected_sha256 is not None:
            raise FileBridgeError("Expected SHA-256 must be omitted for a new file")
        operation_id = str(uuid.uuid4())
        operation = {
            "operation_id": operation_id, "action": "write", "path": str(target),
            "content": data, "size_bytes": len(data),
            "expected_sha256": expected_sha256, "existed": existed,
            "expires_at": time.time() + self.OPERATION_TTL_SECONDS,
        }
        with self.lock:
            self._cleanup_expired_ops()
            self._save_op(operation)
        return {"operation_id": operation_id, "path": str(target), "size_bytes": len(data), "new_sha256": hashlib.sha256(data).hexdigest(), "expires_in_seconds": self.OPERATION_TTL_SECONDS}

    def prepare_write_text(self, path: str, text: str, expected_sha256: str | None) -> dict[str, Any]:
        return self._prepare_write(path, text.encode("utf-8"), expected_sha256)

    def prepare_write_base64(self, path: str, content_base64: str, expected_sha256: str | None) -> dict[str, Any]:
        try:
            data = base64.b64decode(content_base64, validate=True)
        except (binascii.Error, ValueError):
            raise FileBridgeError("Content is not valid base64") from None
        return self._prepare_write(path, data, expected_sha256)

    def _recovery_manifest(self, recovery_id: str, original: Path, kind: str, operation: str) -> dict[str, Any]:
        return {"recovery_id": recovery_id, "original_path": str(original), "kind": kind, "operation": operation, "created_at": time.time()}

    def _save_recovery_manifest(self, recovery_id: str, manifest: dict[str, Any]) -> None:
        (self.recovery_dir / (recovery_id + ".json")).write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")

    def _validated_recovery_manifest(self, recovery_id: str) -> dict[str, Any]:
        manifest_path = self.recovery_dir / (recovery_id + ".json")
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if not isinstance(manifest, dict) or str(uuid.UUID(manifest["recovery_id"])) != recovery_id:
                raise ValueError("Recovery ID mismatch")
            if manifest["operation"] not in ("copy", "move") or manifest["kind"] not in ("file", "directory"):
                raise ValueError("Invalid recovery operation or kind")
            if manifest["operation"] == "copy" and manifest["kind"] != "file":
                raise ValueError("Invalid recovery copy")
            self._path(manifest["original_path"], allow_missing=True)
            source = self.recovery_dir / recovery_id
            info = source.lstat()
            if stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)):
                raise ValueError("Recovery item is a link")
            if (manifest["kind"] == "file") != source.is_file():
                raise ValueError("Recovery item kind mismatch")
            return manifest
        except (KeyError, TypeError, ValueError, OSError, FileBridgeError) as error:
            raise FileBridgeError(f"Recovery item is invalid or missing: {error}") from None

    def commit_write_text(self, operation_id: str) -> dict[str, Any]:
        with self.lock:
            operation = self._load_op(operation_id, "write")
            target = self._path(operation["path"], allow_missing=True)
            if operation["existed"]:
                if not target.is_file() or self._sha256(target) != operation["expected_sha256"]:
                    raise FileBridgeError("File changed since preparation")
            elif target.exists():
                raise FileBridgeError("Target appeared since preparation")
            self._approve(operation)
            target = self._path(operation["path"], allow_missing=True)
            if operation["existed"]:
                if not target.is_file() or self._sha256(target) != operation["expected_sha256"]:
                    raise FileBridgeError("File changed during approval")
            elif target.exists():
                raise FileBridgeError("Target appeared during approval")
            recovery_id = None
            if operation["existed"]:
                recovery_id = str(uuid.uuid4())
                shutil.copy2(target, self.recovery_dir / recovery_id)
                self._save_recovery_manifest(recovery_id, self._recovery_manifest(recovery_id, target, "file", "copy"))
            temporary = target.parent / (".filebridge-" + uuid.uuid4().hex + ".tmp")
            try:
                with temporary.open("xb") as stream:
                    stream.write(operation["content"])
                    stream.flush()
                    os.fsync(stream.fileno())
                if operation["existed"]:
                    shutil.copystat(target, temporary)
                os.replace(temporary, target)
            finally:
                temporary.unlink(missing_ok=True)
            self.operations.pop(operation["operation_id"], None)
            self._audit("write", target, "ok", recovery_id=recovery_id)
            return {"path": str(target), "sha256": self._sha256(target), "recovery_id": recovery_id}

    def prepare_delete(self, path: str, *, permanent: bool = False) -> dict[str, Any]:
        target = self._path(path)
        for protected in (self.state_dir, self.recovery_dir):
            if self._inside(protected, target):
                raise FileBridgeError("Cannot delete a parent of the service state or recovery tree")
        info = target.stat()
        preview_entries = 1
        preview_bytes = info.st_size if target.is_file() else 0
        tree_hash = hashlib.sha256()
        tree_hash.update(f".|{info.st_size}|{info.st_mtime_ns}".encode("utf-8"))
        if target.is_file():
            tree_hash.update(self._sha256(target).encode("ascii"))
        if target.is_dir():
            for folder, dirs, files in os.walk(target, followlinks=False, onerror=self._walk_error):
                dirs.sort()
                files.sort()
                for name in dirs + files:
                    child = Path(folder) / name
                    self._path(str(child))
                    preview_entries += 1
                    if preview_entries > self.MAX_DELETE_PREVIEW_ENTRIES:
                        raise FileBridgeError("Directory exceeds deletion preview limit")
                    child_info = child.stat()
                    tree_hash.update(f"{child.relative_to(target)}|{child_info.st_size}|{child_info.st_mtime_ns}".encode("utf-8"))
                    if child.is_file():
                        preview_bytes += child_info.st_size
                        tree_hash.update(self._sha256(child).encode("ascii"))
        operation_id = str(uuid.uuid4())
        operation = {
            "operation_id": operation_id, "action": "delete", "path": str(target),
            "permanent": permanent, "modified_ns": info.st_mtime_ns,
            "size_bytes": info.st_size, "tree_sha256": tree_hash.hexdigest(),
            "entries": preview_entries, "estimated_bytes": preview_bytes,
            "expires_at": time.time() + self.OPERATION_TTL_SECONDS,
        }
        with self.lock:
            self._cleanup_expired_ops()
            self._save_op(operation)
        return {"operation_id": operation_id, "path": str(target), "kind": "directory" if target.is_dir() else "file", "entries": preview_entries, "estimated_bytes": preview_bytes, "permanent": permanent, "expires_in_seconds": self.OPERATION_TTL_SECONDS}

    def commit_delete(self, operation_id: str) -> dict[str, Any]:
        with self.lock:
            operation = self._load_op(operation_id, "delete")
            target = self._path(operation["path"])
            current = self._delete_summary(target)
            if current["tree_sha256"] != operation["tree_sha256"]:
                raise FileBridgeError("Target changed since preparation")
            self._approve(operation)
            target = self._path(operation["path"])
            if self._delete_summary(target)["tree_sha256"] != operation["tree_sha256"]:
                raise FileBridgeError("Target changed during approval")
            recovery_id = None
            if operation["permanent"]:
                if target.is_dir():
                    shutil.rmtree(target)
                else:
                    target.unlink()
            else:
                recovery_id = str(uuid.uuid4())
                kind = "directory" if target.is_dir() else "file"
                destination = self.recovery_dir / recovery_id
                shutil.move(str(target), str(destination))
                self._save_recovery_manifest(recovery_id, self._recovery_manifest(recovery_id, target, kind, "move"))
            self.operations.pop(operation["operation_id"], None)
            self._audit("delete", target, "ok", permanent=operation["permanent"], recovery_id=recovery_id)
            return {"path": str(target), "permanent": operation["permanent"], "recovery_id": recovery_id}

    def _delete_summary(self, target: Path) -> dict[str, Any]:
        info = target.stat()
        digest = hashlib.sha256()
        digest.update(f".|{info.st_size}|{info.st_mtime_ns}".encode("utf-8"))
        if target.is_file():
            digest.update(self._sha256(target).encode("ascii"))
        count = 1
        if target.is_dir():
            for folder, dirs, files in os.walk(target, followlinks=False, onerror=self._walk_error):
                dirs.sort()
                files.sort()
                for name in dirs + files:
                    child = Path(folder) / name
                    self._path(str(child))
                    count += 1
                    if count > self.MAX_DELETE_PREVIEW_ENTRIES:
                        raise FileBridgeError("Directory exceeds deletion preview limit")
                    child_info = child.stat()
                    digest.update(f"{child.relative_to(target)}|{child_info.st_size}|{child_info.st_mtime_ns}".encode("utf-8"))
                    if child.is_file():
                        digest.update(self._sha256(child).encode("ascii"))
        return {"tree_sha256": digest.hexdigest()}

    def list_recovery(self, *, limit: int = 100) -> dict[str, Any]:
        if not 1 <= limit <= 500:
            raise FileBridgeError("Limit must be 1..500")
        items = []
        for manifest_path in sorted(self.recovery_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            if len(items) >= limit:
                break
            try:
                recovery_id = str(uuid.UUID(manifest_path.stem))
                items.append(self._validated_recovery_manifest(recovery_id))
            except (KeyError, ValueError, OSError, FileBridgeError):
                continue
        return {"items": items}

    def restore_recovery(self, recovery_id: str) -> dict[str, Any]:
        try:
            normalized_id = str(uuid.UUID(recovery_id))
        except (ValueError, AttributeError):
            raise FileBridgeError("Invalid recovery ID") from None
        with self.lock:
            manifest_path = self.recovery_dir / (normalized_id + ".json")
            manifest = self._validated_recovery_manifest(normalized_id)
            target = self._path(manifest["original_path"], allow_missing=True)
            if target.exists() or not target.parent.is_dir():
                raise FileBridgeError("Original path is occupied or its parent is missing")
            source = self.recovery_dir / normalized_id
            if not source.exists():
                raise FileBridgeError("Recovery content is missing")
            self._approve({
                "operation_id": normalized_id, "action": "restore", "path": str(target),
                "recovery_id": normalized_id, "expires_at": time.time() + 120,
            })
            target = self._path(manifest["original_path"], allow_missing=True)
            if target.exists() or not target.parent.is_dir() or not source.exists():
                raise FileBridgeError("Recovery target or content changed during approval")
            if manifest["operation"] == "copy":
                shutil.copy2(source, target)
                source.unlink()
            else:
                shutil.move(str(source), str(target))
            manifest_path.unlink()
            self._audit("restore", target, "ok", recovery_id=normalized_id)
            return {"path": str(target), "recovery_id": normalized_id}
