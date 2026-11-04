"""
Pruebas del flujo CLI y sus códigos de salida.
"""

from unittest.mock import MagicMock

from moodle_scraper.cli import MoodleCLI
from moodle_scraper.config import ScraperConfig
from moodle_scraper.course_scraper import CourseProcessingStats
from moodle_scraper.parser import Course


def _make_cli():
    config = ScraperConfig(
        user="usuario",
        password="secreto",
        base_url="https://moodle.test/moodle/",
    )
    cli = MoodleCLI(config)
    cli.session.login = MagicMock(return_value=True)
    cli.discover_enrolled_courses = MagicMock(
        return_value=[Course(id="1", name="Curso")]
    )
    cli._select_courses = MagicMock(return_value=[Course(id="1", name="Curso")])
    return cli


def test_cli_returns_zero_when_everything_succeeds():
    cli = _make_cli()
    cli.course_scraper.process_course = MagicMock(
        return_value=CourseProcessingStats(files_downloaded=3, links_broken=0)
    )

    assert cli.run(None) == 0


def test_cli_returns_nonzero_on_file_failures():
    cli = _make_cli()
    cli.course_scraper.process_course = MagicMock(
        return_value=CourseProcessingStats(files_downloaded=1, files_failed=1)
    )

    assert cli.run(None) == 1


def test_cli_returns_nonzero_on_broken_links():
    cli = _make_cli()
    cli.course_scraper.process_course = MagicMock(
        return_value=CourseProcessingStats(files_downloaded=1, links_broken=2)
    )

    assert cli.run(None) == 1


def test_cli_returns_two_when_session_expires_during_download():
    cli = _make_cli()
    from moodle_scraper.session import MoodleAuthError

    cli.course_scraper.process_course = MagicMock(
        side_effect=MoodleAuthError("sesión expirada")
    )

    assert cli.run(None) == 2
