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


def test_extract_filename_repairs_utf8_read_as_latin1():
    downloader = _make_downloader()
    resp = MagicMock(spec=requests.Response)
    resp.headers = {
        "Content-Disposition": 'attachment; filename="PresentaciÃ³n.pdf"'
    }

    filename = downloader.extract_filename_from_headers(resp)
    assert filename == "Presentación.pdf"


def test_resolve_filename_repairs_mojibake_before_sanitizing():
    downloader = _make_downloader()
    resp = MagicMock(spec=requests.Response)
    resp.headers = {
        "Content-Disposition": 'attachment; filename="InvestigaciÃ³n.pdf"'
    }
    resp.url = "https://moodle.test/pluginfile.php/1/InvestigaciÃ³n.pdf"

    filename = downloader.resolve_filename(resp)

    assert filename == "Investigacion.pdf"
    assert "A3" not in filename


def test_download_file_adds_suffix_before_extension(tmp_path):
    downloader = _make_downloader()
    response = MagicMock(spec=requests.Response)
    response.headers = {
        "Content-Disposition": 'inline; filename="image.png"',
        "Content-Length": "4",
    }
    response.url = "https://moodle.test/pluginfile.php/1/image.png"
    response.iter_content.return_value = [b"data"]
    downloader.session.get.return_value = response

    success, path, _ = downloader.download_file(
        response.url,
        tmp_path,
        filename_suffix="abc123",
    )

    assert success is True
    assert path == tmp_path / "image-abc123.png"
    assert path.read_bytes() == b"data"


def test_download_file_rejects_non_image_content_type(tmp_path):
    downloader = _make_downloader()
    response = MagicMock(spec=requests.Response)
    response.headers = {
        "Content-Type": "text/html; charset=utf-8",
        "Content-Length": "100",
    }
    response.url = "https://moodle.test/pluginfile.php/1/image.png"
    response.iter_content.return_value = [b"<html>login</html>"]
    downloader.session.get.return_value = response

    success, path, msg = downloader.download_file(
        response.url,
        tmp_path,
        allowed_content_prefix="image/",
    )

    assert success is False
    assert path is None
    assert "Tipo de contenido no permitido" in msg
    assert not (tmp_path / "image.png").exists()
    response.close.assert_called_once()


def test_download_file_accepts_octet_stream_for_image_extension(tmp_path):
    downloader = _make_downloader()
    response = MagicMock(spec=requests.Response)
    response.headers = {
        "Content-Type": "application/octet-stream",
        "Content-Length": "4",
    }
    response.url = "https://moodle.test/pluginfile.php/1/image.png"
    response.iter_content.return_value = [b"data"]
    downloader.session.get.return_value = response

    success, path, _ = downloader.download_file(
        response.url,
        tmp_path,
        allowed_content_prefix="image/",
    )

    assert success is True
    assert path == tmp_path / "image.png"


def test_download_file_rejects_oversized_by_content_length(tmp_path):
    downloader = _make_downloader()
    response = MagicMock(spec=requests.Response)
    response.headers = {
        "Content-Type": "image/png",
        "Content-Length": "100",
    }
    response.url = "https://moodle.test/pluginfile.php/1/image.png"
    downloader.session.get.return_value = response

    success, path, msg = downloader.download_file(
        response.url,
        tmp_path,
        allowed_content_prefix="image/",
        max_bytes=10,
    )

    assert success is False
    assert path is None
    assert "tamaño máximo" in msg
    assert list(tmp_path.iterdir()) == []
    response.close.assert_called_once()


def test_download_file_rejects_oversized_while_streaming(tmp_path):
    downloader = _make_downloader()
    response = MagicMock(spec=requests.Response)
    response.headers = {
        "Content-Type": "image/png",
        "Content-Disposition": 'inline; filename="image.png"',
    }
    response.url = "https://moodle.test/pluginfile.php/1/image.png"
    response.iter_content.return_value = [b"0123456789ABCDEF"]
    downloader.session.get.return_value = response

    success, path, msg = downloader.download_file(
        response.url,
        tmp_path,
        allowed_content_prefix="image/",
        max_bytes=5,
    )

    assert success is False
    assert path is None
    assert "tamaño máximo" in msg
    assert list(tmp_path.iterdir()) == []
