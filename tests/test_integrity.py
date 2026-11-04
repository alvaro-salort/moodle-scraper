"""
Pruebas de verificación de enlaces locales en los Markdown generados.
"""

from pathlib import Path

from moodle_scraper.integrity import check_directory, check_markdown_file, write_report


def test_check_markdown_file_detects_missing_local_references(tmp_path):
    markdown = tmp_path / "notas.md"
    markdown.write_text(
        "[archivo ok](existe.pdf)\n"
        "![imagen rota](imagenes/falta.png)\n"
        "[externo](https://ejemplo.com/x.pdf)\n"
        "[ancla](#seccion)\n",
        encoding="utf-8",
    )
    (tmp_path / "existe.pdf").write_bytes(b"ok")

    issues = check_markdown_file(markdown)

    assert len(issues) == 1
    assert issues[0].target == "imagenes/falta.png"
    assert issues[0].line_number == 2


def test_check_markdown_file_decodes_percent_encoded_targets(tmp_path):
    target = tmp_path / "Tema 1" / "Clase (1)" / "archivo (2).pdf"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"ok")

    markdown = tmp_path / "notas.md"
    markdown.write_text(
        "[archivo](Tema%201/Clase%20%281%29/archivo%20%282%29.pdf)\n",
        encoding="utf-8",
    )

    assert check_markdown_file(markdown) == []


def test_check_markdown_file_detects_legacy_backtick_references(tmp_path):
    markdown = tmp_path / "resumen_tema.md"
    markdown.write_text("- 📎 `Falta.pdf`\n", encoding="utf-8")

    issues = check_markdown_file(markdown)

    assert len(issues) == 1
    assert issues[0].target == "Falta.pdf"


def test_check_directory_ignores_failed_download_markers(tmp_path):
    markdown = tmp_path / "Tema 1" / "resumen_tema.md"
    markdown.parent.mkdir(parents=True)
    markdown.write_text("- ⚠ No descargado: `falta.pdf`\n", encoding="utf-8")

    assert check_directory(tmp_path) == []


def test_write_report_lists_broken_links(tmp_path):
    markdown = tmp_path / "notas.md"
    markdown.write_text("[falta](no-existe.pdf)\n", encoding="utf-8")

    issues = check_directory(tmp_path)
    report = write_report(tmp_path, issues)

    assert report.exists()
    content = report.read_text(encoding="utf-8")
    assert "Referencias rotas: 1" in content
    assert "no-existe.pdf" in content
