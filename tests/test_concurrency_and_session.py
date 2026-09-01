"""
Pruebas unitarias para concurrencia, retardo de solicitudes y autenticación por cookie de sesión.
"""

from unittest.mock import MagicMock, patch

import pytest

from moodle_scraper.config import ScraperConfig
from moodle_scraper.session import MoodleSession, MoodleAuthError
from moodle_scraper.course_scraper import CourseScraper, _DownloadJob, CourseProcessingStats
from moodle_scraper.parser import CourseModule


def test_config_defaults_and_validation():
    cfg = ScraperConfig(session_cookie="abc123xyz")
    errors = cfg.validate()
    assert errors == []
    assert cfg.max_workers == 3
    assert cfg.request_delay == 0.0


def test_session_cookie_login_success():
    cfg = ScraperConfig(session_cookie="valid_cookie_123")
    session = MoodleSession(cfg)

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.url = "https://aulas.itu.uncu.edu.ar/itu/my/"
    mock_resp.text = """
    <html>
        <div class="userbutton">Juan Perez</div>
        <script>var M = {cfg: {sesskey: "test_sesskey_999"}};</script>
    </html>
    """

    with patch.object(session.session, "get", return_value=mock_resp):
        success = session.login()
        assert success is True
        assert session.is_authenticated is True
        assert session.sesskey == "test_sesskey_999"
        assert session.user_fullname == "Juan Perez"


def test_session_cookie_login_failure():
    cfg = ScraperConfig(session_cookie="expired_cookie_123")
    session = MoodleSession(cfg)

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.url = "https://aulas.itu.uncu.edu.ar/itu/login/index.php"
    mock_resp.text = "<html>Login</html>"

    with patch.object(session.session, "get", return_value=mock_resp):
        with pytest.raises(MoodleAuthError):
            session.login()


def test_concurrent_download_execution(tmp_path):
    cfg = ScraperConfig(max_workers=4)
    session = MoodleSession(cfg)
    scraper = CourseScraper(session, cfg)

    stats = CourseProcessingStats()
    mod = CourseModule(id="1", mod_type="resource", name="Doc1.pdf")

    with patch.object(
        scraper.downloader,
        "download_file",
        return_value=(True, tmp_path / "Doc1.pdf", "Descargado correctamente"),
    ):
        jobs = [
            _DownloadJob(
                url=f"https://example.com/file{i}.pdf",
                dest_dir=tmp_path,
                fallback_name=f"file{i}.pdf",
                source_info=f"Recurso {i}",
                target_module=mod,
                is_direct_resource=True,
                section_name="Tema 1",
            )
            for i in range(5)
        ]

        scraper._execute_download_jobs(jobs, stats)
        assert stats.files_downloaded == 5
        assert stats.files_failed == 0
        assert len(mod.files) == 1
