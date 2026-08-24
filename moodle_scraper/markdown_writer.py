"""
Formateador de Markdown para Moodle: Conversión de HTML a Markdown limpio y
generación de documentos consolidados de teoría y resúmenes por tema.
"""

import datetime
import re
from pathlib import Path
from typing import List, Optional
from bs4 import BeautifulSoup, NavigableString, Tag

from moodle_scraper.parser import Course, CourseSection, CourseModule, FileItem
from moodle_scraper.utils import Logger


class MarkdownFormatter:
    """Convierte fragmentos de HTML de Moodle a texto Markdown limpio y formateado."""

    @classmethod
    def html_to_markdown(cls, html_str: str) -> str:
        """Transforma una cadena HTML en Markdown legible."""
        if not html_str or not html_str.strip():
            return ""

        soup = BeautifulSoup(html_str, "html.parser")
        
        # Eliminar elementos no deseados
        for tag in soup(["script", "style", "meta", "noscript", "svg"]):
            tag.decompose()

        return cls._render_node(soup).strip()

    @classmethod
    def _render_node(cls, node) -> str:
        """Renderiza recursivamente nodos del DOM a sintaxis Markdown."""
        if isinstance(node, NavigableString):
            text = str(node)
            # Reemplazar múltiples espacios sin perder saltos
            return re.sub(r'[ \t\r\f\v]+', ' ', text)

        if not isinstance(node, Tag):
            return ""

        tag_name = node.name.lower()
        children_text = "".join(cls._render_node(child) for child in node.children)

        if tag_name in ["h1", "h2", "h3", "h4", "h5", "h6"]:
            level = int(tag_name[1])
            hashes = "#" * min(level + 1, 6)  # Nivel relativo
            clean_title = children_text.strip()
            return f"\n\n{hashes} {clean_title}\n\n" if clean_title else ""

        elif tag_name == "p":
            clean_p = children_text.strip()
            return f"\n\n{clean_p}\n\n" if clean_p else ""

        elif tag_name in ["strong", "b"]:
            t = children_text.strip()
            return f"**{t}**" if t else ""

        elif tag_name in ["em", "i"]:
            t = children_text.strip()
            return f"*{t}*" if t else ""

        elif tag_name == "u":
            t = children_text.strip()
            return f"<u>{t}</u>" if t else ""

        elif tag_name in ["s", "strike", "del"]:
            t = children_text.strip()
            return f"~~{t}~~" if t else ""

        elif tag_name == "code":
            t = children_text.strip()
            return f"`{t}`" if t else ""

        elif tag_name == "pre":
            t = node.get_text()
            return f"\n\n```\n{t.strip()}\n```\n\n"

        elif tag_name == "blockquote":
            lines = children_text.strip().splitlines()
            quoted = "\n".join(f"> {line}" for line in lines if line.strip())
            return f"\n\n{quoted}\n\n" if quoted else ""

        elif tag_name == "ul":
            items = []
            for li in node.find_all("li", recursive=False):
                li_text = cls._render_node(li).strip()
                if li_text:
                    items.append(f"- {li_text}")
            return "\n" + "\n".join(items) + "\n" if items else ""

        elif tag_name == "ol":
            items = []
            for i, li in enumerate(node.find_all("li", recursive=False), 1):
                li_text = cls._render_node(li).strip()
                if li_text:
                    items.append(f"{i}. {li_text}")
            return "\n" + "\n".join(items) + "\n" if items else ""

        elif tag_name == "li":
            return children_text.strip()

        elif tag_name == "a":
            href = node.get("href", "")
            text = children_text.strip() or href
            if href and not href.startswith("javascript:"):
                return f"[{text}]({href})"
            return text

        elif tag_name == "img":
            src = node.get("src", "")
            alt = node.get("alt", "imagen")
            if src:
                return f"![{alt}]({src})"
            return ""

        elif tag_name == "hr":
            return "\n\n---\n\n"

        elif tag_name == "br":
            return "  \n"

        elif tag_name == "table":
            return cls._render_table(node)

        # Contenedores neutros (div, span, section, article, etc.)
        return children_text

    @classmethod
    def _render_table(cls, table_tag: Tag) -> str:
        """Renderiza tablas HTML simples a Markdown."""
        rows = table_tag.find_all("tr")
        if not rows:
            return ""

        md_rows = []
        col_count = 0

        for r_idx, tr in enumerate(rows):
            cells = tr.find_all(["th", "td"])
            if not cells:
                continue
            col_count = max(col_count, len(cells))
            row_vals = [c.get_text(" ", strip=True).replace("|", "\\|") for c in cells]
            md_rows.append("| " + " | ".join(row_vals) + " |")

            # Encabezado separador después de la primera fila
            if r_idx == 0:
                sep = "| " + " | ".join(["---"] * len(cells)) + " |"
                md_rows.append(sep)

        return "\n\n" + "\n".join(md_rows) + "\n\n"


class CourseMarkdownWriter:
    """Escribe los archivos Markdown consolidados y resúmenes por tema."""

    @staticmethod
    def generate_consolidated_markdown(course: Course, sections: List[CourseSection], output_file: Path) -> None:
        """
        Genera notas_y_teoria_completa.md con todo el contenido textual,
        etiquetas y teoría explicativa organizada cronológicamente por secciones.
        """
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        lines = [
            f"# 📚 {course.name}",
            f"\n> **Moodle ITU UNCUYO** | *Documento generado automáticamente el {now}*",
            "\n---",
            "\n## 📑 Índice de Contenidos\n"
        ]

        # 1. Tabla de contenidos
        for idx, sec in enumerate(sections, 1):
            anchor = re.sub(r'[^a-zA-Z0-9_-]', '', sec.name.lower().replace(" ", "-"))
            lines.append(f"{idx}. [{sec.name}](#{anchor})")

        lines.append("\n---\n")

        # 2. Contenido detallado por sección
        for sec in sections:
            anchor = re.sub(r'[^a-zA-Z0-9_-]', '', sec.name.lower().replace(" ", "-"))
            lines.append(f"## <a id=\"{anchor}\"></a>{sec.name}\n")

            # Resumen o texto introductorio de la sección
            if sec.summary_html:
                sec_md = MarkdownFormatter.html_to_markdown(sec.summary_html)
                if sec_md:
                    lines.append(f"{sec_md}\n")
            elif sec.summary_text:
                lines.append(f"{sec.summary_text}\n")

            if not sec.modules:
                lines.append("*Esta sección no contiene actividades registradas.*\n")
                lines.append("---\n")
                continue

            for mod in sec.modules:
                CourseMarkdownWriter._append_module_to_lines(mod, lines)

            lines.append("\n---\n")

        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        Logger.text_saved(f"{output_file.name} ({output_file.parent.name})")

    @staticmethod
    def generate_section_summary(course: Course, section: CourseSection, output_file: Path) -> None:
        """
        Genera resumen_tema.md dentro de la carpeta específica del tema.
        """
        lines = [
            f"# 📖 {section.name}",
            f"\n> Curso: **{course.name}**",
            "\n---",
            "\n### 📝 Resumen y Explicación de la Unidad\n"
        ]

        if section.summary_html:
            sec_md = MarkdownFormatter.html_to_markdown(section.summary_html)
            lines.append(f"{sec_md}\n")
        elif section.summary_text:
            lines.append(f"{section.summary_text}\n")
        else:
            lines.append("*Sin descripción introductoria de sección.*\n")

        lines.append("### 📌 Contenidos y Actividades\n")

        for mod in section.modules:
            CourseMarkdownWriter._append_module_to_lines(mod, lines)

        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        Logger.text_saved(f"resumen_tema.md -> {output_file.parent.name}")

    @staticmethod
    def _append_module_to_lines(mod: CourseModule, lines: List[str]) -> None:
        """Añade un módulo específico al flujo de líneas Markdown."""
        icons = {
            "resource": "📄 [Archivo]",
            "folder": "📁 [Carpeta]",
            "page": "📑 [Página Teórica]",
            "label": "📝 [Nota/Explicación]",
            "url": "🔗 [Enlace Web]",
            "assign": "📋 [Tarea/Consigna]",
            "forum": "💬 [Foro/Debate]",
            "book": "📖 [Libro]",
            "quiz": "❓ [Cuestionario]",
            "other": "📌 [Actividad]"
        }
        type_badge = icons.get(mod.mod_type, "📌")

        lines.append(f"### {type_badge} {mod.name}\n")

        # Texto/HTML de etiquetas o contenido directo
        if mod.content_html:
            content_md = MarkdownFormatter.html_to_markdown(mod.content_html)
            if content_md:
                lines.append(f"{content_md}\n")
        elif mod.content_text:
            lines.append(f"{mod.content_text}\n")

        # Descripción del recurso
        if mod.description_html:
            desc_md = MarkdownFormatter.html_to_markdown(mod.description_html)
            if desc_md:
                lines.append(f"**Descripción:**\n{desc_md}\n")
        elif mod.description_text:
            lines.append(f"**Descripción:** {mod.description_text}\n")

        # Enlace externo si aplica
        if mod.external_url:
            lines.append(f"- 🌐 **Enlace externo:** [{mod.external_url}]({mod.external_url})\n")
        elif mod.url and mod.mod_type == "url":
            lines.append(f"- 🌐 **Enlace de Moodle:** [{mod.url}]({mod.url})\n")

        # Archivos adjuntos o contenidos
        if mod.files:
            lines.append("**Archivos asociados:**")
            for f in mod.files:
                size_str = f" ({f.size_hint})" if f.size_hint else ""
                lines.append(f"- 📎 `{f.name}`{size_str}")
            lines.append("")
