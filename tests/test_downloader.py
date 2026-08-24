"""
Pruebas unitarias para resolución de nombres de archivo y cabeceras Content-Disposition.
"""

import unittest
from unittest.mock import MagicMock
import requests
from moodle_scraper.config import ScraperConfig
from moodle_scraper.downloader import Downloader


class TestDownloader(unittest.TestCase):

    def setUp(self):
        self.session_mock = MagicMock()
        self.config = ScraperConfig()
        self.downloader = Downloader(self.session_mock, self.config)

    def test_extract_filename_rfc5987(self):
        resp = MagicMock(spec=requests.Response)
        resp.headers = {
            "Content-Disposition": "attachment; filename*=UTF-8''Gu%C3%ADa%20de%20Trabajos%20Pr%C3%A1cticos.pdf"
        }
        filename = self.downloader.extract_filename_from_headers(resp)
        self.assertEqual(filename, "Guía de Trabajos Prácticos.pdf")

    def test_extract_filename_standard_quotes(self):
        resp = MagicMock(spec=requests.Response)
        resp.headers = {
            "Content-Disposition": 'attachment; filename="Teoria_Arquitectura_2025.pptx"'
        }
        filename = self.downloader.extract_filename_from_headers(resp)
        self.assertEqual(filename, "Teoria_Arquitectura_2025.pptx")

    def test_resolve_filename_fallback_with_content_type(self):
        resp = MagicMock(spec=requests.Response)
        resp.headers = {
            "Content-Type": "application/pdf"
        }
        resp.url = "https://aulas.itu.uncu.edu.ar/itu/mod/resource/view.php?id=999"
        
        filename = self.downloader.resolve_filename(resp, fallback_name="Resumen de Cursada")
        self.assertEqual(filename, "Resumen de Cursada.pdf")

    def test_resolve_filename_from_url_path(self):
        resp = MagicMock(spec=requests.Response)
        resp.headers = {}
        resp.url = "https://aulas.itu.uncu.edu.ar/itu/pluginfile.php/123/mod_resource/content/1/Presentacion.pdf"
        
        filename = self.downloader.resolve_filename(resp, fallback_name="Default")
        self.assertEqual(filename, "Presentacion.pdf")


if __name__ == "__main__":
    unittest.main()
