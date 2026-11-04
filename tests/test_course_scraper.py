"""
Pruebas para la descarga de imágenes embebidas de un curso.
"""

from pathlib import Path
from unittest.mock import MagicMock

from moodle_scraper.config import ScraperConfig
from moodle_scraper.course_scraper import CourseProcessingStats, CourseScraper, _DownloadJob
from moodle_scraper.manifest import RunManifest, sha256_file
from moodle_scraper.parser import CourseModule, CourseSection, FileItem


def _make_scraper(**config_overrides):
    config = ScraperConfig(base_url="https://moodle.test/moodle/", max_workers=1)
    for key, value in config_overrides.items():
        setattr(config, key, value)
    scraper = CourseScraper(session=MagicMock(), config=config)
    scraper.downloader = MagicMock()
    return scraper


def _fake_download(url, dest, **kwargs):
    suffix = kwargs.get("filename_suffix", "img")
    return True, Path(dest) / f"{suffix}.png", "Descargado correctamente"


def _section_with_images(images_by_module):
    section = CourseSection(id="sec-1", section_number=1, name="Tema 1")
    for index, (html, module_url) in enumerate(images_by_module, 1):
        section.modules.append(
            CourseModule(
                id=f"mod-{index}",
                mod_type="page",
                name=f"Página {index}",
                url=module_url,
                content_html=html,
            )
        )
    return section


def test_download_course_images_deduplicates_and_skips_external(tmp_path):
    scraper = _make_scraper()
    scraper.downloader.download_file.side_effect = _fake_download

    internal = "https://moodle.test/moodle/pluginfile.php/1/a.png"
    relative = "pluginfile.php/2/b.png"
    relative_abs = "https://moodle.test/moodle/pluginfile.php/2/b.png"
    section = _section_with_images([
        (
            f'<img src="{internal}" alt="A">'
            '<img src="data:image/png;base64,AAAA">'
            '<img src="https://tracker.test/pixel.png">',
            "https://moodle.test/moodle/mod/page/view.php?id=1",
        ),
        (
            f'<img src="{internal}"><img src="{relative}" alt="B">',
            "https://moodle.test/moodle/mod/page/view.php?id=2",
        ),
    ])
    stats = CourseProcessingStats()

    paths = scraper._download_course_images([section], tmp_path, stats)

    called_urls = {call.args[0] for call in scraper.downloader.download_file.call_args_list}
    assert called_urls == {internal, relative_abs}
    assert set(paths) == {internal, relative_abs}
    assert stats.images_downloaded == 2
    assert stats.images_failed == 0


def test_download_course_images_skips_when_markdown_is_disabled(tmp_path):
    scraper = _make_scraper(
        save_section_summaries=False,
        save_consolidated_markdown=False,
    )
    section = CourseSection(
        id="sec-1",
        section_number=1,
        name="Tema 1",
        summary_html='<img src="https://moodle.test/moodle/pluginfile.php/1/a.png">',
    )

    paths = scraper._download_course_images(
        [section], tmp_path, CourseProcessingStats()
    )

    assert paths == {}
    scraper.downloader.download_file.assert_not_called()


def test_download_course_images_counts_failures(tmp_path):
    scraper = _make_scraper()
    scraper.downloader.download_file.return_value = (
        False,
        None,
        "Tipo de contenido no permitido: text/html",
    )
    section = CourseSection(
        id="sec-1",
        section_number=1,
        name="Tema 1",
        summary_html='<img src="https://moodle.test/moodle/pluginfile.php/1/a.png">',
    )
    stats = CourseProcessingStats()

    paths = scraper._download_course_images([section], tmp_path, stats)

    assert paths == {}
    assert stats.images_failed == 1
    assert stats.images_downloaded == 0


def test_download_course_images_counts_skipped_existing_files(tmp_path):
    scraper = _make_scraper()
    scraper.downloader.download_file.return_value = (
        True,
        tmp_path / "imagenes" / "a.png",
        "Omitido por existencia previa",
    )
    section = CourseSection(
        id="sec-1",
        section_number=1,
        name="Tema 1",
        summary_html='<img src="https://moodle.test/moodle/pluginfile.php/1/a.png">',
    )
    stats = CourseProcessingStats()

    paths = scraper._download_course_images([section], tmp_path, stats)

    assert len(paths) == 1
    assert stats.images_skipped == 1
    assert stats.images_downloaded == 0


def test_handle_download_result_updates_local_name_for_existing_file(tmp_path):
    scraper = _make_scraper()
    url = "https://moodle.test/moodle/pluginfile.php/1/Presentaci%C3%B3n.pdf"
    file_item = FileItem(name="Presentación.pdf", url=url, section_name="Tema 1")
    module = CourseModule(
        id="mod-1",
        mod_type="folder",
        name="Carpeta",
        files=[file_item],
    )
    job = _DownloadJob(
        url=url,
        dest_dir=tmp_path,
        fallback_name="Presentación.pdf",
        source_info="Archivo",
        target_module=module,
        section_name="Tema 1",
    )
    local_path = tmp_path / "Presentacion.pdf"

    scraper._handle_download_result(
        True,
        local_path,
        "Descargado correctamente",
        job,
        CourseProcessingStats(),
    )

    assert file_item.local_name == "Presentacion.pdf"


def test_handle_download_result_uses_local_name_for_direct_resource(tmp_path):
    scraper = _make_scraper()
    url = "https://moodle.test/moodle/mod/resource/view.php?id=1"
    module = CourseModule(id="mod-1", mod_type="resource", name="Recurso")
    job = _DownloadJob(
        url=url,
        dest_dir=tmp_path,
        fallback_name="Recurso",
        source_info="Recurso",
        target_module=module,
        is_direct_resource=True,
        section_name="Tema 1",
    )
    local_path = tmp_path / "Recurso.pdf"

    scraper._handle_download_result(
        True,
        local_path,
        "Descargado correctamente",
        job,
        CourseProcessingStats(),
    )

    assert len(module.files) == 1
    assert module.files[0].name == "Recurso.pdf"
    assert module.files[0].local_name == "Recurso.pdf"


def test_execute_download_jobs_skips_files_current_in_manifest(tmp_path):
    scraper = _make_scraper()
    url = "https://moodle.test/moodle/pluginfile.php/1/Presentacion.pdf"
    local_path = tmp_path / "Presentacion.pdf"
    local_path.write_bytes(b"datos")

    manifest = RunManifest(tmp_path, course_id="1", course_name="Curso")
    manifest.record(
        url,
        local_path,
        size=local_path.stat().st_size,
        sha256=sha256_file(local_path),
        remote_size=local_path.stat().st_size,
        remote_mtime=1700000000,
    )
    manifest.save()

    file_item = FileItem(
        name="Presentación.pdf",
        url=url,
        size_bytes=local_path.stat().st_size,
        timemodified=1700000000,
    )
    module = CourseModule(id="mod-1", mod_type="resource", name="Recurso", files=[file_item])
    job = _DownloadJob(
        url=url,
        dest_dir=tmp_path,
        fallback_name="Presentación.pdf",
        source_info="Recurso",
        target_module=module,
        target_file=file_item,
        remote_size=local_path.stat().st_size,
        remote_mtime=1700000000,
    )
    stats = CourseProcessingStats()

    scraper._execute_download_jobs([job], stats, manifest)

    scraper.downloader.download_file.assert_not_called()
    assert stats.files_skipped == 1
    assert file_item.local_name == "Presentacion.pdf"


def test_execute_download_jobs_records_manifest_after_download(tmp_path):
    scraper = _make_scraper()
    url = "https://moodle.test/moodle/pluginfile.php/1/documento.pdf"
    local_path = tmp_path / "documento.pdf"
    local_path.write_bytes(b"datos")
    scraper.downloader.download_file.return_value = (
        True,
        local_path,
        "Descargado correctamente",
    )

    manifest = RunManifest(tmp_path, course_id="1", course_name="Curso")
    file_item = FileItem(name="documento.pdf", url=url)
    module = CourseModule(id="mod-1", mod_type="resource", name="Recurso", files=[file_item])
    job = _DownloadJob(
        url=url,
        dest_dir=tmp_path,
        fallback_name="documento.pdf",
        source_info="Recurso",
        target_module=module,
        target_file=file_item,
    )
    stats = CourseProcessingStats()

    scraper._execute_download_jobs([job], stats, manifest)

    entry = manifest.get(url)
    assert entry is not None
    assert entry["status"] == "ok"
    assert entry["size"] == 5
    assert (tmp_path / "manifest.json").exists()
