"""
Módulo de Descarga: Descargas en streaming de 8KB, resolución de Content-Disposition,
anti-duplicados, reanudación y sanitización de rutas.
"""

import mimetypes
import os
import re
import unicodedata
from pathlib import Path
from typing import Optional, Tuple
from urllib.parse import unquote, urlparse

import requests

from moodle_scraper.config import ScraperConfig
from moodle_scraper.session import MoodleSession
from moodle_scraper.utils import Logger, sanitize_filename, format_bytes


_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg", ".ico", ".avif"}


def _repair_text(value: str) -> str:
    """
    Repara el mojibake típico de headers UTF-8 leídos como Latin-1/CP1252
    y normaliza la forma Unicode a NFC.
    """
    if not value:
        return value

    repaired = value
    for encoding in ("latin-1", "cp1252"):
        try:
            candidate = value.encode(encoding).decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            continue
        if candidate != value:
            repaired = candidate
            break

    return unicodedata.normalize("NFC", repaired)


class _DownloadSizeExceeded(Exception):
    """Se lanza cuando una descarga supera el tamaño máximo permitido."""


class Downloader:
    """Administra la descarga de archivos y recursos multimedia de Moodle."""

    def __init__(self, session: MoodleSession, config: ScraperConfig):
        self.session = session
        self.config = config

    def extract_filename_from_headers(self, response: requests.Response) -> Optional[str]:
        """
        Extrae el nombre de archivo desde la cabecera Content-Disposition
        soportando RFC 5987 (filename*=UTF-8''...) y RFC 2616 (filename="...").
        """
        cd = response.headers.get("Content-Disposition", "")
        if not cd:
            return None

        # 1. Buscar formato extendido RFC 5987: filename*=UTF-8''nombre.pdf
        match_rfc5987 = re.search(r"filename\*\s*=\s*(?:UTF-8|iso-8859-1)?\'\'([^;]+)", cd, re.IGNORECASE)
        if match_rfc5987:
            encoded_name = match_rfc5987.group(1)
            return _repair_text(unquote(encoded_name).strip(' \t\r\n"'))

        # 2. Buscar formato estándar: filename="nombre.pdf" o filename=nombre.pdf
        match_std = re.search(r'filename\s*=\s*"([^"]+)"', cd, re.IGNORECASE)
        if match_std:
            return _repair_text(match_std.group(1).strip())
        
        match_unquoted = re.search(r'filename\s*=\s*([^;]+)', cd, re.IGNORECASE)
        if match_unquoted:
            return _repair_text(match_unquoted.group(1).strip(' \t\r\n"'))

        return None

    def resolve_filename(
        self,
        response: requests.Response,
        fallback_name: Optional[str] = None
    ) -> str:
        """
        Resuelve el nombre real del archivo analizando headers, URLs y Content-Type.
        """
        # 1. Intentar desde cabecera Content-Disposition
        header_name = self.extract_filename_from_headers(response)
        if header_name:
            return sanitize_filename(header_name)

        # 2. Intentar desde la URL final después de redirecciones
        parsed_url = urlparse(response.url)
        url_path = _repair_text(unquote(parsed_url.path))
        url_filename = Path(url_path).name

        # Validar si el nombre de la URL parece un archivo real con extensión
        if url_filename and "." in url_filename and not url_filename.endswith((".php", ".html", ".htm")):
            return sanitize_filename(url_filename)

        # 3. Utilizar nombre alternativo con extensión deducida de Content-Type
        clean_fallback = sanitize_filename(_repair_text(fallback_name or "archivo"))
        content_type = response.headers.get("Content-Type", "").split(";")[0].strip()
        
        if "." not in clean_fallback and content_type:
            guessed_ext = mimetypes.guess_extension(content_type)
            if guessed_ext:
                # Corregir algunas extensiones comunes de Moodle
                if guessed_ext == ".htm":
                    guessed_ext = ".html"
                clean_fallback = f"{clean_fallback}{guessed_ext}"

        return clean_fallback

    @staticmethod
    def _is_content_type_allowed(
        content_type: str,
        url: str,
        allowed_prefix: Optional[str],
    ) -> bool:
        """Valida el Content-Type, tolerando octet-stream cuando la URL parece una imagen."""
        if not allowed_prefix:
            return True
        if content_type.startswith(allowed_prefix):
            return True
        if allowed_prefix == "image/" and content_type in ("", "application/octet-stream"):
            return Path(urlparse(url).path).suffix.lower() in _IMAGE_EXTENSIONS
        return False

    def download_file(
        self,
        url: str,
        dest_dir: Path,
        fallback_name: Optional[str] = None,
        source_info: str = "",
        filename_suffix: Optional[str] = None,
        allowed_content_prefix: Optional[str] = None,
        max_bytes: Optional[int] = None,
    ) -> Tuple[bool, Optional[Path], str]:
        """
        Descarga un archivo con streaming en bloques de 8KB.
        Retorna: (éxito, ruta_archivo, mensaje)
        """
        dest_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            # Petición GET con stream=True
            response = self.session.get(url, stream=True, allow_redirects=True)
            response.raise_for_status()
        except requests.RequestException as e:
            Logger.error(f"Fallo al solicitar descarga de {url}: {e}")
            return False, None, f"Error de red: {e}"

        # Validar el tipo de contenido antes de escribir nada en disco
        content_type = response.headers.get("Content-Type", "").split(";")[0].strip().lower()
        if not self._is_content_type_allowed(content_type, url, allowed_content_prefix):
            response.close()
            Logger.warn(f"Descarga omitida por tipo de contenido no permitido ({content_type or 'desconocido'}): {url}")
            return False, None, f"Tipo de contenido no permitido: {content_type or 'desconocido'}"

        # Resolver el nombre final del archivo
        filename = self.resolve_filename(response, fallback_name)
        if filename_suffix:
            path = Path(filename)
            filename = f"{path.stem}-{sanitize_filename(filename_suffix)}{path.suffix}"
        target_path = dest_dir / filename
        temp_path = dest_dir / f"{filename}.part"

        # Obtener tamaño reportado por el servidor
        content_length_header = response.headers.get("Content-Length")
        total_bytes = int(content_length_header) if content_length_header and content_length_header.isdigit() else None
        formatted_total = format_bytes(total_bytes) if total_bytes else "desconocido"

        if max_bytes is not None and total_bytes is not None and total_bytes > max_bytes:
            response.close()
            Logger.warn(
                f"Descarga omitida por tamaño excesivo "
                f"({format_bytes(total_bytes)} > {format_bytes(max_bytes)}): {url}"
            )
            return False, None, f"El archivo excede el tamaño máximo permitido ({format_bytes(max_bytes)})"

        # Mecanismo Anti-Duplicados / Resumen
        if target_path.exists() and not self.config.overwrite_existing:
            local_size = target_path.stat().st_size
            # Si el tamaño coincide o el archivo local ya existe con tamaño > 0
            if total_bytes and local_size == total_bytes:
                Logger.skip(f"{filename} ({format_bytes(local_size)}) ya existe completamente.")
                response.close()
                return True, target_path, "Omitido por existencia previa (tamaño idéntico)"
            elif not total_bytes and local_size > 0:
                Logger.skip(f"{filename} ({format_bytes(local_size)}) ya existe.")
                response.close()
                return True, target_path, "Omitido por existencia previa"

        # Descarga en bloques de 8KB
        chunk_size = self.config.chunk_size
        downloaded_bytes = 0

        info_tag = f" [{source_info}]" if source_info else ""
        Logger.info(f"Descargando: {filename}{info_tag} (Tamaño: {formatted_total})...")

        try:
            with open(temp_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=chunk_size):
                    if chunk:
                        downloaded_bytes += len(chunk)
                        if max_bytes is not None and downloaded_bytes > max_bytes:
                            raise _DownloadSizeExceeded(
                                f"El archivo excede el tamaño máximo permitido ({format_bytes(max_bytes)})"
                            )
                        f.write(chunk)

            # Reemplazar atómicamente el archivo temporal por el definitivo
            if temp_path.exists():
                if target_path.exists():
                    target_path.unlink()
                temp_path.rename(target_path)

            Logger.success(f"Descargado: {filename} ({format_bytes(downloaded_bytes)})")
            return True, target_path, "Descargado correctamente"

        except _DownloadSizeExceeded as e:
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except Exception:
                    pass
            Logger.error(f"Descarga cancelada: {e}: {url}")
            return False, None, str(e)

        except Exception as e:
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except Exception:
                    pass
            Logger.error(f"Error al escribir {filename}: {e}")
            return False, None, f"Error de escritura: {e}"
        finally:
            response.close()
