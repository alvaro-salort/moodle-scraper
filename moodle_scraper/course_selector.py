"""
Selector de cursos para la CLI: resolución de argumentos, filtros y selecciones
interactivas sin acoplar la lógica de selección a la interfaz de usuario.
"""

from dataclasses import dataclass
from typing import List, Optional

from moodle_scraper.parser import Course


@dataclass(frozen=True)
class CourseSelection:
    """Intención de selección recibida desde una interfaz."""

    select_all: bool = False
    course_id: Optional[str] = None
    name_filter: Optional[str] = None

    @classmethod
    def from_args(cls, args: object | None) -> "CourseSelection":
        """Construye una selección desde un objeto de argumentos tipo argparse."""
        if args is None:
            return cls()
        return cls(
            select_all=bool(getattr(args, "all", False)),
            course_id=(str(args.course_id) if getattr(args, "course_id", None) else None),
            name_filter=getattr(args, "filter", None),
        )


class CourseSelector:
    """Resuelve selecciones de cursos sin depender de consola ni argparse."""

    def __init__(self, base_url: str):
        self.base_url = base_url

    def select_explicit(
        self,
        courses: List[Course],
        selection: CourseSelection,
    ) -> Optional[List[Course]]:
        """Resuelve flags explícitos; None indica que debe usarse modo interactivo."""
        if selection.select_all:
            return courses

        if selection.course_id:
            matched = [course for course in courses if course.id == selection.course_id]
            if matched:
                return matched
            return [Course(
                id=selection.course_id,
                name=f"Curso_{selection.course_id}",
                url=f"{self.base_url}course/view.php?id={selection.course_id}",
            )]

        if selection.name_filter:
            pattern = selection.name_filter.lower()
            matched = [course for course in courses if pattern in course.name.lower()]
            if matched:
                return matched

        return None

    @staticmethod
    def parse_indices(input_str: str, max_value: int) -> List[int]:
        """Convierte selecciones como '1,2,5' y '1-4' en índices válidos."""
        indices = set()
        for part in input_str.split(","):
            part = part.strip()
            if "-" in part:
                subparts = part.split("-")
                if len(subparts) == 2 and all(value.isdigit() for value in subparts):
                    start, end = (int(value) for value in subparts)
                    indices.update(
                        n for n in range(start, end + 1)
                        if 1 <= n <= max_value
                    )
            elif part.isdigit():
                value = int(part)
                if 1 <= value <= max_value:
                    indices.add(value)
        return sorted(indices)

    def select_interactive_choice(
        self,
        courses: List[Course],
        choice: str,
    ) -> Optional[List[Course]]:
        """Resuelve una respuesta del menú; None indica una respuesta inválida."""
        normalized_choice = choice.strip().lower()
        if normalized_choice in ("q", "quit", "exit", "salir"):
            return []
        if normalized_choice in ("a", "all", "todos", "*"):
            return courses

        selected = self.parse_indices(normalized_choice, len(courses))
        if selected:
            return [courses[index - 1] for index in selected]
        return None
