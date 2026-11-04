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

from moodle_scraper.config import (
    load_config,
    prompt_for_base_url,
    prompt_for_credentials,
)
from moodle_scraper.cli import MoodleCLI
from moodle_scraper.integrity import check_directory, write_report
from moodle_scraper.manifest import verify_directory
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
        help=(
            "Cookie de sesión 'MoodleSession' para login directo. "
            "Preferí MOODLE_SESSION_COOKIE o el prompt interactivo; "
            "usá '-' para leerla por stdin sin dejarla en el historial."
        )
    )
    parser.add_argument(
        "--check-links",
        type=str,
        metavar="DIR",
        default=None,
        help="Verifica los enlaces locales de un directorio de descargas y sale (no requiere login)"
    )
    parser.add_argument(
        "--verify",
        type=str,
        metavar="DIR",
        default=None,
        help="Verifica tamaño y SHA-256 de los archivos registrados en los manifest.json (no requiere login)"
    )

    return parser.parse_args()


def _run_link_check(root: Path) -> int:
    """Verifica enlaces locales de un directorio sin autenticarse."""
    root = root.expanduser().resolve()
    if not root.exists() or not root.is_dir():
        Logger.error(f"No existe el directorio a verificar: {root}")
        return 1

    issues = check_directory(root)
    report_path = write_report(root, issues)

    Logger.header("VERIFICACIÓN DE ENLACES LOCALES")
    for issue in issues[:50]:
        Logger.warn(issue.describe(root))
    if len(issues) > 50:
        Logger.warn(f"... y {len(issues) - 50} referencia(s) más en {report_path.name}")

    if issues:
        Logger.error(f"Se encontraron {len(issues)} referencia(s) rota(s). Reporte: {report_path}")
        return 1

    Logger.success(f"Todas las referencias locales existen. Reporte: {report_path}")
    return 0


def _run_manifest_verify(root: Path) -> int:
    """Verifica los archivos registrados en los manifest.json de un directorio."""
    root = root.expanduser().resolve()
    if not root.exists() or not root.is_dir():
        Logger.error(f"No existe el directorio a verificar: {root}")
        return 1

    manifests = list(root.rglob("manifest.json"))
    if not manifests:
        Logger.warn(f"No se encontraron manifest.json en {root}")
        return 1

    issues = verify_directory(root)
    report_path = root / "verificacion_manifest.txt"
    report_path.write_text(
        "\n".join(["Verificación de manifest", "======================", f"Errores: {len(issues)}", ""] + issues) + "\n",
        encoding="utf-8",
    )

    Logger.header("VERIFICACIÓN DE MANIFEST Y HASHES")
    for issue in issues[:50]:
        Logger.warn(issue)
    if len(issues) > 50:
        Logger.warn(f"... y {len(issues) - 50} problema(s) más en {report_path.name}")

    if issues:
        Logger.error(f"Se encontraron {len(issues)} problema(s). Reporte: {report_path}")
        return 1

    Logger.success(f"Todos los archivos coinciden con su manifest. Reporte: {report_path}")
    return 0


def main() -> int:
    args = parse_arguments()

    if args.check_links:
        return _run_link_check(Path(args.check_links))
    if args.verify:
        return _run_manifest_verify(Path(args.verify))
    
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
        if args.cookie == "-":
            config.session_cookie = sys.stdin.readline().strip()
        else:
            config.session_cookie = args.cookie
            Logger.warn(
                "La cookie pasada por --cookie queda visible en el historial del shell. "
                "Usá --cookie - o MOODLE_SESSION_COOKIE."
            )

    try:
        Logger.header("MOODLE 4.x SCRAPER & TEORÍA EXTRACTOR - ITU UNCUYO")
        prompt_for_base_url(config)
        prompt_for_credentials(config)
        cli = MoodleCLI(config)
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
