"""
Orquestador de Procesamiento de Curso: Extrae contenidos, teoría, páginas y descarga recursos.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional
import requests
from bs4 import BeautifulSoup

from moodle_scraper.config import ScraperConfig
from moodle_scraper.downloader import Downloader
from moodle_scraper.markdown_writer import CourseMarkdownWriter
from moodle_scraper.parser import Course, CourseSection, CourseModule, FileItem, MoodleParser
from moodle_scraper.session import MoodleSession
from moodle_scraper.utils import Logger, sanitize_filename, make_absolute_url


@dataclass
class CourseProcessingStats:
    """Métricas de ejecución por curso."""
    files_downloaded: int = 0
    files_skipped: int = 0
    files_failed: int = 0
    pages_extracted: int = 0
    sections_count: int = 0


class CourseScraper:
    """Maneja la extracción completa de un curso específico."""

    def __init__(self, session: MoodleSession, config: ScraperConfig):
        self.session = session
        self.config = config
        self.downloader = Downloader(session, config)

    def process_course(self, course: Course, course_index: int = 0, total_courses: int = 0) -> CourseProcessingStats:
        """
        Ejecuta el pipeline completo de extracción y descarga para un curso.
        """
        stats = CourseProcessingStats()
        Logger.course_header(course.name, course_index, total_courses)

        # 1. Crear carpeta raíz del curso
        course_dir = self.config.download_dir / course.sanitized_name
        course_dir.mkdir(parents=True, exist_ok=True)
        Logger.info(f"Directorio local del curso: {course_dir}")

        # 2. Descargar y parsear la página principal del curso
        course_view_url = course.url or f"course/view.php?id={course.id}"
        try:
            resp = self.session.get(course_view_url)
            resp.raise_for_status()
            course_html = resp.text
        except requests.RequestException as e:
            Logger.error(f"No se pudo cargar el curso {course.name} ({course_view_url}): {e}")
            return stats

        sections = MoodleParser.parse_course_sections(course_html, self.config.base_url)
        stats.sections_count = len(sections)
        Logger.info(f"Secciones detectadas: {len(sections)}")

        # 3. Recorrer secciones, procesar actividades y descargar archivos
        for sec in sections:
            Logger.section(sec.name)
            sec_dir = course_dir / sec.folder_name
            sec_dir.mkdir(parents=True, exist_ok=True)

            for mod in sec.modules:
                self._process_module(mod, sec, sec_dir, stats)

            # Guardar resumen del tema si está habilitado
            if self.config.save_section_summaries:
                summary_path = sec_dir / "resumen_tema.md"
                CourseMarkdownWriter.generate_section_summary(course, sec, summary_path)

        # 4. Guardar archivo consolidado de teoría del curso completo
        if self.config.save_consolidated_markdown:
            consolidated_path = course_dir / "notas_y_teoria_completa.md"
            CourseMarkdownWriter.generate_consolidated_markdown(course, sections, consolidated_path)

        # 5. Reporte de resumen del curso
        Logger.info(
            f"Resumen de curso '{course.name}': "
            f"{stats.files_downloaded} descargados, "
            f"{stats.files_skipped} omitidos/existentes, "
            f"{stats.files_failed} errores, "
            f"{stats.pages_extracted} páginas de teoría procesadas."
        )
        return stats

    def _process_module(
        self,
        mod: CourseModule,
        section: CourseSection,
        sec_dir: Path,
        stats: CourseProcessingStats
    ) -> None:
        """Procesa una actividad individual según su tipo (recurso, carpeta, página, URL, etc.)."""
        
        # A) Páginas de contenido (/mod/page/view.php)
        if mod.mod_type == "page" and mod.url:
            try:
                page_resp = self.session.get(mod.url)
                if page_resp.status_code == 200:
                    page_data = MoodleParser.parse_page_content(page_resp.text)
                    mod.content_html = page_data.get("html", "")
                    mod.content_text = page_data.get("text", "")
                    stats.pages_extracted += 1
                    Logger.info(f"Página teórica extraída: {mod.name}")
            except Exception as e:
                Logger.warn(f"No se pudo obtener el contenido de la página {mod.name}: {e}")

        # B) Enlaces externos (/mod/url/view.php)
        elif mod.mod_type == "url" and mod.url:
            try:
                url_resp = self.session.get(mod.url)
                if url_resp.status_code == 200:
                    ext_url = MoodleParser.parse_external_url(url_resp.text)
                    if ext_url:
                        mod.external_url = ext_url
                        Logger.info(f"Enlace externo resuelto: {mod.name} -> {ext_url}")
            except Exception as e:
                Logger.warn(f"No se pudo resolver URL externa {mod.name}: {e}")

        # C) Carpetas con múltiples archivos (/mod/folder/view.php)
        elif mod.mod_type == "folder" and mod.url:
            try:
                folder_resp = self.session.get(mod.url)
                if folder_resp.status_code == 200:
                    folder_files = MoodleParser.parse_folder_files(
                        folder_resp.text,
                        self.config.base_url,
                        section.name,
                        mod.name
                    )
                    mod.files.extend(folder_files)
                    
                    for f in folder_files:
                        success, path, _ = self.downloader.download_file(
                            f.url,
                            sec_dir,
                            fallback_name=f.name,
                            source_info=f"Carpeta: {mod.name}"
                        )
                        if success:
                            if "Omitido" in _:
                                stats.files_skipped += 1
                            else:
                                stats.files_downloaded += 1
                        else:
                            stats.files_failed += 1
            except Exception as e:
                Logger.error(f"Error procesando carpeta {mod.name}: {e}")

        # D) Recursos directos descargables (/mod/resource/view.php)
        elif mod.mod_type == "resource" and mod.url:
            success, path, msg = self.downloader.download_file(
                mod.url,
                sec_dir,
                fallback_name=mod.name,
                source_info=f"Recurso: {mod.name}"
            )
            if success:
                if "Omitido" in msg:
                    stats.files_skipped += 1
                else:
                    stats.files_downloaded += 1
                if path:
                    mod.files.append(FileItem(
                        name=path.name,
                        url=mod.url,
                        section_name=section.name,
                        source_module=mod.name
                    ))
            else:
                stats.files_failed += 1

        # E) Descargar archivos adjuntos detectados en el DOM (pluginfile.php)
        for f in mod.files:
            # Evitar re-descargar si ya fue descargado como parte del recurso
            if f.url and f.url != mod.url:
                success, path, msg = self.downloader.download_file(
                    f.url,
                    sec_dir,
                    fallback_name=f.name,
                    source_info=f"Adjunto de {mod.name}"
                )
                if success:
                    if "Omitido" in msg:
                        stats.files_skipped += 1
                    else:
                        stats.files_downloaded += 1
                else:
                    stats.files_failed += 1
