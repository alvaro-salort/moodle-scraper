"""
Pruebas unitarias para utilidades, sanitización de archivos y formateo.
"""

import unittest
from pathlib import Path
from moodle_scraper.utils import (
    sanitize_filename,
    format_bytes,
    make_absolute_url,
    WINDOWS_RESERVED_NAMES
)


class TestUtils(unittest.TestCase):

    def test_sanitize_forbidden_characters(self):
        # Caracteres prohibidos en Windows: < > : " / \ | ? *
        raw = '2025B - Álgebra y Estadística: "Junin/DS" <Tema 1>? *Guía|Doc*'
        cleaned = sanitize_filename(raw)
        
        for char in ['<', '>', ':', '"', '/', '\\', '|', '?', '*']:
            self.assertNotIn(char, cleaned)
        
        self.assertTrue(len(cleaned) > 0)

    def test_sanitize_windows_reserved_names(self):
        # Nombres como CON, PRN, AUX, NUL, COM1, LPT1
        for reserved in ["CON", "prn", "aux.txt", "NUL.pdf", "COM1"]:
            cleaned = sanitize_filename(reserved)
            stem = Path(cleaned).stem.upper()
            self.assertNotIn(stem, WINDOWS_RESERVED_NAMES)

    def test_sanitize_max_length(self):
        long_name = "A" * 300 + ".pdf"
        cleaned = sanitize_filename(long_name, max_length=100)
        self.assertLessEqual(len(cleaned), 100)
        self.assertTrue(cleaned.endswith(".pdf"))

    def test_format_bytes(self):
        self.assertEqual(format_bytes(500), "500.00 B")
        self.assertEqual(format_bytes(1024), "1.00 KB")
        self.assertEqual(format_bytes(1048576), "1.00 MB")
        self.assertEqual(format_bytes(1073741824), "1.00 GB")
        self.assertEqual(format_bytes(None), "0 B")

    def test_make_absolute_url(self):
        base = "https://aulas.itu.uncu.edu.ar/itu/"
        rel1 = "mod/resource/view.php?id=1234"
        rel2 = "/itu/course/view.php?id=567"
        abs1 = "https://otro-servidor.com/archivo.pdf"

        self.assertEqual(make_absolute_url(base, rel1), "https://aulas.itu.uncu.edu.ar/itu/mod/resource/view.php?id=1234")
        self.assertEqual(make_absolute_url(base, rel2), "https://aulas.itu.uncu.edu.ar/itu/course/view.php?id=567")
        self.assertEqual(make_absolute_url(base, abs1), "https://otro-servidor.com/archivo.pdf")


if __name__ == "__main__":
    unittest.main()
