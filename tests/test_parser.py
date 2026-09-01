"""
Pruebas unitarias para el parser de Moodle 4.x (HTML, AJAX, cursos, secciones y actividades).
"""

from moodle_scraper.parser import MoodleParser


def test_parse_courses_from_html():
    html = """
    <html>
        <body>
            <div class="dashboard-card">
                <a class="coursename" href="https://aulas.itu.uncu.edu.ar/itu/course/view.php?id=101">
                    2025B - Álgebra y Estadística - Junin/DS
                </a>
            </div>
            <div class="coursebox">
                <a href="/itu/course/view.php?id=102">
                    2025B - Arquitectura de Hardware Computacional - Junin/DS
                </a>
            </div>
            <!-- Ignorar portada id=1 -->
            <a href="https://aulas.itu.uncu.edu.ar/itu/course/view.php?id=1">Página Principal</a>
        </body>
    </html>
    """
    base_url = "https://aulas.itu.uncu.edu.ar/itu/"
    courses = MoodleParser.parse_courses_from_html(html, base_url)

    assert len(courses) == 2
    c_ids = [c.id for c in courses]
    assert "101" in c_ids
    assert "102" in c_ids
    assert "1" not in c_ids


def test_parse_courses_from_ajax():
    ajax_response = [{
        "data": {
            "courses": [
                {
                    "id": 201,
                    "fullname": "2025B - Base de Datos Relacionales - Junin/DS",
                    "shortname": "BDR-2025",
                    "viewurl": "https://aulas.itu.uncu.edu.ar/itu/course/view.php?id=201"
                },
                {
                    "id": 202,
                    "fullname": "2025B - Programación Orientada a Objetos - JNN/DS",
                    "shortname": "POO-2025",
                    "viewurl": "https://aulas.itu.uncu.edu.ar/itu/course/view.php?id=202"
                }
            ]
        }
    }]
    base_url = "https://aulas.itu.uncu.edu.ar/itu/"
    courses = MoodleParser.parse_courses_from_ajax(ajax_response, base_url)

    assert len(courses) == 2
    assert courses[0].id == "201"
    assert courses[0].name == "2025B - Base de Datos Relacionales - Junin/DS"
    assert courses[1].id == "202"
    assert courses[1].name == "2025B - Programación Orientada a Objetos - JNN/DS"


def test_parse_course_sections_and_modules():
    html = """
    <div class="course-content">
        <li id="section-0" class="section main">
            <div class="sectionname">Información General</div>
            <div class="summary">
                <p>Bienvenidos a la materia. Aquí encontrarán el programa.</p>
            </div>
            <ul class="section img-text">
                <li class="activity modtype_label" id="module-1">
                    <div class="contentwithoutlink">
                        <p><strong>Aviso Importante:</strong> Las clases inician el lunes.</p>
                    </div>
                </li>
                <li class="activity modtype_resource" id="module-2">
                    <div class="activityinstance">
                        <a href="https://aulas.itu.uncu.edu.ar/itu/mod/resource/view.php?id=500">
                            <span class="instancename">Programa_de_la_Materia.pdf <span class="accesshide">Archivo</span></span>
                        </a>
                    </div>
                </li>
            </ul>
        </li>
        <li id="section-1" class="section main">
            <div class="sectionname">Tema 1: Arquitectura y Modelado</div>
            <ul class="section img-text">
                <li class="activity modtype_page" id="module-3">
                    <div class="activityinstance">
                        <a href="https://aulas.itu.uncu.edu.ar/itu/mod/page/view.php?id=501">
                            <span class="instancename">Teoría - Conceptos Fundamentales</span>
                        </a>
                    </div>
                </li>
                <li class="activity modtype_url" id="module-4">
                    <div class="activityinstance">
                        <a href="https://aulas.itu.uncu.edu.ar/itu/mod/url/view.php?id=502">
                            <span class="instancename">Documentación Oficial Python</span>
                        </a>
                    </div>
                    <div class="contentafterlink">Enlace oficial a python.org</div>
                </li>
            </ul>
        </li>
    </div>
    """
    base_url = "https://aulas.itu.uncu.edu.ar/itu/"
    sections = MoodleParser.parse_course_sections(html, base_url)

    assert len(sections) == 2

    sec0 = sections[0]
    assert sec0.section_number == 0
    assert "Información General" in sec0.name
    assert len(sec0.modules) == 2
    assert sec0.modules[0].mod_type == "label"
    assert "Aviso Importante" in sec0.modules[0].content_text
    assert sec0.modules[1].mod_type == "resource"
    assert sec0.modules[1].name == "Programa_de_la_Materia.pdf"

    sec1 = sections[1]
    assert sec1.section_number == 1
    assert len(sec1.modules) == 2
    assert sec1.modules[0].mod_type == "page"
    assert sec1.modules[1].mod_type == "url"


def test_parse_page_content():
    page_html = """
    <div id="region-main">
        <h2 class="page-title">Unidad 1: Algoritmos</h2>
        <div class="box py-3 generalbox page-content">
            <h3>Introducción</h3>
            <p>Un algoritmo es una secuencia finita de instrucciones bien definidas.</p>
            <div class="activity-navigation">Ignorar este bloque</div>
        </div>
    </div>
    """
    result = MoodleParser.parse_page_content(page_html)
    assert result["title"] == "Unidad 1: Algoritmos"
    assert "secuencia finita" in result["text"]
    assert "Ignorar este bloque" not in result["text"]


def test_parse_folder_files():
    folder_html = """
    <div class="foldertree">
        <div>
            <a href="https://aulas.itu.uncu.edu.ar/itu/pluginfile.php/123/mod_folder/content/0/Guia1.pdf">
                Guia1.pdf
            </a>
            <span class="filesize">1.2 MB</span>
        </div>
        <div>
            <a href="https://aulas.itu.uncu.edu.ar/itu/pluginfile.php/123/mod_folder/content/0/Ejemplos.zip">
                Ejemplos.zip
            </a>
            <span class="filesize">4.5 MB</span>
        </div>
    </div>
    """
    base_url = "https://aulas.itu.uncu.edu.ar/itu/"
    files = MoodleParser.parse_folder_files(folder_html, base_url, "Tema 1", "Carpeta Material")

    assert len(files) == 2
    assert files[0].name == "Guia1.pdf"
    assert files[0].size_hint == "1.2 MB"
    assert files[1].name == "Ejemplos.zip"


def test_parse_course_contents_from_ajax():
    ajax_data = [{
        "data": [
            {
                "id": 501,
                "name": "Unidad 1 - Introducción a los Patrones de Diseño",
                "section": 1,
                "summary": "<p>Objetivos de la unidad</p>",
                "modules": [
                    {
                        "id": 1001,
                        "name": "1.1.1 - Introducción a los Patrones de Diseño",
                        "modname": "page",
                        "url": "https://aulas.itu.uncu.edu.ar/itu/mod/page/view.php?id=1001",
                        "contents": []
                    },
                    {
                        "id": 1002,
                        "name": "1.1.2 - Presentación: Introducción a los Patrones de Diseño",
                        "modname": "resource",
                        "url": "https://aulas.itu.uncu.edu.ar/itu/mod/resource/view.php?id=1002",
                        "contents": [
                            {
                                "filename": "Presentacion_Patrones.pdf",
                                "fileurl": "https://aulas.itu.uncu.edu.ar/itu/webservice/pluginfile.php/1002/mod_resource/content/1/Presentacion_Patrones.pdf",
                                "filesize": 2048576
                            }
                        ]
                    }
                ]
            }
        ]
    }]
    base_url = "https://aulas.itu.uncu.edu.ar/itu/"
    sections = MoodleParser.parse_course_contents_from_ajax(ajax_data, base_url)

    assert len(sections) == 1
    assert sections[0].name == "Unidad 1 - Introducción a los Patrones de Diseño"
    assert len(sections[0].modules) == 2

    mod_pdf = sections[0].modules[1]
    assert mod_pdf.mod_type == "resource"
    assert len(mod_pdf.files) == 1
    assert mod_pdf.files[0].name == "Presentacion_Patrones.pdf"
    assert "pluginfile.php" in mod_pdf.files[0].url


def test_extract_section_links_from_html():
    html = """
    <div class="onetopic">
        <ul class="nav nav-tabs">
            <li class="nav-item"><a class="nav-link" href="https://aulas.itu.uncu.edu.ar/itu/course/view.php?id=45&section=0">General</a></li>
            <li class="nav-item"><a class="nav-link" href="https://aulas.itu.uncu.edu.ar/itu/course/view.php?id=45&section=1">Unidad 1</a></li>
            <li class="nav-item"><a class="nav-link" href="https://aulas.itu.uncu.edu.ar/itu/course/view.php?id=45&section=2">Unidad 2</a></li>
        </ul>
    </div>
    """
    base_url = "https://aulas.itu.uncu.edu.ar/itu/"
    links = MoodleParser.extract_section_links_from_html(html, base_url, "45")

    assert len(links) == 3
    assert links[0][0] == 0
    assert links[1][0] == 1
    assert links[2][0] == 2
