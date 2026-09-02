"""
Pruebas unitarias para resolución de nombres de archivo y cabeceras Content-Disposition.
"""

from unittest.mock import MagicMock

import requests

from moodle_scraper.config import ScraperConfig
from moodle_scraper.downloader import Downloader


def _make_downloader():
    session_mock = MagicMock()
    config = ScraperConfig()
    return Downloader(session_mock, config)


def test_extract_filename_rfc5987():
    downloader = _make_downloader()
    resp = MagicMock(spec=requests.Response)
    resp.headers = {
        "Content-Disposition": "attachment; filename*=UTF-8''Gu%C3%ADa%20de%20Trabajos%20Pr%C3%A1cticos.pdf"
    }
    filename = downloader.extract_filename_from_headers(resp)
    assert filename == "Guía de Trabajos Prácticos.pdf"


def test_extract_filename_standard_quotes():
    downloader = _make_downloader()
    resp = MagicMock(spec=requests.Response)
    resp.headers = {
        "Content-Disposition": 'attachment; filename="Teoria_Arquitectura_2025.pptx"'
    }
    filename = downloader.extract_filename_from_headers(resp)
    assert filename == "Teoria_Arquitectura_2025.pptx"


def test_resolve_filename_fallback_with_content_type():
    downloader = _make_downloader()
    resp = MagicMock(spec=requests.Response)
    resp.headers = {
        "Content-Type": "application/pdf"
    }
    resp.url = "https://aulas.itu.uncu.edu.ar/itu/mod/resource/view.php?id=999"

    filename = downloader.resolve_filename(resp, fallback_name="Resumen de Cursada")
    assert filename == "Resumen de Cursada.pdf"


def test_resolve_filename_from_url_path():
    downloader = _make_downloader()
    resp = MagicMock(spec=requests.Response)
    resp.headers = {}
    resp.url = "https://aulas.itu.uncu.edu.ar/itu/pluginfile.php/123/mod_resource/content/1/Presentacion.pdf"

    filename = downloader.resolve_filename(resp, fallback_name="Default")
    assert filename == "Presentacion.pdf"
