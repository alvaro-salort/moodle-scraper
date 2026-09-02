"""
Pruebas unitarias para utilidades, sanitización de archivos y formateo.
"""

from pathlib import Path
from moodle_scraper.utils import (
    sanitize_filename,
    format_bytes,
    make_absolute_url,
    WINDOWS_RESERVED_NAMES
)


def test_sanitize_forbidden_characters_and_accents():
    raw = '2025B - Álgebra y Estadística: "Junin/DS" <Año 1>? *Guía de Diseño | Ñandú*'
    cleaned = sanitize_filename(raw)

    for char in ['<', '>', ':', '"', '/', '\\', '|', '?', '*']:
        assert char not in cleaned

    for char in ['á', 'é', 'í', 'ó', 'ú', 'Á', 'É', 'Í', 'Ó', 'Ú', 'ñ', 'Ñ', 'ü', 'Ü']:
        assert char not in cleaned

    assert "Algebra y Estadistica" in cleaned
    assert "Ano 1" in cleaned
    assert "Guia de Diseno" in cleaned
    assert "Nandu" in cleaned
    assert len(cleaned) > 0


def test_sanitize_windows_reserved_names():
    for reserved in ["CON", "prn", "aux.txt", "NUL.pdf", "COM1"]:
        cleaned = sanitize_filename(reserved)
        stem = Path(cleaned).stem.upper()
        assert stem not in WINDOWS_RESERVED_NAMES


def test_sanitize_max_length():
    long_name = "A" * 300 + ".pdf"
    cleaned = sanitize_filename(long_name, max_length=100)
    assert len(cleaned) <= 100
    assert cleaned.endswith(".pdf")


def test_format_bytes():
    assert format_bytes(500) == "500.00 B"
    assert format_bytes(1024) == "1.00 KB"
    assert format_bytes(1048576) == "1.00 MB"
    assert format_bytes(1073741824) == "1.00 GB"
    assert format_bytes(None) == "0 B"


def test_make_absolute_url():
    base = "https://aulas.itu.uncu.edu.ar/itu/"
    rel1 = "mod/resource/view.php?id=1234"
    rel2 = "/itu/course/view.php?id=567"
    abs1 = "https://otro-servidor.com/archivo.pdf"

    assert make_absolute_url(base, rel1) == "https://aulas.itu.uncu.edu.ar/itu/mod/resource/view.php?id=1234"
    assert make_absolute_url(base, rel2) == "https://aulas.itu.uncu.edu.ar/itu/course/view.php?id=567"
    assert make_absolute_url(base, abs1) == "https://otro-servidor.com/archivo.pdf"
