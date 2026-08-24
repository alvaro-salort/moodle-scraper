"""
Módulo de Descarga: Descargas en streaming de 8KB, resolución de Content-Disposition,
anti-duplicados, reanudación y sanitización de rutas.
"""

import mimetypes
import os
import re
from pathlib import Path
from typing import Optional, Tuple
from urllib.parse import unquote, urlparse

import requests

from moodle_scraper.config import ScraperConfig
from moodle_scraper.session import MoodleSession
from moodle_scraper.utils import Logger, sanitize_filename, format_bytes


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
            return unquote(encoded_name).strip(' \t\r\n"')

        # 2. Buscar formato estándar: filename="nombre.pdf" o filename=nombre.pdf
        match_std = re.search(r'filename\s*=\s*"([^"]+)"', cd, re.IGNORECASE)
        if match_std:
            return match_std.group(1).strip()
        
        match_unquoted = re.search(r'filename\s*=\s*([^;]+)', cd, re.IGNORECASE)
        if match_unquoted:
            return match_unquoted.group(1).strip(' \t\r\n"')

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
        url_path = unquote(parsed_url.path)
        url_filename = Path(url_path).name

        # Validar si el nombre de la URL parece un archivo real con extensión
        if url_filename and "." in url_filename and not url_filename.endswith((".php", ".html", ".htm")):
            return sanitize_filename(url_filename)

        # 3. Utilizar nombre alternativo con extensión deducida de Content-Type
        clean_fallback = sanitize_filename(fallback_name or "archivo")
        content_type = response.headers.get("Content-Type", "").split(";")[0].strip()
        
        if "." not in clean_fallback and content_type:
            guessed_ext = mimetypes.guess_extension(content_type)
            if guessed_ext:
                # Corregir algunas extensiones comunes de Moodle
                if guessed_ext == ".htm":
                    guessed_ext = ".html"
                clean_fallback = f"{clean_fallback}{guessed_ext}"

        return clean_fallback

    def download_file(
        self,
        url: str,
        dest_dir: Path,
        fallback_name: Optional[str] = None,
        source_info: str = ""
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

        # Resolver el nombre final del archivo
        filename = self.resolve_filename(response, fallback_name)
        target_path = dest_dir / filename
        temp_path = dest_dir / f"{filename}.part"

        # Obtener tamaño reportado por el servidor
        content_length_header = response.headers.get("Content-Length")
        total_bytes = int(content_length_header) if content_length_header and content_length_header.isdigit() else None
        formatted_total = format_bytes(total_bytes) if total_bytes else "desconocido"

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
                        f.write(chunk)
                        downloaded_bytes += len(chunk)

            # Reemplazar atómicamente el archivo temporal por el definitivo
            if temp_path.exists():
                if target_path.exists():
                    target_path.unlink()
                temp_path.rename(target_path)

            Logger.success(f"Descargado: {filename} ({format_bytes(downloaded_bytes)})")
            return True, target_path, "Descargado correctamente"

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
