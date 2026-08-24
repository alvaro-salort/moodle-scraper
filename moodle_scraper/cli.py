"""
Interfaz de Línea de Comandos (CLI) interactiva y automatizada para el Moodle Scraper.
Permite descubrir cursos, seleccionar interactivamente o procesar en lote.
"""

import argparse
import sys
import time
from typing import List, Optional
import requests

from moodle_scraper.config import ScraperConfig, load_config
from moodle_scraper.course_scraper import CourseScraper, CourseProcessingStats
from moodle_scraper.parser import Course, MoodleParser
from moodle_scraper.session import MoodleSession, MoodleAuthError
from moodle_scraper.utils import Logger, Colors


class MoodleCLI:
    """Controlador de interacción y flujo CLI."""

    def __init__(self, config: ScraperConfig):
        self.config = config
        self.session = MoodleSession(config)
        self.course_scraper = CourseScraper(self.session, config)
        self.discovered_courses: List[Course] = []

    def run(self, args: Optional[argparse.Namespace] = None) -> int:
        """Punto de entrada principal del flujo CLI."""
        Logger.header("MOODLE 4.x SCRAPER & TEORÍA EXTRACTOR - ITU UNCUYO")
        
        # Validar configuración
        errors = self.config.validate()
        if errors:
            for err in errors:
                Logger.error(err)
            Logger.warn("Por favor configure sus credenciales en el archivo .env o scraper.conf")
            return 1

        # 1. Autenticación
        try:
            self.session.login()
        except MoodleAuthError as e:
            Logger.error(str(e))
            return 1
        except Exception as e:
            Logger.error(f"Error inesperado al iniciar sesión: {e}")
            return 1

        # 2. Descubrimiento de Cursos
        self.discovered_courses = self.discover_enrolled_courses()
        if not self.discovered_courses:
            Logger.warn("No se encontraron cursos matriculados en la cuenta o la plataforma no los listó.")
            return 0

        # 3. Selección de cursos a procesar
        selected_courses = self._select_courses(args)
        if not selected_courses:
            Logger.info("Operación cancelada por el usuario.")
            return 0

        # 4. Procesamiento
        start_time = time.time()
        total_stats = CourseProcessingStats()

        Logger.header(f"INICIANDO DESCARGA DE {len(selected_courses)} CURSO(S)")

        for idx, course in enumerate(selected_courses, 1):
            stats = self.course_scraper.process_course(
                course,
                course_index=idx,
                total_courses=len(selected_courses)
            )
            total_stats.files_downloaded += stats.files_downloaded
            total_stats.files_skipped += stats.files_skipped
            total_stats.files_failed += stats.files_failed
            total_stats.pages_extracted += stats.pages_extracted
            total_stats.sections_count += stats.sections_count

        elapsed = time.time() - start_time
        
        # 5. Resumen final
        Logger.header("RESUMEN GENERAL DE DESCARGA")
        print(f"{Colors.BOLD}{Colors.GREEN}✔ Cursos procesados: {len(selected_courses)}{Colors.RESET}")
        print(f"{Colors.BOLD}{Colors.CYAN}✔ Archivos nuevos descargados: {total_stats.files_downloaded}{Colors.RESET}")
        print(f"{Colors.BOLD}{Colors.YELLOW}✔ Archivos omitidos (ya existentes): {total_stats.files_skipped}{Colors.RESET}")
        print(f"{Colors.BOLD}{Colors.MAGENTA}✔ Páginas teóricas extraídas a Markdown: {total_stats.pages_extracted}{Colors.RESET}")
        if total_stats.files_failed > 0:
            print(f"{Colors.BOLD}{Colors.RED}✖ Errores en archivos: {total_stats.files_failed}{Colors.RESET}")
        print(f"{Colors.BOLD}{Colors.WHITE}⏱ Tiempo total: {elapsed:.1f} segundos{Colors.RESET}")
        print(f"\n{Colors.GREEN}Archivos y teoría organizados en: {self.config.download_dir.resolve()}{Colors.RESET}\n")

        return 0

    def discover_enrolled_courses(self) -> List[Course]:
        """Descubre cursos utilizando múltiples estrategias (AJAX, my/courses.php, my/)."""
        courses_map = {}
        Logger.info("Buscando cursos matriculados...")

        # Estrategia 1: AJAX Endpoint de Moodle 4.x con sesskey
        if self.session.sesskey:
            try:
                ajax_url = f"lib/ajax/service.php?sesskey={self.session.sesskey}&info=core_course_get_enrolled_courses_by_timeline_classification"
                payload = [{
                    "index": 0,
                    "methodname": "core_course_get_enrolled_courses_by_timeline_classification",
                    "args": {
                        "offset": 0,
                        "limit": 0,
                        "classification": "all",
                        "sort": "fullname",
                        "customfieldname": "",
                        "customfieldvalue": ""
                    }
                }]
                resp = self.session.post(ajax_url, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    ajax_courses = MoodleParser.parse_courses_from_ajax(data, self.config.base_url)
                    for c in ajax_courses:
                        courses_map[c.id] = c
                    if ajax_courses:
                        Logger.success(f"Se encontraron {len(ajax_courses)} cursos mediante la API de Moodle.")
            except Exception as e:
                Logger.warn(f"No se pudo consultar el servicio AJAX de cursos: {e}")

        # Estrategia 2: my/courses.php (Vista Mis Cursos Moodle 4.x)
        if not courses_map:
            try:
                resp = self.session.get("my/courses.php")
                if resp.status_code == 200:
                    html_courses = MoodleParser.parse_courses_from_html(resp.text, self.config.base_url)
                    for c in html_courses:
                        courses_map[c.id] = c
            except Exception:
                pass

        # Estrategia 3: my/ (Dashboard principal)
        if not courses_map:
            try:
                resp = self.session.get("my/")
                if resp.status_code == 200:
                    html_courses = MoodleParser.parse_courses_from_html(resp.text, self.config.base_url)
                    for c in html_courses:
                        courses_map[c.id] = c
            except Exception:
                pass

        courses = list(courses_map.values())
        courses.sort(key=lambda x: x.name)
        return courses

    def _select_courses(self, args: Optional[argparse.Namespace]) -> List[Course]:
        """Gestiona la selección interactiva o por parámetros CLI."""
        # 1. Si se pasó argumento --all
        if args and getattr(args, "all", False):
            return self.discovered_courses

        # 2. Si se pasó argumento --course-id
        if args and getattr(args, "course_id", None):
            cid = str(args.course_id)
            matched = [c for c in self.discovered_courses if c.id == cid]
            if matched:
                return matched
            # Si no estaba en la lista descubierta, crear objeto ad-hoc
            return [Course(id=cid, name=f"Curso_{cid}", url=f"{self.config.base_url}course/view.php?id={cid}")]

        # 3. Si se pasó argumento --filter
        if args and getattr(args, "filter", None):
            pattern = args.filter.lower()
            matched = [c for c in self.discovered_courses if pattern in c.name.lower()]
            if matched:
                return matched
            Logger.warn(f"No se encontraron cursos que coincidan con el filtro '{args.filter}'")

        # 4. Modo interactivo
        print(f"\n{Colors.BOLD}{Colors.CYAN}Cursos disponibles en su cuenta:{Colors.RESET}")
        print(f"{Colors.DIM}{'─'*70}{Colors.RESET}")
        for i, c in enumerate(self.discovered_courses, 1):
            print(f"  {Colors.BOLD}{Colors.YELLOW}[{i:2d}]{Colors.RESET} {c.name} {Colors.DIM}(ID: {c.id}){Colors.RESET}")
        print(f"{Colors.DIM}{'─'*70}{Colors.RESET}")
        print(f"  {Colors.BOLD}{Colors.GREEN}[ a]{Colors.RESET} Descargar TODOS los cursos")
        print(f"  {Colors.BOLD}{Colors.RED}[ q]{Colors.RESET} Salir\n")

        while True:
            choice = input(f"{Colors.BOLD}{Colors.CYAN}Seleccione una opción (ej: 1, 1-3, 1,4,7 o 'a'): {Colors.RESET}").strip().lower()
            if not choice:
                continue
            if choice in ("q", "quit", "exit", "salir"):
                return []
            if choice in ("a", "all", "todos", "*"):
                return self.discovered_courses

            # Parsear selección múltiple (ej: 1,2,5 o 1-4)
            selected = self._parse_indices(choice, len(self.discovered_courses))
            if selected:
                return [self.discovered_courses[i - 1] for i in selected]
            
            print(f"{Colors.RED}Selección inválida. Intente de nuevo.{Colors.RESET}")

    def _parse_indices(self, input_str: str, max_val: int) -> List[int]:
        """Parsea cadenas de rango como '1,2,5' o '1-4'."""
        indices = set()
        parts = input_str.split(",")
        for part in parts:
            part = part.strip()
            if "-" in part:
                subparts = part.split("-")
                if len(subparts) == 2 and subparts[0].isdigit() and subparts[1].isdigit():
                    start, end = int(subparts[0]), int(subparts[1])
                    for n in range(start, end + 1):
                        if 1 <= n <= max_val:
                            indices.add(n)
            elif part.isdigit():
                n = int(part)
                if 1 <= n <= max_val:
                    indices.add(n)
        return sorted(list(indices))
