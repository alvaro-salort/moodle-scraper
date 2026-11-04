"""
Manifest de descargas: registra URL, ruta local, tamaño y SHA-256.

Permite reanudar sin re-descargar archivos que no cambiaron y verificar
que los archivos locales siguen coincidiendo con lo descargado.
"""

import datetime
import hashlib
import json
import os
import threading
from pathlib import Path
from typing import Dict, List, Optional, Union


MANIFEST_NAME = "manifest.json"


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    """Calcula el SHA-256 de un archivo."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


class RunManifest:
    """Manifest JSON de una corrida, persistido dentro de la carpeta del curso."""

    def __init__(self, root: Path, course_id: str = "", course_name: str = ""):
        self.root = Path(root).resolve()
        self.path = self.root / MANIFEST_NAME
        self.course_id = course_id
        self.course_name = course_name
        self.entries: Dict[str, dict] = {}
        self._lock = threading.Lock()
        self._dirty = False
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return

        self.course_id = data.get("course", {}).get("id", self.course_id)
        self.course_name = data.get("course", {}).get("name", self.course_name)
        entries = data.get("entries", {})
        if isinstance(entries, dict):
            self.entries = entries

    @staticmethod
    def load(root: Path) -> "RunManifest":
        return RunManifest(root)

    def _relative_path(self, local_path: Path) -> str:
        try:
            return Path(local_path).resolve().relative_to(self.root).as_posix()
        except ValueError:
            return str(Path(local_path).resolve())

    def _dest_key(self, dest_dir: Optional[Path]) -> str:
        if dest_dir is None:
            return ""
        try:
            relative = Path(dest_dir).resolve().relative_to(self.root).as_posix()
        except ValueError:
            return str(Path(dest_dir).resolve())
        return "" if relative == "." else relative

    def _key(self, url: str, dest_dir: Optional[Path] = None) -> str:
        prefix = self._dest_key(dest_dir)
        return f"{prefix}|{url}" if prefix else url

    def get(self, url: str, dest_dir: Optional[Path] = None) -> Optional[dict]:
        with self._lock:
            return self.entries.get(self._key(url, dest_dir))

    def record(
        self,
        url: str,
        local_path: Optional[Path] = None,
        size: int = 0,
        sha256: str = "",
        status: str = "ok",
        remote_size: Optional[int] = None,
        remote_mtime: Optional[int] = None,
        error: str = "",
        dest_dir: Optional[Path] = None,
    ) -> None:
        if local_path is not None:
            dest_dir = Path(local_path).parent
        entry = {
            "url": url,
            "local_path": self._relative_path(local_path) if local_path else "",
            "size": int(size),
            "sha256": sha256,
            "status": status,
            "remote_size": remote_size,
            "remote_mtime": remote_mtime,
            "updated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        }
        if error:
            entry["error"] = error
        with self._lock:
            self.entries[self._key(url, dest_dir)] = entry
            self._dirty = True

    def is_current(
        self,
        url: str,
        dest_dir: Optional[Path] = None,
        expected_size: Optional[int] = None,
        expected_mtime: Optional[int] = None,
    ) -> Optional[Path]:
        """Devuelve la ruta local si el archivo no cambió respecto del manifest."""
        entry = self.get(url, dest_dir)
        if not entry or entry.get("status") != "ok":
            return None

        local_name = entry.get("local_path", "")
        if not local_name:
            return None

        local_path = Path(local_name)
        if not local_path.is_absolute():
            local_path = self.root / local_path
        if not local_path.exists() or local_path.stat().st_size != entry.get("size", -1):
            return None

        if expected_size is not None and entry.get("remote_size") is not None:
            if expected_size != entry["remote_size"]:
                return None
        if expected_mtime is not None and entry.get("remote_mtime") is not None:
            if expected_mtime != entry["remote_mtime"]:
                return None

        return local_path

    def save(self) -> None:
        with self._lock:
            if not self._dirty and self.path.exists():
                return
            data = {
                "version": 1,
                "course": {"id": self.course_id, "name": self.course_name},
                "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
                "entries": dict(self.entries),
            }
            payload = json.dumps(data, ensure_ascii=False, indent=2)

        self.root.mkdir(parents=True, exist_ok=True)
        temp_path = self.path.with_suffix(".json.tmp")
        temp_path.write_text(payload + "\n", encoding="utf-8")
        os.replace(temp_path, self.path)

        with self._lock:
            self._dirty = False

    def verify(self) -> List[str]:
        """Comprueba existencia, tamaño y SHA-256 de cada entrada correcta."""
        issues: List[str] = []
        for url, entry in sorted(self.entries.items()):
            if entry.get("status") != "ok":
                continue

            local_name = entry.get("local_path", "")
            if not local_name:
                issues.append(f"{url}: entrada sin ruta local")
                continue

            local_path = Path(local_name)
            if not local_path.is_absolute():
                local_path = self.root / local_path

            if not local_path.exists():
                issues.append(f"{local_path}: no existe")
                continue

            if local_path.stat().st_size != entry.get("size", -1):
                issues.append(
                    f"{local_path}: tamaño {local_path.stat().st_size} != {entry.get('size')}"
                )
                continue

            expected_hash = entry.get("sha256", "")
            if expected_hash and sha256_file(local_path) != expected_hash:
                issues.append(f"{local_path}: SHA-256 no coincide")

        return issues


def verify_directory(root: Union[str, Path]) -> List[str]:
    """Verifica todos los manifest.json encontrados bajo un directorio."""
    root = Path(root)
    issues: List[str] = []
    for manifest_path in sorted(root.rglob(MANIFEST_NAME)):
        manifest = RunManifest(manifest_path.parent)
        for issue in manifest.verify():
            issues.append(f"{manifest_path}: {issue}")
    return issues
