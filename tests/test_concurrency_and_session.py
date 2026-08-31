"""
Pruebas unitarias para concurrencia, retardo de solicitudes y autenticación por cookie de sesión.
"""

import unittest
from pathlib import Path
import tempfile
from unittest.mock import MagicMock, patch

from moodle_scraper.config import ScraperConfig, load_config
from moodle_scraper.session import MoodleSession, MoodleAuthError
from moodle_scraper.course_scraper import CourseScraper, _DownloadJob, CourseProcessingStats
from moodle_scraper.parser import Course, CourseSection, CourseModule, FileItem


class TestConcurrencyAndSession(unittest.TestCase):

    def test_config_defaults_and_validation(self):
        # Con cookie de sesión, no requiere usuario ni contraseña
        cfg = ScraperConfig(session_cookie="abc123xyz")
        errors = cfg.validate()
        self.assertEqual(errors, [])
        self.assertEqual(cfg.max_workers, 3)
        self.assertEqual(cfg.request_delay, 0.0)

    def test_session_cookie_login_success(self):
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
            self.assertTrue(success)
            self.assertTrue(session.is_authenticated)
            self.assertEqual(session.sesskey, "test_sesskey_999")
            self.assertEqual(session.user_fullname, "Juan Perez")

    def test_session_cookie_login_failure(self):
        cfg = ScraperConfig(session_cookie="expired_cookie_123")
        session = MoodleSession(cfg)

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.url = "https://aulas.itu.uncu.edu.ar/itu/login/index.php"
        mock_resp.text = "<html>Login</html>"

        with patch.object(session.session, "get", return_value=mock_resp):
            with self.assertRaises(MoodleAuthError):
                session.login()

    def test_concurrent_download_execution(self):
        cfg = ScraperConfig(max_workers=4)
        session = MoodleSession(cfg)
        scraper = CourseScraper(session, cfg)

        stats = CourseProcessingStats()
        mod = CourseModule(id="1", mod_type="resource", name="Doc1.pdf")

        # Mock download_file
        with tempfile.TemporaryDirectory() as tmpdir:
            dest_dir = Path(tmpdir)
            
            with patch.object(scraper.downloader, "download_file", return_value=(True, dest_dir / "Doc1.pdf", "Descargado correctamente")):
                jobs = [
                    _DownloadJob(
                        url=f"https://example.com/file{i}.pdf",
                        dest_dir=dest_dir,
                        fallback_name=f"file{i}.pdf",
                        source_info=f"Recurso {i}",
                        target_module=mod,
                        is_direct_resource=True,
                        section_name="Tema 1"
                    )
                    for i in range(5)
                ]

                scraper._execute_download_jobs(jobs, stats)
                self.assertEqual(stats.files_downloaded, 5)
                self.assertEqual(stats.files_failed, 0)
                self.assertEqual(len(mod.files), 1)  # Direct resource added without duplication


if __name__ == "__main__":
    unittest.main()
