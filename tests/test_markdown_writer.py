"""
Pruebas unitarias para formateador de Markdown y escritor de teoría.
"""

import tempfile
import unittest
from pathlib import Path

from moodle_scraper.markdown_writer import MarkdownFormatter, CourseMarkdownWriter
from moodle_scraper.parser import Course, CourseSection, CourseModule, FileItem


class TestMarkdownWriter(unittest.TestCase):

    def test_html_to_markdown_formatting(self):
        html = """
        <h2>Introducción al Álgebra</h2>
        <p>Este es un párrafo con <strong>negrita</strong> y <em>cursiva</em>.</p>
        <ul>
            <li>Elemento 1</li>
            <li>Elemento 2</li>
        </ul>
        <p>Visita el sitio en <a href="https://ejemplo.com">este enlace</a>.</p>
        <blockquote>Cita célebre de matemática.</blockquote>
        """
        md = MarkdownFormatter.html_to_markdown(html)

        self.assertIn("## Introducción al Álgebra", md)
        self.assertIn("**negrita**", md)
        self.assertIn("*cursiva*", md)
        self.assertIn("- Elemento 1", md)
        self.assertIn("- Elemento 2", md)
        self.assertIn("[este enlace](https://ejemplo.com)", md)
        self.assertIn("> Cita célebre", md)

    def test_generate_consolidated_markdown(self):
        course = Course(id="101", name="2025B - Álgebra y Estadística - Junin/DS")
        sec1 = CourseSection(
            id="sec-1",
            section_number=1,
            name="Tema 1: Matrices y Determinantes",
            summary_text="En esta unidad veremos matrices y operaciones básicas.",
            modules=[
                CourseModule(
                    id="mod-1",
                    mod_type="page",
                    name="Definición de Matriz",
                    content_text="Una matriz es un arreglo bidimensional de números."
                ),
                CourseModule(
                    id="mod-2",
                    mod_type="resource",
                    name="Ejercicios_Matrices.pdf",
                    files=[FileItem(name="Ejercicios_Matrices.pdf", url="https://example.com/pdf")]
                )
            ]
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            out_file = Path(tmpdir) / "notas_y_teoria_completa.md"
            CourseMarkdownWriter.generate_consolidated_markdown(course, [sec1], out_file)

            self.assertTrue(out_file.exists())
            content = out_file.read_text(encoding="utf-8")
            
            self.assertIn("# 📚 2025B - Álgebra y Estadística - Junin/DS", content)
            self.assertIn("## 📑 Índice de Contenidos", content)
            self.assertIn("Tema 1: Matrices y Determinantes", content)
            self.assertIn("Definición de Matriz", content)
            self.assertIn("Una matriz es un arreglo bidimensional", content)
            self.assertIn("Ejercicios_Matrices.pdf", content)


if __name__ == "__main__":
    unittest.main()
