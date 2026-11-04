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


def test_html_to_markdown_uses_local_image_path():
    html = '<p>Diagrama:</p><img src="https://moodle.test/pluginfile.php/1/diagrama.png" alt="Diagrama">'

    md = MarkdownFormatter.html_to_markdown(
        html,
        {"https://moodle.test/pluginfile.php/1/diagrama.png": "imagenes/diagrama.png"},
    )

    assert "![Diagrama](imagenes/diagrama.png)" in md
    assert "https://moodle.test/pluginfile.php/1/diagrama.png" not in md


def test_html_to_markdown_resolves_relative_image_with_base_url():
    html = '<img src="pluginfile.php/1/diagrama.png" alt="Diagrama">'

    md = MarkdownFormatter.html_to_markdown(
        html,
        {"https://moodle.test/moodle/pluginfile.php/1/diagrama.png": "imagenes/diagrama.png"},
        "https://moodle.test/moodle/",
    )

    assert "![Diagrama](imagenes/diagrama.png)" in md


def test_html_to_markdown_uses_data_src_for_lazy_images():
    html = '<img src="data:image/gif;base64,R0lGOD" data-src="pluginfile.php/2/lazy.png" alt="Lazy">'

    md = MarkdownFormatter.html_to_markdown(
        html,
        {"https://moodle.test/moodle/pluginfile.php/2/lazy.png": "imagenes/lazy.png"},
        "https://moodle.test/moodle/",
    )

    assert "![Lazy](imagenes/lazy.png)" in md


def test_section_summary_uses_relative_path_to_course_images(tmp_path):
    course_dir = tmp_path / "curso"
    output_file = course_dir / "Tema 1" / "resumen_tema.md"
    image_path = course_dir / "imagenes" / "diagrama.png"
    course = Course(id="101", name="Curso")
    section = CourseSection(
        id="sec-1",
        section_number=1,
        name="Tema 1",
        summary_html='<img src="https://moodle.test/diagrama.png" alt="Diagrama">',
    )

    CourseMarkdownWriter.generate_section_summary(
        course,
        section,
        output_file,
        {"https://moodle.test/diagrama.png": image_path},
    )

    assert "![Diagrama](../imagenes/diagrama.png)" in output_file.read_text(encoding="utf-8")


def test_section_summary_links_to_local_downloaded_name(tmp_path):
    course_dir = tmp_path / "curso"
    output_file = course_dir / "Tema 1" / "resumen_tema.md"
    local_file = output_file.parent / "Presentacion.pdf"
    local_file.parent.mkdir(parents=True)
    local_file.write_bytes(b"ok")

    course = Course(id="101", name="Curso")
    section = CourseSection(
        id="sec-1",
        section_number=1,
        name="Tema 1",
        modules=[
            CourseModule(
                id="mod-1",
                mod_type="resource",
                name="Presentación",
                files=[
                    FileItem(
                        name="Presentación.pdf",
                        url="https://moodle.test/pluginfile.php/1/Presentaci%C3%B3n.pdf",
                        local_name="Presentacion.pdf",
                    )
                ],
            )
        ],
    )

    CourseMarkdownWriter.generate_section_summary(course, section, output_file)

    content = output_file.read_text(encoding="utf-8")
    assert "[`Presentación.pdf`](Presentacion.pdf)" in content
    assert "No descargado" not in content


def test_consolidated_file_links_are_relative_to_course(tmp_path):
    course_dir = tmp_path / "curso"
    output_file = course_dir / "notas_y_teoria_completa.md"
    local_file = course_dir / "Tema1" / "Presentacion.pdf"
    local_file.parent.mkdir(parents=True)
    local_file.write_bytes(b"ok")

    course = Course(id="101", name="Curso")
    section = CourseSection(
        id="sec-1",
        section_number=1,
        name="Tema1",
        modules=[
            CourseModule(
                id="mod-1",
                mod_type="resource",
                name="Presentación",
                files=[
                    FileItem(
                        name="Presentación.pdf",
                        url="https://moodle.test/pluginfile.php/1/Presentaci%C3%B3n.pdf",
                        local_name="Presentacion.pdf",
                    )
                ],
            )
        ],
    )

    CourseMarkdownWriter.generate_consolidated_markdown(course, [section], output_file)

    content = output_file.read_text(encoding="utf-8")
    assert "[`Presentación.pdf`](Tema1/Presentacion.pdf)" in content


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
