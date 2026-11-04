"""
Verificación de integridad de los enlaces locales generados en los Markdown.

Comprueba que cada enlace relativo (archivos e imágenes) apunte a un archivo
que realmente existe dentro del árbol de descargas.
"""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List
from urllib.parse import unquote, urlparse

_MARKDOWN_LINK_RE = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
_SKIP_MARKERS = ("no descargado",)


@dataclass(frozen=True)
class BrokenLink:
    """Representa una referencia local que no existe en disco."""

    markdown: Path
    target: str
    line_number: int

    def describe(self, root: Path) -> str:
        try:
            md_path = self.markdown.relative_to(root)
        except ValueError:
            md_path = self.markdown
        return f"{md_path}:{self.line_number} -> {self.target}"


def _is_external(target: str) -> bool:
    parsed = urlparse(target)
    return bool(parsed.scheme) or target.startswith(("#", "mailto:", "tel:"))


def check_markdown_file(markdown: Path) -> List[BrokenLink]:
    """Devuelve los enlaces locales rotos de un archivo Markdown."""
    if not markdown.exists() or markdown.suffix.lower() != ".md":
        return []

    issues: List[BrokenLink] = []
    text = markdown.read_text(encoding="utf-8", errors="replace")

    for line_number, line in enumerate(text.splitlines(), 1):
        if any(marker in line.lower() for marker in _SKIP_MARKERS):
            continue

        for match in _MARKDOWN_LINK_RE.finditer(line):
            target = match.group(1).strip()
            if not target or _is_external(target):
                continue

            local_target = unquote(target.split("#", 1)[0])
            if not local_target:
                continue

            resolved = (markdown.parent / local_target).resolve()
            if not resolved.exists():
                issues.append(BrokenLink(markdown, target, line_number))

    return issues


def check_directory(root: Path) -> List[BrokenLink]:
    """Recorre un árbol de descargas y devuelve todos los enlaces rotos."""
    root = Path(root)
    issues: List[BrokenLink] = []
    for markdown in sorted(root.rglob("*.md")):
        issues.extend(check_markdown_file(markdown))
    return issues


def write_report(root: Path, issues: Iterable[BrokenLink]) -> Path:
    """Escribe un reporte legible y devuelve su ruta."""
    root = Path(root)
    issues = list(issues)
    report_path = root / "verificacion_enlaces.txt"

    lines = [
        "Verificación de enlaces locales",
        "================================",
        f"Referencias rotas: {len(issues)}",
        "",
    ]
    lines.extend(issue.describe(root) for issue in issues)
    if not issues:
        lines.append("Todas las referencias locales existen.")

    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report_path
