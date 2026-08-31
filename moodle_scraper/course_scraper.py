"""
Orquestador de Procesamiento de Curso: Extrae contenidos, teoría, páginas y descarga recursos.
"""

from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import List, Optional, Tuple
import requests

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


@dataclass
class _DownloadJob:
    """Representa un trabajo de descarga pendiente."""
    url: str
    dest_dir: Path
    fallback_name: str
    source_info: str
    target_module: Optional[CourseModule] = None
    is_direct_resource: bool = False
    section_name: str = ""


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

            download_jobs: List[_DownloadJob] = []

            for mod in sec.modules:
                self._collect_module_jobs(mod, sec, sec_dir, download_jobs, stats)

            # Ejecutar descargas de la sección (secuencial o paralelo según max_workers)
            if download_jobs:
                self._execute_download_jobs(download_jobs, stats)

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

    def _collect_module_jobs(
        self,
        mod: CourseModule,
        section: CourseSection,
        sec_dir: Path,
        jobs: List[_DownloadJob],
        stats: CourseProcessingStats
    ) -> None:
        """Procesa una actividad individual y encola sus descargas necesarias."""
        
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
                        jobs.append(_DownloadJob(
                            url=f.url,
                            dest_dir=sec_dir,
                            fallback_name=f.name,
                            source_info=f"Carpeta: {mod.name}",
                            target_module=mod,
                            section_name=section.name
                        ))
            except Exception as e:
                Logger.error(f"Error procesando carpeta {mod.name}: {e}")

        # D) Recursos directos descargables (/mod/resource/view.php)
        elif mod.mod_type == "resource" and mod.url:
            jobs.append(_DownloadJob(
                url=mod.url,
                dest_dir=sec_dir,
                fallback_name=mod.name,
                source_info=f"Recurso: {mod.name}",
                target_module=mod,
                is_direct_resource=True,
                section_name=section.name
            ))

        # E) Descargar archivos adjuntos detectados en el DOM (pluginfile.php)
        for f in mod.files:
            if f.url and f.url != mod.url:
                jobs.append(_DownloadJob(
                    url=f.url,
                    dest_dir=sec_dir,
                    fallback_name=f.name,
                    source_info=f"Adjunto de {mod.name}",
                    target_module=mod,
                    section_name=section.name
                ))

    def _execute_download_jobs(self, jobs: List[_DownloadJob], stats: CourseProcessingStats) -> None:
        """Ejecuta los trabajos de descarga en paralelo o secuencial según la configuración."""
        workers = max(1, self.config.max_workers)

        def _run_job(job: _DownloadJob) -> Tuple[bool, Optional[Path], str, _DownloadJob]:
            success, path, msg = self.downloader.download_file(
                job.url,
                job.dest_dir,
                fallback_name=job.fallback_name,
                source_info=job.source_info
            )
            return success, path, msg, job

        if workers > 1 and len(jobs) > 1:
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = [executor.submit(_run_job, j) for j in jobs]
                for future in as_completed(futures):
                    try:
                        success, path, msg, job = future.result()
                        self._handle_download_result(success, path, msg, job, stats)
                    except Exception as e:
                        Logger.error(f"Error inesperado en descarga concurrente: {e}")
                        stats.files_failed += 1
        else:
            for job in jobs:
                success, path, msg, job = _run_job(job)
                self._handle_download_result(success, path, msg, job, stats)

    def _handle_download_result(
        self,
        success: bool,
        path: Optional[Path],
        msg: str,
        job: _DownloadJob,
        stats: CourseProcessingStats
    ) -> None:
        """Actualiza las estadísticas y registra el archivo descargado en su módulo correspondiente."""
        if success:
            if "Omitido" in msg:
                stats.files_skipped += 1
            else:
                stats.files_downloaded += 1

            if path and job.is_direct_resource and job.target_module:
                # Evitar duplicar en la lista de files del módulo
                if not any(f.name == path.name for f in job.target_module.files):
                    job.target_module.files.append(FileItem(
                        name=path.name,
                        url=job.url,
                        section_name=job.section_name,
                        source_module=job.target_module.name
                    ))
        else:
            stats.files_failed += 1
