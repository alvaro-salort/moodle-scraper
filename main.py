#!/usr/bin/env python3
"""
Punto de Entrada Principal del Scraper de Moodle ITU UNCUYO.
Uso:
    python main.py                     # Modo interactivo
    python main.py --all               # Descargar todos los cursos automáticamente
    python main.py --course-id 1234    # Descargar un curso específico por ID
    python main.py --filter "Algebra"  # Filtrar cursos por nombre
"""

import argparse
import sys
from pathlib import Path

from moodle_scraper.config import load_config
from moodle_scraper.cli import MoodleCLI
from moodle_scraper.utils import Logger


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scraper automatizado de Moodle 4.x (ITU UNCUYO): Recursos, documentos y teoría en Markdown.",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        "-a", "--all",
        action="store_true",
        help="Descargar automáticamente todos los cursos matriculados sin preguntar"
    )
    parser.add_argument(
        "-c", "--course-id",
        type=str,
        help="ID numérico de un curso específico de Moodle para descargar"
    )
    parser.add_argument(
        "-f", "--filter",
        type=str,
        help="Texto para filtrar cursos por nombre (ej: 'Algebra', 'Hardware')"
    )
    parser.add_argument(
        "-d", "--download-dir",
        type=str,
        help="Ruta personalizada para la carpeta de descargas (sobreescribe .env)"
    )
    parser.add_argument(
        "--env",
        type=str,
        default=None,
        help="Ruta a un archivo .env específico"
    )
    parser.add_argument(
        "--conf",
        type=str,
        default=None,
        help="Ruta a un archivo de configuración .conf / .ini"
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Sobreescribir archivos locales aunque ya existan"
    )
    parser.add_argument(
        "-w", "--workers",
        type=int,
        default=None,
        help="Número de descargas simultáneas en paralelo (por defecto: 3)"
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=None,
        help="Retardo en segundos entre solicitudes HTTP para proteger el servidor (ej: 0.2)"
    )
    parser.add_argument(
        "--cookie",
        type=str,
        default=None,
        help="Cookie de sesión 'MoodleSession' para login directo (bypass de SSO / Google / MS 365)"
    )

    return parser.parse_args()


def main() -> int:
    args = parse_arguments()
    
    # Cargar configuración desde .env / .conf
    config = load_config(env_path=args.env, conf_path=args.conf)
    
    # Sobreescribir con flags de línea de comando si se pasaron
    if args.download_dir:
        config.download_dir = Path(args.download_dir).resolve()
    if args.overwrite:
        config.overwrite_existing = True
    if args.workers is not None:
        config.max_workers = args.workers
    if args.delay is not None:
        config.request_delay = args.delay
    if args.cookie is not None:
        config.session_cookie = args.cookie

    cli = MoodleCLI(config)

    try:
        return cli.run(args)
    except KeyboardInterrupt:
        print("\n")
        Logger.warn("Proceso interrumpido por el usuario (Ctrl+C).")
        return 130
    except Exception as e:
        Logger.error(f"Error crítico en la ejecución: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
