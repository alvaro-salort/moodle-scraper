"""
Parser de Moodle 4.x: Extracción de cursos, secciones, actividades, textos y recursos.
Utiliza BeautifulSoup4 para parsear estructuras DOM y la API AJAX de Moodle cuando esté disponible.
"""

import json
import re
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from urllib.parse import urljoin, parse_qs, urlparse
from bs4 import BeautifulSoup, Tag

from moodle_scraper.utils import sanitize_filename, make_absolute_url, Logger


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

    @property
    def folder_name(self) -> str:
        """Genera un nombre de carpeta limpio para la sección."""
        prefix = f"Tema_{self.section_number}_" if self.section_number > 0 else "Tema_0_General_"
        clean = sanitize_filename(self.name)
        # Si ya comienza con prefijo numérico similar, evitar redundancia
        if clean.lower().startswith("tema") or clean.lower().startswith("sección") or clean.lower().startswith("unidad"):
            return sanitize_filename(clean)
        return sanitize_filename(f"{prefix}{clean}")


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


class MoodleParser:
    """Colección de métodos para parsear el HTML y respuestas de Moodle 4.x."""

    @staticmethod
    def parse_courses_from_html(html: str, base_url: str) -> List[Course]:
        """
        Extrae la lista de cursos desde páginas HTML como my/courses.php, my/ o el menú principal.
        """
        soup = BeautifulSoup(html, "html.parser")
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
    def parse_course_sections(html: str, base_url: str) -> List[CourseSection]:
        """
        Parsea la vista principal de un curso (course/view.php?id=X)
        extrayendo todas las secciones, etiquetas, textos, páginas, recursos y enlaces.
        """
        soup = BeautifulSoup(html, "html.parser")
        sections: List[CourseSection] = []

        # Buscar contenedores de secciones en Moodle 4.x / 3.x
        # Moodle 4.x: li.course-section, div.course-section, li.section.main, ul.topics > li, ul.weeks > li
        section_elems = soup.find_all(
            ["li", "div", "section"],
            class_=re.compile(r"section\s+main|course-section|sectionname|topics|weeks")
        )

        # Si no encontró con la clase principal, buscar por IDs tipo section-0, section-1, etc.
        if not section_elems:
            section_elems = soup.find_all(["li", "div", "section"], id=re.compile(r"section-\d+"))

        # Si aún está vacío, usar el contenedor de contenido general
        if not section_elems:
            content_container = soup.find(class_=re.compile(r"course-content|region-main"))
            if content_container:
                section_elems = [content_container]

        seen_section_ids = set()
        sec_counter = 0

        for sec_node in section_elems:
            sec_id_attr = sec_node.get("id", "")
            
            # Identificar número de sección
            sec_num_match = re.search(r"section-(\d+)", sec_id_attr or "")
            if sec_num_match:
                section_num = int(sec_num_match.group(1))
            else:
                section_num = sec_counter
            
            # Evitar secciones duplicadas por anidamiento de selectores
            sec_key = f"{section_num}_{sec_id_attr}"
            if sec_key in seen_section_ids:
                continue
            seen_section_ids.add(sec_key)
            sec_counter += 1

            # 1. Extraer título de la sección
            title_elem = (
                sec_node.find(class_=re.compile(r"sectionname|section-title|coursesection-title"))
                or sec_node.find(["h3", "h4", "h2"], class_=re.compile(r"section-title|title"))
            )
            if title_elem:
                section_title = title_elem.get_text(" ", strip=True)
            else:
                section_title = "General" if section_num == 0 else f"Tema {section_num}"

            # Limpiar título
            section_title = re.sub(r'\s+', ' ', section_title).strip()

            # 2. Extraer resumen o descripción de la sección
            summary_elem = sec_node.find(class_=re.compile(r"summary|section-summary|summarytext"))
            summary_html = str(summary_elem) if summary_elem else ""
            summary_text = summary_elem.get_text("\n", strip=True) if summary_elem else ""

            section_obj = CourseSection(
                id=sec_id_attr or f"section-{section_num}",
                section_number=section_num,
                name=section_title,
                summary_html=summary_html,
                summary_text=summary_text,
                modules=[]
            )

            # 3. Extraer actividades y recursos dentro de la sección
            activities = sec_node.find_all(
                ["li", "div"],
                class_=re.compile(r"activity\s+|activity-item|activityinstance")
            )

            for act in activities:
                mod = MoodleParser._parse_activity_element(act, base_url, section_title)
                if mod:
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
            # Remover texto de accesibilidad ("Archivo", "Página", etc.)
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
                # Tomar la primera línea significativa como nombre
                first_line = [l.strip() for l in content_text.splitlines() if l.strip()]
                name = first_line[0][:60] if first_line else "Nota / Explicación"

        if not name and not content_text and not act_url:
            return None

        if not name:
            name = f"Recurso_{mod_type}_{mod_id or 'item'}"

        name = re.sub(r'\s+', ' ', name).strip()

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
        soup = BeautifulSoup(html, "html.parser")
        
        # En Moodle 4.x, el contenido suele estar en .box.py-3.generalbox o .page-content o #region-main
        content_box = (
            soup.find(class_=re.compile(r"page-content|generalbox"))
            or soup.find("div", role="main")
            or soup.find(id="region-main")
        )
        
        # Título de la página
        title_elem = soup.find(["h2", "h3"], class_=re.compile(r"page-title|title")) or soup.find("h2")
        title = title_elem.get_text(strip=True) if title_elem else ""

        if content_box:
            # Eliminar navegación interna o migas si están dentro
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
        También busca el botón o formulario para descargar el .ZIP completo.
        """
        soup = BeautifulSoup(html, "html.parser")
        files: List[FileItem] = []

        # 1. Comprobar si hay botón para descargar carpeta completa en .zip (download_folder.php)
        zip_form = soup.find("form", action=re.compile(r"download_folder\.php"))
        if zip_form:
            action_url = make_absolute_url(base_url, zip_form.get("action", ""))
            # Obtener parámetros del formulario
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

        # 2. Si no hay ZIP general, listar archivos individuales del árbol de la carpeta
        tree = soup.find(class_=re.compile(r"foldertree|box\s+generalbox"))
        if tree:
            for a_tag in tree.find_all("a", href=re.compile(r"pluginfile\.php")):
                file_url = make_absolute_url(base_url, a_tag.get("href", ""))
                file_name = a_tag.get_text(strip=True) or file_url.split("/")[-1].split("?")[0]
                
                # Obtener tamaño si está en el DOM
                size_hint = None
                size_span = a_tag.find_next("span", class_="filesize")
                if size_span:
                    size_hint = size_span.get_text(strip=True)

                files.append(FileItem(
                    name=file_name,
                    url=file_url,
                    size_hint=size_hint,
                    section_name=section_name,
                    source_module=module_name
                ))

        return files

    @staticmethod
    def parse_external_url(html: str) -> Optional[str]:
        """
        Extrae el enlace de destino real desde la vista /mod/url/view.php.
        """
        soup = BeautifulSoup(html, "html.parser")
        
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
