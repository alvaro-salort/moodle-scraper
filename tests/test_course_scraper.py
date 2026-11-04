"""
Pruebas para la descarga de imágenes embebidas de un curso.
"""

from pathlib import Path
from unittest.mock import MagicMock

from moodle_scraper.config import ScraperConfig
from moodle_scraper.course_scraper import CourseProcessingStats, CourseScraper
from moodle_scraper.parser import CourseModule, CourseSection


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
