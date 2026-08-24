"""
Utilidades para el Moodle Scraper: Sanitización de archivos, Logger coloreado y formateadores.
"""

import os
import re
import sys
import unicodedata
from pathlib import Path
from urllib.parse import urljoin, urlparse

# Intentar habilitar colores en consola (Colorama si está disponible)
try:
    import colorama
    colorama.init(autoreset=True)
    COLORAMA_AVAILABLE = True
except ImportError:
    COLORAMA_AVAILABLE = False
    # En Windows 10/11, activar soporte VT100 nativo en PowerShell / CMD si es posible
    if sys.platform == "win32":
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
        except Exception:
            pass


class Colors:
    """Códigos ANSI de escape para estilos y colores en consola."""
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    
    # Texto
    BLACK = "\033[30m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"
    
    # Fondos
    BG_BLUE = "\033[44m"
    BG_MAGENTA = "\033[45m"
    BG_CYAN = "\033[46m"
    BG_GREEN = "\033[42m"
    BG_RED = "\033[41m"


class Logger:
    """Sistema de logging enriquecido con colores e iconografía para consola."""

    @staticmethod
    def header(title: str) -> None:
        line = "=" * 70
        print(f"\n{Colors.BOLD}{Colors.CYAN}{line}{Colors.RESET}")
        print(f"{Colors.BOLD}{Colors.CYAN}  {title.center(66)}  {Colors.RESET}")
        print(f"{Colors.BOLD}{Colors.CYAN}{line}{Colors.RESET}\n")

    @staticmethod
    def course_header(course_name: str, index: int = 0, total: int = 0) -> None:
        counter = f" [{index}/{total}]" if total > 0 else ""
        print(f"\n{Colors.BOLD}{Colors.MAGENTA}┌{'─'*68}┐{Colors.RESET}")
        print(f"{Colors.BOLD}{Colors.MAGENTA}│ 🎓 CURSO{counter}: {Colors.WHITE}{course_name[:56]:<56}{Colors.MAGENTA}│{Colors.RESET}")
        print(f"{Colors.BOLD}{Colors.MAGENTA}└{'─'*68}┘{Colors.RESET}")

    @staticmethod
    def section(name: str) -> None:
        print(f"\n{Colors.BOLD}{Colors.BLUE}  📁 [SECCIÓN] {name}{Colors.RESET}")
        print(f"{Colors.DIM}{Colors.BLUE}  {'─' * 60}{Colors.RESET}")

    @staticmethod
    def info(msg: str) -> None:
        print(f"{Colors.CYAN}  ℹ {msg}{Colors.RESET}")

    @staticmethod
    def success(msg: str) -> None:
        print(f"{Colors.BOLD}{Colors.GREEN}  ✔ {msg}{Colors.RESET}")

    @staticmethod
    def skip(msg: str) -> None:
        print(f"{Colors.YELLOW}  ↷ [OMITIDO] {msg}{Colors.RESET}")

    @staticmethod
    def warn(msg: str) -> None:
        print(f"{Colors.BOLD}{Colors.YELLOW}  ⚠ [AVISO] {msg}{Colors.RESET}")

    @staticmethod
    def error(msg: str) -> None:
        print(f"{Colors.BOLD}{Colors.RED}  ✖ [ERROR] {msg}{Colors.RESET}")

    @staticmethod
    def text_saved(file_name: str) -> None:
        print(f"{Colors.GREEN}  📝 [TEXTO GUARDADO] {file_name}{Colors.RESET}")

    @staticmethod
    def download_progress(filename: str, current_kb: float, total_kb: float | None = None) -> None:
        if total_kb and total_kb > 0:
            pct = (current_kb / total_kb) * 100
            print(f"\r{Colors.CYAN}  ⬇ Descargando {filename}... {current_kb:.1f}KB / {total_kb:.1f}KB ({pct:.1f}%){Colors.RESET}", end="", flush=True)
        else:
            print(f"\r{Colors.CYAN}  ⬇ Descargando {filename}... {current_kb:.1f}KB{Colors.RESET}", end="", flush=True)


# Nombres reservados en el sistema de archivos de Windows
WINDOWS_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
    "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9"
}


def sanitize_filename(name: str, max_length: int = 150) -> str:
    """
    Sanitiza un nombre de archivo o carpeta para ser 100% compatible con Windows,
    macOS y Linux, reemplazando caracteres prohibidos y evitando nombres reservados.
    """
    if not name:
        return "sin_nombre"
    
    # Decodificar entidades HTML básicas si vinieron en el texto
    name = name.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"').replace("&#039;", "'")
    
    # Reemplazar caracteres prohibidos en sistemas de archivos (Windows: < > : " / \ | ? *)
    sanitized = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name)
    
    # Eliminar espacios múltiples y espacios/puntos al inicio o final
    sanitized = re.sub(r'\s+', ' ', sanitized).strip(" .")
    
    # Verificar nombres reservados de Windows (ej: CON.txt, NUL, AUX)
    base_stem = Path(sanitized).stem.upper()
    if base_stem in WINDOWS_RESERVED_NAMES:
        sanitized = f"_{sanitized}"
    
    if not sanitized:
        sanitized = "archivo"
    
    # Limitar longitud para evitar desbordamiento del límite MAX_PATH en Windows (260 caracteres)
    if len(sanitized) > max_length:
        ext = Path(sanitized).suffix
        stem = Path(sanitized).stem
        allowed_stem = max_length - len(ext) - 1
        sanitized = f"{stem[:allowed_stem]}{ext}"
        
    return sanitized


def format_bytes(size_bytes: int | float | None) -> str:
    """Convierte un tamaño en bytes a formato legible (B, KB, MB, GB)."""
    if size_bytes is None:
        return "0 B"
    size = float(size_bytes)
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024.0 or unit == 'TB':
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} B"


def make_absolute_url(base_url: str, link: str) -> str:
    """Convierte una URL relativa o con prefijo en una URL absoluta bien formada."""
    if not link:
        return ""
    return urljoin(base_url, link.strip())
