"""
Parser de Moodle 4.x: Extracción de cursos, secciones, actividades, textos y recursos.
Utiliza BeautifulSoup4 para parsear estructuras DOM y la API AJAX de Moodle cuando esté disponible.
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
from urllib.parse import urljoin, parse_qs, urlparse
from bs4 import BeautifulSoup, Tag

from moodle_scraper.utils import sanitize_filename, make_absolute_url, Logger, format_bytes


@dataclass
class FileItem:
    """Representa un archivo descargable."""
    name: str
    url: str
    size_hint: Optional[str] = None
    section_name: str = ""
    source_module: str = ""


@dataclass
class CourseModule:
    """Representa una actividad o recurso dentro de una sección de Moodle."""
    id: str
    mod_type: str  # 'resource', 'folder', 'page', 'url', 'label', 'assign', 'forum', 'book', 'other'
    name: str
    url: Optional[str] = None
    description_html: str = ""
    description_text: str = ""
    content_html: str = ""
    content_text: str = ""
    external_url: Optional[str] = None
    files: List[FileItem] = field(default_factory=list)


@dataclass
class CourseSection:
    """Representa una sección, tema o semana de un curso."""
    id: str
    section_number: int
    name: str
    summary_html: str = ""
    summary_text: str = ""
    modules: List[CourseModule] = field(default_factory=list)
    parent_name: Optional[str] = None

    @property
    def folder_name(self) -> str:
        """Nombre limpio de la carpeta de la sección."""
        clean = sanitize_filename(self.name)
        if not clean or clean.lower() in ["sección", "tema", "section"]:
            return f"Tema_{self.section_number}"
        return clean

    @property
    def relative_folder_path(self) -> Path:
        """Genera la ruta de carpetas relativa respetando la jerarquía padre/hijo (ej: Modulo 1/Clase 2)."""
        clean_name = self.folder_name
        if self.parent_name:
            clean_parent = sanitize_filename(self.parent_name)
            if clean_parent and clean_parent.lower() != clean_name.lower():
                return Path(clean_parent) / clean_name
        return Path(clean_name)


@dataclass
class OnetopicTabInfo:
    """Información de navegación de una pestaña de Onetopic / Árbol de pestañas."""
    section_number: int
    title: str
    url: str
    parent_name: Optional[str] = None
    level: int = 0


@dataclass
class Course:
    """Representa un curso de Moodle."""
    id: str
    name: str
    shortname: str = ""
    url: str = ""

    @property
    def sanitized_name(self) -> str:
        """Nombre normalizado para la carpeta local en el sistema de archivos."""
        return sanitize_filename(self.name)


def _create_soup(html: str) -> BeautifulSoup:
    """Crea una instancia de BeautifulSoup utilizando lxml (más rápido y tolerante) con fallback a html.parser."""
    try:
        return BeautifulSoup(html, "lxml")
    except Exception:
        return BeautifulSoup(html, "html.parser")


class MoodleParser:
    """Colección de métodos para parsear el HTML y respuestas de Moodle 4.x."""

    @staticmethod
    def parse_courses_from_html(html: str, base_url: str) -> List[Course]:
        """
        Extrae la lista de cursos desde páginas HTML como my/courses.php, my/ o el menú principal.
        """
        soup = _create_soup(html)
        courses: Dict[str, Course] = {}

        # 1. Buscar enlaces con patrón /course/view.php?id=X
        for a_tag in soup.find_all("a", href=re.compile(r"course/view\.php\?id=\d+")):
            href = a_tag.get("href", "")
            full_url = make_absolute_url(base_url, href)
            parsed = urlparse(full_url)
            params = parse_qs(parsed.query)
            course_id = params.get("id", [""])[0]
            
            if not course_id or course_id == "1":  # ID 1 suele ser la portada del sitio
                continue

            # Obtener el nombre del curso
            title = a_tag.get_text(strip=True)
            if not title:
                # Buscar en elementos hijos o atributos title/aria-label
                title = a_tag.get("title", "") or a_tag.get("aria-label", "")
                if not title and a_tag.parent:
                    title = a_tag.parent.get_text(strip=True)

            # Limpiar textos de badges tipo "Nuevo", "Curso", etc.
            title = re.sub(r'^(Curso|Course)\s*:\s*', '', title, flags=re.IGNORECASE)
            title = re.sub(r'\s+', ' ', title).strip()

            if title and len(title) > 2 and course_id not in courses:
                courses[course_id] = Course(
                    id=course_id,
                    name=title,
                    url=full_url
                )

        # 2. Buscar tarjetas de curso en Moodle 4.x (.dashboard-card, .coursebox)
        for card in soup.find_all(class_=re.compile(r"dashboard-card|coursebox")):
            link = card.find("a", href=re.compile(r"course/view\.php\?id=\d+"))
            if link:
                href = link.get("href", "")
                full_url = make_absolute_url(base_url, href)
                course_id = parse_qs(urlparse(full_url).query).get("id", [""])[0]
                
                # Nombre en la tarjeta
                name_elem = card.find(class_=re.compile(r"coursename|course-title|coursename-text")) or link
                name = name_elem.get_text(strip=True)
                
                if course_id and name and course_id not in courses:
                    courses[course_id] = Course(
                        id=course_id,
                        name=name,
                        url=full_url
                    )

        return list(courses.values())

    @staticmethod
    def parse_courses_from_ajax(json_data: List[Dict[str, Any]], base_url: str) -> List[Course]:
        """
        Extrae cursos desde la respuesta JSON de lib/ajax/service.php
        (core_course_get_enrolled_courses_by_timeline_classification)
        """
        courses = []
        for item in json_data:
            # La respuesta de Moodle AJAX suele ser una lista de respuestas por método
            data = item.get("data", {}) if isinstance(item, dict) else {}
            course_list = data.get("courses", [])
            
            for c in course_list:
                cid = str(c.get("id", ""))
                fullname = c.get("fullname", "") or c.get("displayname", "") or c.get("shortname", "")
                view_url = c.get("viewurl", "") or f"course/view.php?id={cid}"
                full_url = make_absolute_url(base_url, view_url)
                
                if cid and fullname:
                    courses.append(Course(
                        id=cid,
                        name=fullname,
                        shortname=c.get("shortname", ""),
                        url=full_url
                    ))
        return courses

    @staticmethod
    def parse_course_contents_from_ajax(json_data: Any, base_url: str) -> List[CourseSection]:
        """
        Extrae la estructura completa de secciones y módulos desde el endpoint AJAX de Moodle:
        core_course_get_contents (lib/ajax/service.php).
        """
        sections: List[CourseSection] = []
        raw_sections = []

        if isinstance(json_data, list):
            for item in json_data:
                if isinstance(item, dict) and "data" in item:
                    inner = item.get("data")
                    if isinstance(inner, list):
                        raw_sections = inner
                        break
                elif isinstance(item, dict) and ("modules" in item or "section" in item):
                    raw_sections = json_data
                    break
        elif isinstance(json_data, dict):
            raw_sections = json_data.get("data", [])

        for sec in raw_sections:
            sec_id = str(sec.get("id", ""))
            sec_num = int(sec.get("section", 0))
            sec_name = sec.get("name", "") or f"Tema {sec_num}"
            summary = sec.get("summary", "") or ""
            
            clean_title = re.sub(r'<[^>]+>', '', sec_name).strip() or f"Tema {sec_num}"

            modules: List[CourseModule] = []
            for m in sec.get("modules", []):
                mod_id = str(m.get("id", ""))
                mod_name = m.get("name", "") or f"Actividad_{mod_id}"
                # Limpiar texto HTML en nombre del módulo
                clean_mod_name = re.sub(r'<[^>]+>', '', mod_name).strip()
                mod_type = m.get("modname", "other")
                mod_url = m.get("url") or ""
                if mod_url:
                    mod_url = make_absolute_url(base_url, mod_url)
                
                desc = m.get("description", "") or ""
                clean_desc = re.sub(r'<[^>]+>', '', desc).strip()

                files: List[FileItem] = []
                for content_file in m.get("contents", []):
                    f_url = content_file.get("fileurl") or ""
                    if f_url:
                        f_url = make_absolute_url(base_url, f_url)
                        f_name = content_file.get("filename") or f_url.split("/")[-1].split("?")[0]
                        f_size = content_file.get("filesize")
                        size_str = format_bytes(f_size) if f_size else None
                        
                        files.append(FileItem(
                            name=f_name,
                            url=f_url,
                            size_hint=size_str,
                            section_name=clean_title,
                            source_module=clean_mod_name
                        ))

                modules.append(CourseModule(
                    id=mod_id,
                    mod_type=mod_type,
                    name=clean_mod_name,
                    url=mod_url if mod_url else None,
                    description_html=desc,
                    description_text=clean_desc,
                    files=files
                ))

            sections.append(CourseSection(
                id=sec_id or f"section-{sec_num}",
                section_number=sec_num,
                name=clean_title,
                summary_html=summary,
                summary_text=re.sub(r'<[^>]+>', '', summary).strip(),
                modules=modules
            ))

        return sections

    @staticmethod
    def extract_section_links_from_html(html: str, base_url: str, course_id: str) -> List[Tuple[int, str, str]]:
        """
        Detecta enlaces a pestañas o sub-secciones en formatos multi-página (onetopic, tabs, etc.).
        Retorna lista de tuplas (numero_seccion, nombre_seccion, url_absoluta).
        """
        soup = _create_soup(html)
        links: List[Tuple[int, str, str]] = []
        seen_urls = set()

        # Buscar enlaces con parámetro section=\d+ o sectionid=\d+ o tabs de onetopic
        pattern = re.compile(rf"course/view\.php\?.*id={re.escape(str(course_id))}.*(?:section|sectionid)=\d+", re.IGNORECASE)
        for a_tag in soup.find_all("a", href=pattern):
            href = a_tag.get("href", "")
            full_url = make_absolute_url(base_url, href)
            if full_url in seen_urls:
                continue
            seen_urls.add(full_url)
            
            parsed = urlparse(full_url)
            params = parse_qs(parsed.query)
            sec_num = 0
            if "section" in params:
                try:
                    sec_num = int(params["section"][0])
                except ValueError:
                    pass

            sec_title = a_tag.get_text(" ", strip=True)
            sec_title = re.sub(r'\s+', ' ', sec_title).strip()
            links.append((sec_num, sec_title, full_url))

        # Ordenar por número de sección
        links.sort(key=lambda x: x[0])
        return links

    @staticmethod
    def is_onetopic_course(html: str) -> bool:
        """Determina si un curso utiliza el formato de pestañas / árbol de pestañas onetopic."""
        soup = _create_soup(html)
        if soup.find(id="tabs-tree-start"):
            return True
        if soup.find(class_=re.compile(r"onetopic|format-onetopic|format_onetopic")):
            return True
        if soup.find("li", class_=re.compile(r"tab_position_\d+|tab_level_\d+|subtopic")):
            return True
        return False

    @staticmethod
    def extract_onetopic_level_0_tabs(html: str, base_url: str, course_id: str) -> List[Dict[str, Any]]:
        """Extrae pestañas de nivel raíz (nivel 0) en formato onetopic."""
        soup = _create_soup(html)
        tabs: List[Dict[str, Any]] = []
        tabs_container = soup.find(class_=re.compile(r"onetopic|tabs-tree")) or soup

        for li in tabs_container.find_all("li", class_=re.compile(r"tab_level_0|nav-item")):
            classes = li.get("class", [])
            if "tab_level_0" not in classes and "tab_position" not in " ".join(classes):
                continue
            a = li.find("a")
            if not a or not a.get("href"):
                continue

            is_disabled = "disabled" in classes or "dimmed" in classes
            has_childs = "haschilds" in classes

            for hide in a.find_all(class_=re.compile(r"accesshide|sr-only")):
                hide.decompose()
            tab_title = re.sub(r'\s+', ' ', a.get_text(" ", strip=True)).strip()

            full_url = make_absolute_url(base_url, a.get("href"))
            parsed = urlparse(full_url)
            params = parse_qs(parsed.query)

            cid = params.get("id", [""])[0]
            if cid and str(cid) != str(course_id):
                continue

            sec_num = 0
            if "section" in params:
                try:
                    sec_num = int(params["section"][0])
                except ValueError:
                    pass

            tabs.append({
                "section": sec_num,
                "title": tab_title,
                "url": full_url,
                "haschilds": has_childs,
                "disabled": is_disabled
            })
        return tabs

    @staticmethod
    def extract_onetopic_level_1_tabs(html: str, base_url: str, parent_title: str) -> List[OnetopicTabInfo]:
        """Extrae subpestañas hijas (nivel 1 / subtopics) de una pestaña padre en onetopic."""
        soup = _create_soup(html)
        sub_tabs: List[OnetopicTabInfo] = []
        tabs_container = soup.find(class_=re.compile(r"onetopic|tabs-tree")) or soup

        for li in tabs_container.find_all("li", class_=re.compile(r"tab_level_1|subtopic")):
            classes = li.get("class", [])
            is_disabled = "disabled" in classes or "dimmed" in classes
            a = li.find("a")
            if not a or not a.get("href"):
                continue

            for hide in a.find_all(class_=re.compile(r"accesshide|sr-only")):
                hide.decompose()
            tab_title = re.sub(r'\s+', ' ', a.get_text(" ", strip=True)).strip()

            full_url = make_absolute_url(base_url, a.get("href"))
            parsed = urlparse(full_url)
            params = parse_qs(parsed.query)
            sec_num = 0
            if "section" in params:
                try:
                    sec_num = int(params["section"][0])
                except ValueError:
                    pass

            if not is_disabled:
                sub_tabs.append(OnetopicTabInfo(
                    section_number=sec_num,
                    title=tab_title,
                    url=full_url,
                    parent_name=parent_title,
                    level=1
                ))
        return sub_tabs

    @staticmethod
    def parse_course_sections(
        html: str,
        base_url: str,
        target_section_number: Optional[int] = None,
        section_title: Optional[str] = None,
        parent_name: Optional[str] = None
    ) -> List[CourseSection]:
        """
        Parsea la vista de un curso extrayendo secciones, etiquetas, textos, páginas, recursos y enlaces.
        Si se especifica target_section_number, extrae exclusivamente el contenido de esa sección específica.
        """
        soup = _create_soup(html)
        sections: List[CourseSection] = []

        # Caso específico: Se solicita extraer una sección puntual (como en onetopic o páginas individuales)
        if target_section_number is not None:
            sec_node = soup.find(["li", "div", "section"], id=f"section-{target_section_number}")
            if not sec_node:
                # Si no se encuentra por id exacto, buscar contenedor de sección principal
                candidates = soup.find_all(
                    ["li", "div", "section"],
                    class_=re.compile(r"\bsection\s+main\b|\bcourse-section\b|\bsection\b")
                )
                for cand in candidates:
                    cand_id = cand.get("id", "")
                    if f"section-{target_section_number}" in cand_id or str(target_section_number) in cand_id:
                        sec_node = cand
                        break
                if not sec_node and candidates:
                    sec_node = candidates[0]

            if not sec_node:
                sec_node = soup.find(class_=re.compile(r"course-content|region-main")) or soup

            # Determinar el nombre final de la sección
            final_title = section_title
            if not final_title:
                title_elem = (
                    sec_node.find(class_=re.compile(r"sectionname|section-title|coursesection-title"))
                    or sec_node.find(["h3", "h4", "h2"], class_=re.compile(r"section-title|title"))
                )
                if title_elem:
                    final_title = title_elem.get_text(" ", strip=True)
                else:
                    # Intentar desde el título de la página
                    if soup.title and soup.title.string:
                        page_title = soup.title.string
                        match_title = re.search(r"Tema:\s*([^|]+)", page_title)
                        if match_title:
                            final_title = match_title.group(1).strip()
            if not final_title:
                final_title = "General" if target_section_number == 0 else f"Tema {target_section_number}"

            final_title = re.sub(r'\s+', ' ', final_title).strip()

            summary_elem = sec_node.find(class_=re.compile(r"summary|section-summary|summarytext"))
            summary_html = str(summary_elem) if summary_elem else ""
            summary_text = summary_elem.get_text("\n", strip=True) if summary_elem else ""

            section_obj = CourseSection(
                id=f"section-{target_section_number}",
                section_number=target_section_number,
                name=final_title,
                summary_html=summary_html,
                summary_text=summary_text,
                modules=[],
                parent_name=parent_name
            )

            raw_activities = sec_node.find_all(
                ["li", "div"],
                class_=re.compile(r"\bactivity\s+|\bactivity\b|\bactivity-item\b|\bmodtype_\w+")
            )

            activities = []
            for act in raw_activities:
                if not any(parent in raw_activities and parent != act for parent in act.parents):
                    activities.append(act)

            seen_mod_keys = set()
            for act in activities:
                mod = MoodleParser._parse_activity_element(act, base_url, final_title)
                if mod:
                    mod_key = mod.url or mod.id or mod.name
                    if mod_key in seen_mod_keys:
                        continue
                    seen_mod_keys.add(mod_key)
                    section_obj.modules.append(mod)

            return [section_obj]

        # Caso general: Extraer todas las secciones presentes en la página HTML
        candidates = soup.find_all(
            ["li", "div", "section"],
            class_=re.compile(r"\bsection\s+main\b|\bcourse-section\b|\bsection\b")
        )

        section_elems = []
        for cand in candidates:
            cand_classes = cand.get("class", [])
            if any(c in ["sectionname", "summary", "section-summary", "activity", "activityinstance", "contentwithoutlink"] for c in cand_classes):
                continue
            if not any(parent in candidates and parent != cand for parent in cand.parents):
                section_elems.append(cand)

        if not section_elems:
            candidates_id = soup.find_all(["li", "div", "section"], id=re.compile(r"^section-\d+$"))
            for cand in candidates_id:
                if not any(parent in candidates_id and parent != cand for parent in cand.parents):
                    section_elems.append(cand)

        if not section_elems:
            content_container = soup.find(class_=re.compile(r"course-content|region-main"))
            if content_container:
                section_elems = [content_container]

        seen_section_ids = set()
        sec_counter = 0

        for sec_node in section_elems:
            sec_id_attr = sec_node.get("id", "")
            sec_num_match = re.search(r"section-(\d+)", sec_id_attr or "")
            if sec_num_match:
                section_num = int(sec_num_match.group(1))
            else:
                section_num = sec_counter
            
            sec_key = f"{section_num}_{sec_id_attr}"
            if sec_key in seen_section_ids:
                continue
            seen_section_ids.add(sec_key)
            sec_counter += 1

            title_elem = (
                sec_node.find(class_=re.compile(r"sectionname|section-title|coursesection-title"))
                or sec_node.find(["h3", "h4", "h2"], class_=re.compile(r"section-title|title"))
            )
            if title_elem:
                sec_title = title_elem.get_text(" ", strip=True)
            else:
                sec_title = "General" if section_num == 0 else f"Tema {section_num}"

            sec_title = re.sub(r'\s+', ' ', sec_title).strip()

            summary_elem = sec_node.find(class_=re.compile(r"summary|section-summary|summarytext"))
            summary_html = str(summary_elem) if summary_elem else ""
            summary_text = summary_elem.get_text("\n", strip=True) if summary_elem else ""

            section_obj = CourseSection(
                id=sec_id_attr or f"section-{section_num}",
                section_number=section_num,
                name=sec_title,
                summary_html=summary_html,
                summary_text=summary_text,
                modules=[],
                parent_name=parent_name
            )

            raw_activities = sec_node.find_all(
                ["li", "div"],
                class_=re.compile(r"\bactivity\s+|\bactivity\b|\bactivity-item\b|\bmodtype_\w+")
            )

            activities = []
            for act in raw_activities:
                if not any(parent in raw_activities and parent != act for parent in act.parents):
                    activities.append(act)

            seen_mod_keys = set()
            for act in activities:
                mod = MoodleParser._parse_activity_element(act, base_url, sec_title)
                if mod:
                    mod_key = mod.url or mod.id or mod.name
                    if mod_key in seen_mod_keys:
                        continue
                    seen_mod_keys.add(mod_key)
                    section_obj.modules.append(mod)

            sections.append(section_obj)

        return sections

    @staticmethod
    def _parse_activity_element(elem: Tag, base_url: str, section_name: str) -> Optional[CourseModule]:
        """Parsea un elemento DOM de actividad/recurso individual de Moodle."""
        elem_classes = " ".join(elem.get("class", []))
        mod_id = elem.get("id", "")
        
        # Determinar el tipo de módulo desde las clases de CSS o enlaces
        mod_type = "other"
        for t in ["resource", "folder", "page", "url", "label", "assign", "forum", "book", "quiz", "glossary"]:
            if f"modtype_{t}" in elem_classes or f"type_{t}" in elem_classes or f"/{t}/" in str(elem):
                mod_type = t
                break

        # Enlace principal de la actividad
        link = elem.find("a", href=re.compile(r"mod/\w+/view\.php\?id=\d+"))
        act_url = make_absolute_url(base_url, link.get("href", "")) if link else None
        
        # Si no había mod_type por clase, deducir de la URL
        if act_url and mod_type == "other":
            match = re.search(r"mod/(\w+)/view\.php", act_url)
            if match:
                mod_type = match.group(1)

        # Nombre de la actividad
        name = ""
        name_elem = (
            elem.find(class_=re.compile(r"instancename|activityname|activity-item-title"))
            or link
        )
        if name_elem:
            # Remover texto de accesibilidad ("Archivo", "Página", "Tarea", etc.)
            for hide in name_elem.find_all(class_=re.compile(r"accesshide|sr-only")):
                hide.decompose()
            name = name_elem.get_text(" ", strip=True)

        # Descripción o texto introductorio de la actividad
        desc_elem = elem.find(class_=re.compile(r"contentafterlink|activity-description|description|contentwithoutlink"))
        desc_html = str(desc_elem) if desc_elem else ""
        desc_text = desc_elem.get_text("\n", strip=True) if desc_elem else ""

        # Manejo especial para mod_label (Etiquetas de texto puro o explicaciones)
        content_html = ""
        content_text = ""
        if mod_type == "label" or not act_url:
            label_content = (
                elem.find(class_=re.compile(r"contentwithoutlink|mod-indent-outer|activity-description"))
                or elem
            )
            content_html = str(label_content)
            content_text = label_content.get_text("\n", strip=True)
            if not name:
                first_line = [l.strip() for l in content_text.splitlines() if l.strip()]
                name = first_line[0][:60] if first_line else "Nota / Explicación"

        if not name and not content_text and not act_url:
            return None

        if not name:
            name = f"Recurso_{mod_type}_{mod_id or 'item'}"

        name = re.sub(r'\s+', ' ', name).strip()
        # Limpiar sufijos residuales de tipo si quedaron pegados
        name = re.sub(r'\s+Tarea$', '', name, flags=re.IGNORECASE)
        name = re.sub(r'\s+Archivo$', '', name, flags=re.IGNORECASE)
        name = re.sub(r'\s+Carpeta$', '', name, flags=re.IGNORECASE)
        name = re.sub(r'\s+Página$', '', name, flags=re.IGNORECASE)
        name = re.sub(r'\s+URL$', '', name, flags=re.IGNORECASE)

        files: List[FileItem] = []

        # Buscar enlaces directos a archivos (ej: pluginfile.php) dentro del elemento
        for file_link in elem.find_all("a", href=re.compile(r"pluginfile\.php")):
            f_url = make_absolute_url(base_url, file_link.get("href", ""))
            f_name = file_link.get_text(strip=True) or f_url.split("/")[-1]
            files.append(FileItem(
                name=f_name,
                url=f_url,
                section_name=section_name,
                source_module=name
            ))

        return CourseModule(
            id=mod_id,
            mod_type=mod_type,
            name=name,
            url=act_url,
            description_html=desc_html,
            description_text=desc_text,
            content_html=content_html,
            content_text=content_text,
            files=files
        )

    @staticmethod
    def parse_page_content(html: str) -> Dict[str, str]:
        """
        Extrae el contenido textual y HTML de un recurso tipo 'Página' (/mod/page/view.php).
        """
        soup = _create_soup(html)
        content_box = (
            soup.find(class_=re.compile(r"page-content|generalbox"))
            or soup.find("div", role="main")
            or soup.find(id="region-main")
        )
        title_elem = soup.find(["h2", "h3"], class_=re.compile(r"page-title|title")) or soup.find("h2")
        title = title_elem.get_text(strip=True) if title_elem else ""

        if content_box:
            for nav in content_box.find_all(class_=re.compile(r"activity-navigation|breadcrumb|modified")):
                nav.decompose()
            return {
                "title": title,
                "html": str(content_box),
                "text": content_box.get_text("\n", strip=True)
            }
        return {"title": title, "html": "", "text": ""}

    @staticmethod
    def parse_folder_files(html: str, base_url: str, section_name: str, module_name: str) -> List[FileItem]:
        """
        Extrae los archivos contenidos dentro de una carpeta (/mod/folder/view.php).
        Extrae todos los archivos individuales (pluginfile.php) y utiliza el ZIP sólo como respaldo.
        """
        soup = _create_soup(html)
        files: List[FileItem] = []

        # 1. Extraer archivos individuales dentro del árbol de la carpeta
        tree = (
            soup.find(class_=re.compile(r"foldertree|generalbox"))
            or soup.find("div", role="main")
            or soup.find(id="region-main")
            or soup
        )
        for a_tag in tree.find_all("a", href=re.compile(r"pluginfile\.php")):
            href = a_tag.get("href", "")
            file_url = make_absolute_url(base_url, href)
            file_name = a_tag.get_text(strip=True)
            if not file_name or "." not in file_name:
                file_name = file_url.split("/")[-1].split("?")[0]
            file_name = re.sub(r'\s+', ' ', file_name).strip()

            size_hint = None
            size_span = a_tag.find_next("span", class_=re.compile(r"filesize"))
            if size_span:
                size_hint = size_span.get_text(strip=True)

            if not any(f.url == file_url for f in files):
                files.append(FileItem(
                    name=file_name,
                    url=file_url,
                    size_hint=size_hint,
                    section_name=section_name,
                    source_module=module_name
                ))

        # 2. Si no se encontraron archivos individuales, buscar formulario/botón ZIP
        if not files:
            zip_form = soup.find("form", action=re.compile(r"download_folder\.php"))
            if zip_form:
                action_url = make_absolute_url(base_url, zip_form.get("action", ""))
                inputs = {inp.get("name"): inp.get("value", "") for inp in zip_form.find_all("input") if inp.get("name")}
                query_str = "&".join(f"{k}={v}" for k, v in inputs.items())
                zip_url = f"{action_url}?{query_str}" if query_str else action_url

                files.append(FileItem(
                    name=f"{sanitize_filename(module_name)}.zip",
                    url=zip_url,
                    section_name=section_name,
                    source_module=module_name
                ))

        return files

    @staticmethod
    def parse_external_url(html: str) -> Optional[str]:
        """
        Extrae el enlace de destino real desde la vista /mod/url/view.php.
        """
        soup = _create_soup(html)
        
        # Buscar enlace en workaround o botón 'haga clic aquí'
        url_div = soup.find(class_=re.compile(r"urlworkaround"))
        if url_div:
            a_tag = url_div.find("a")
            if a_tag and a_tag.get("href"):
                return a_tag.get("href")

        main_box = soup.find("div", role="main") or soup.find(id="region-main")
        if main_box:
            for a in main_box.find_all("a", href=re.compile(r"^https?://")):
                href = a.get("href")
                if "moodle" not in href and "logout" not in href and "course" not in href:
                    return href

        return None
