"""
Pruebas unitarias para el parser de Moodle 4.x (HTML, AJAX, cursos, secciones y actividades).
"""

import unittest
from moodle_scraper.parser import MoodleParser, Course, CourseSection, CourseModule


class TestParser(unittest.TestCase):

    def test_parse_courses_from_html(self):
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

        self.assertEqual(len(courses), 2)
        c_ids = [c.id for c in courses]
        self.assertIn("101", c_ids)
        self.assertIn("102", c_ids)
        self.assertNotIn("1", c_ids)

    def test_parse_courses_from_ajax(self):
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

        self.assertEqual(len(courses), 2)
        self.assertEqual(courses[0].id, "201")
        self.assertEqual(courses[0].name, "2025B - Base de Datos Relacionales - Junin/DS")
        self.assertEqual(courses[1].id, "202")
        self.assertEqual(courses[1].name, "2025B - Programación Orientada a Objetos - JNN/DS")

    def test_parse_course_sections_and_modules(self):
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

        self.assertEqual(len(sections), 2)
        
        sec0 = sections[0]
        self.assertEqual(sec0.section_number, 0)
        self.assertIn("Información General", sec0.name)
        self.assertEqual(len(sec0.modules), 2)
        self.assertEqual(sec0.modules[0].mod_type, "label")
        self.assertIn("Aviso Importante", sec0.modules[0].content_text)
        self.assertEqual(sec0.modules[1].mod_type, "resource")
        self.assertEqual(sec0.modules[1].name, "Programa_de_la_Materia.pdf")

        sec1 = sections[1]
        self.assertEqual(sec1.section_number, 1)
        self.assertEqual(len(sec1.modules), 2)
        self.assertEqual(sec1.modules[0].mod_type, "page")
        self.assertEqual(sec1.modules[1].mod_type, "url")

    def test_parse_page_content(self):
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
        self.assertEqual(result["title"], "Unidad 1: Algoritmos")
        self.assertIn("secuencia finita", result["text"])
        self.assertNotIn("Ignorar este bloque", result["text"])

    def test_parse_folder_files(self):
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

        self.assertEqual(len(files), 2)
        self.assertEqual(files[0].name, "Guia1.pdf")
        self.assertEqual(files[0].size_hint, "1.2 MB")
        self.assertEqual(files[1].name, "Ejemplos.zip")


if __name__ == "__main__":
    unittest.main()
