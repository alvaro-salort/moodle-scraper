"""
Módulo de Configuración para el Moodle Scraper.
Soporta carga desde archivos .env, scraper.conf (INI) y variables de entorno del sistema.
"""

import os
import sys
import configparser
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# Carga opcional de python-dotenv si está disponible
try:
    from dotenv import load_dotenv
    DOTENV_AVAILABLE = True
except ImportError:
    DOTENV_AVAILABLE = False


def _parse_bool(val: Optional[str], default: bool = False) -> bool:
    if val is None:
        return default
    return str(val).strip().lower() in ("true", "1", "yes", "si", "s", "t")


@dataclass
class ScraperConfig:
    """Clase de configuración central del scraper."""
    user: str = ""
    password: str = ""
    base_url: str = "https://aulas.itu.uncu.edu.ar/itu/"
    download_dir: Path = field(default_factory=lambda: Path("./downloads"))
    timeout: int = 30
    max_retries: int = 3
    chunk_size_kb: int = 8
    overwrite_existing: bool = False
    save_section_summaries: bool = True
    save_consolidated_markdown: bool = True

    def validate(self) -> list[str]:
        """Valida que los parámetros indispensables estén configurados."""
        errors = []
        if not self.base_url or not self.base_url.startswith(("http://", "https://")):
            errors.append("La URL base de Moodle no es válida o está vacía.")
        if not self.user:
            errors.append("El usuario (MOODLE_USER) no está configurado.")
        if not self.password:
            errors.append("La contraseña (MOODLE_PASSWORD) no está configurada.")
        return errors

    @property
    def chunk_size(self) -> int:
        """Tamaño de chunk en bytes para streaming."""
        return self.chunk_size_kb * 1024


def load_config(
    env_path: Optional[str | Path] = None,
    conf_path: Optional[str | Path] = None
) -> ScraperConfig:
    """
    Carga la configuración con la siguiente prioridad:
    1. Variables de entorno activas en el sistema
    2. Archivo .env
    3. Archivo scraper.conf / config.ini
    4. Valores por defecto
    """
    # 1. Intentar cargar .env si existe
    if env_path is None:
        default_env = Path(".env")
        if default_env.exists() and DOTENV_AVAILABLE:
            load_dotenv(dotenv_path=default_env)
        elif default_env.exists() and not DOTENV_AVAILABLE:
            # Parseo manual liviano si no está instalado python-dotenv
            _parse_env_file_manually(default_env)
    elif Path(env_path).exists():
        if DOTENV_AVAILABLE:
            load_dotenv(dotenv_path=env_path, override=True)
        else:
            _parse_env_file_manually(Path(env_path))

    # 2. Intentar cargar scraper.conf si existe
    conf_values = {}
    if conf_path is None:
        for candidate in [Path("scraper.conf"), Path("config.ini"), Path("moodle.conf")]:
            if candidate.exists():
                conf_values = _read_ini_file(candidate)
                break
    elif Path(conf_path).exists():
        conf_values = _read_ini_file(Path(conf_path))

    # 3. Ensamblar valores con precedencia (ENV > CONF > DEFAULT)
    user = os.getenv("MOODLE_USER") or conf_values.get("user") or ""
    password = os.getenv("MOODLE_PASSWORD") or conf_values.get("password") or ""
    
    base_url = (
        os.getenv("MOODLE_BASE_URL")
        or conf_values.get("base_url")
        or "https://aulas.itu.uncu.edu.ar/itu/"
    )
    if not base_url.endswith("/"):
        base_url += "/"

    download_dir_str = (
        os.getenv("DOWNLOAD_DIR")
        or conf_values.get("download_dir")
        or "./downloads"
    )
    download_dir = Path(download_dir_str).resolve()

    timeout = int(os.getenv("REQUEST_TIMEOUT") or conf_values.get("timeout") or 30)
    max_retries = int(os.getenv("MAX_RETRIES") or conf_values.get("max_retries") or 3)
    chunk_size_kb = int(os.getenv("CHUNK_SIZE_KB") or conf_values.get("chunk_size_kb") or 8)

    overwrite_existing = _parse_bool(
        os.getenv("OVERWRITE_EXISTING"),
        default=_parse_bool(conf_values.get("overwrite_existing"), default=False)
    )
    save_section_summaries = _parse_bool(
        os.getenv("SAVE_SECTION_SUMMARIES"),
        default=_parse_bool(conf_values.get("save_section_summaries"), default=True)
    )
    save_consolidated_markdown = _parse_bool(
        os.getenv("SAVE_CONSOLIDATED_MARKDOWN"),
        default=_parse_bool(conf_values.get("save_consolidated_markdown"), default=True)
    )

    return ScraperConfig(
        user=user,
        password=password,
        base_url=base_url,
        download_dir=download_dir,
        timeout=timeout,
        max_retries=max_retries,
        chunk_size_kb=chunk_size_kb,
        overwrite_existing=overwrite_existing,
        save_section_summaries=save_section_summaries,
        save_consolidated_markdown=save_consolidated_markdown
    )


def _read_ini_file(path: Path) -> dict:
    """Lee un archivo de configuración estilo INI."""
    parser = configparser.ConfigParser()
    try:
        parser.read(str(path), encoding="utf-8")
        result = {}
        for section in parser.sections():
            for key, val in parser.items(section):
                result[key.lower()] = val
        return result
    except Exception:
        return {}


def _parse_env_file_manually(path: Path) -> None:
    """Parser manual de emergencia para archivos .env."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip("'\"")
                    if k and k not in os.environ:
                        os.environ[k] = v
    except Exception:
        pass
