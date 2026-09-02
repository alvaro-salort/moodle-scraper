"""
Pruebas unitarias para formateador de Markdown y escritor de teoría.
"""

from moodle_scraper.markdown_writer import MarkdownFormatter, CourseMarkdownWriter
from moodle_scraper.parser import Course, CourseSection, CourseModule, FileItem


def test_html_to_markdown_formatting():
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

    assert "## Introducción al Álgebra" in md
    assert "**negrita**" in md
    assert "*cursiva*" in md
    assert "- Elemento 1" in md
    assert "- Elemento 2" in md
    assert "[este enlace](https://ejemplo.com)" in md
    assert "> Cita célebre" in md


def test_generate_consolidated_markdown(tmp_path):
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

    out_file = tmp_path / "notas_y_teoria_completa.md"
    CourseMarkdownWriter.generate_consolidated_markdown(course, [sec1], out_file)

    assert out_file.exists()
    content = out_file.read_text(encoding="utf-8")

    assert "# 📚 2025B - Álgebra y Estadística - Junin/DS" in content
    assert "## 📑 Índice de Contenidos" in content
    assert "Tema 1: Matrices y Determinantes" in content
    assert "Definición de Matriz" in content
    assert "Una matriz es un arreglo bidimensional" in content
    assert "Ejercicios_Matrices.pdf" in content
