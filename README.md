# 🎓 Moodle 4.x Scraper & Extractor de Teoría (ITU UNCUYO)

Un scraper modular, robusto y automatizado en **Python 3.10+** diseñado específicamente para la plataforma **Moodle 4.x** 

Permite descargar automáticamente todos los recursos de estudio (PDFs, presentaciones PPTX, documentos Word DOCX, hojas de cálculo, archivos comprimidos ZIP y carpetas completas) y extraer todo el texto, teoría explicativa, etiquetas y páginas teóricas a archivos **Markdown (.md)** perfectamente estructurados por temas y unidades.

---

## 🚀 Características Principales

- 🔐 **Autenticación Moodle 4.x Segura:**
  - Extracción automática de token CSRF (`logintoken`) previo al `POST` de login.
  - Persistencia de cookies con `requests.Session` y obtención de clave de sesión (`sesskey`).
  - **Soporte de Cookie de Sesión Directa (`MoodleSession`):** Permite conectarse directamente en entornos que utilizan Single Sign-On (Google Workspace, Microsoft 365 / Entra ID) o Captcha.
- 🧭 **Mapeo Inteligente de Cursos:**
  - Detección rápida mediante el WebService AJAX de Moodle (`core_course_get_enrolled_courses_by_timeline_classification`), `my/courses.php` y `my/`.
  - Menú interactivo para seleccionar cursos individuales (`1`), listas/rangos (`1,3,5` o `1-4`), o todos con `a`.
- ⚡ **Descargas Concurrentes y Streaming de Alto Rendimiento:**
  - **Pool de Descargas Paralelas (`ThreadPoolExecutor`):** Descarga múltiples archivos simultáneamente con control de hilos concurrentes (`--workers`).
  - **Motor de Parseo `lxml` Ultrarrápido:** Extracción del árbol DOM 5x-10x más rápida con tolerancia a HTML mal formado.
  - **Cortesía de Red y Rate Limiting:** Control de retardo (`--delay`) y reintentos adaptativos para proteger el servidor de la universidad.
  - Descarga en bloques de 8KB (`stream=True`) con archivos temporales `.part` para evitar corrupciones.
  - Resolución inteligente de nombres reales mediante cabeceras `Content-Disposition` (RFC 5987 / RFC 2616), URLs redirigidas y `Content-Type`.
  - **Mecanismo Anti-Duplicados:** Omite descargas de archivos existentes con el mismo tamaño para reanudación instantánea sin consumo innecesario de ancho de banda.
- 📝 **Extracción Completa de Texto y Teoría a Markdown:**
  - **Títulos de sección:** Nombres limpios de cada unidad o tema.
  - **Etiquetas y avisos (`mod_label`):** Explicaciones de los profesores, notas y advertencias.
  - **Páginas teóricas (`mod_page`):** Extracción y conversión completa de HTML a Markdown limpio.
  - **Enlaces externos (`mod_url`):** Enlaces web y descripciones asociadas.
  - **Consolidado General (`notas_y_teoria_completa.md`):** Todo el curso en un solo documento con índice y enlaces.
  - **Resumen por tema (`resumen_tema.md`):** Contenido textual específico dentro de cada carpeta de tema.
- 🛡 **Sanitización Total de Archivos:** Compatible al 100% con Windows (`\ / : * ? " < > |`), Linux y macOS (incluyendo soporte UTF-8 seguro para consolas Windows).
- 🎨 **Consola Enriquecida:** Colores, estados claros y métricas detalladas de descarga en tiempo real.

---

## 📁 Estructura de Archivos Generada

Al ejecutar el scraper, se organizará el material de la siguiente manera:

```text
downloads/
└── 2025B - Álgebra y Estadística - Junin_DS/
    ├── notas_y_teoria_completa.md       # Todo el texto, etiquetas y teoría consolidada
    ├── Tema_0_General_Información General/
    │   ├── resumen_tema.md              # Resumen y avisos generales
    │   └── Programa_de_la_Materia.pdf   # Archivos descargados
    ├── Tema_1_Matrices y Determinantes/
    │   ├── resumen_tema.md              # Explicaciones teóricas de la unidad
    │   ├── Teoria_Matrices.pdf
    │   └── Guia_Practica_1.docx
    └── Tema_2_Sistemas de Ecuaciones Lineales/
        ├── resumen_tema.md
        └── Ejercicios_Resueltos.pdf
```

---

## 🛠 Instalación y Requisitos

### 1. Requisitos Previos
- Python 3.10 o superior instalado en el sistema.

### 2. Clonar / Descargar el Proyecto
Asegúrese de estar en el directorio del proyecto:
```bash
cd "c:\TuNombre\Moodle Scraper"
```

### 3. Instalar Dependencias
Instale las librerías necesarias con `pip`:
```bash
pip install -r requirements.txt
```

---

## ⚙ Configuración de Credenciales

Copie el archivo de ejemplo `.env.example` como `.env` (o use `scraper.conf`):

```bash
copy .env.example .env
```

Edite el archivo `.env` con sus credenciales de Moodle ITU UNCUYO:

```ini
# Credenciales de acceso a Moodle ITU UNCUYO
MOODLE_USER=tu_usuario_moodle
MOODLE_PASSWORD=tu_contraseña_moodle

# O bien usar Cookie de Sesión (para SSO de Google/Microsoft)
# MOODLE_SESSION_COOKIE=tu_cookie_aqui

# URL Base del Moodle
MOODLE_BASE_URL=https://aulas.itu.uncu.edu.ar/itu/

# Directorio de descarga local
DOWNLOAD_DIR=./downloads

# Concurrencia y optimizaciones
MAX_WORKERS=3
REQUEST_DELAY=0.0

# Opciones avanzadas
OVERWRITE_EXISTING=false
SAVE_SECTION_SUMMARIES=true
SAVE_CONSOLIDATED_MARKDOWN=true
REQUEST_TIMEOUT=30
CHUNK_SIZE_KB=8
```

---

## 💻 Modos de Uso

### 1. Modo Interactivo (Recomendado)
Ejecute el script principal para autenticarse y seleccionar interactivamente los cursos:
```bash
python main.py
```
*Se mostrará una lista numerada con todos sus cursos matriculados. Puede ingresar `1` para un curso, `1-5` para un rango, `1,3,7` para cursos específicos o `a` para descargar TODOS.*

### 2. Descarga Automática de TODOS los Cursos
Para descargar todo el contenido de todas las materias sin preguntas interactivas:
```bash
python main.py --all
```

### 3. Descarga de un Curso Específico por ID
Si conoce el ID del curso de Moodle (ej: `course/view.php?id=1234`):
```bash
python main.py --course-id 1234
```

### 4. Filtrar Cursos por Nombre
Para procesar materias que contengan una palabra clave:
```bash
python main.py --filter "Algebra"
python main.py --filter "Hardware"
```

### 5. Parámetros Adicionales de Línea de Comandos
- `-w`, `--workers 4`: Define el número de descargas simultáneas en paralelo (por defecto: `3`).
- `--delay 0.5`: Añade una pausa de cortesía en segundos entre peticiones para proteger el servidor.
- `--cookie "valor_moodlesession"`: Autentica directamente mediante cookie de sesión (evita login con credenciales / SSO).
- `--download-dir "C:/Mis_Materias"`: Especifica una carpeta de destino personalizada.
- `--overwrite`: Fuerza la sobreescritura de archivos locales existentes.
- `--env "ruta/a/otro.env"`: Carga un archivo `.env` específico.
- `--conf "ruta/a/config.ini"`: Carga un archivo INI específico.

---

---

## 🧪 Ejecución de Pruebas Unitarias

Para validar el funcionamiento de los componentes internos (parsers DOM, sanitización de nombres en Windows, extracción de cabeceras HTTP y formateo Markdown):

```bash
python -m unittest discover -s tests
```

---

## 🏛 Arquitectura del Proyecto

```text
Moodle Scraper/
├── main.py                      # Punto de entrada y gestión de argumentos CLI
├── requirements.txt             # Dependencias del proyecto
├── .env.example                 # Plantilla de configuración de entorno
├── scraper.conf.example         # Plantilla de configuración INI alternativa
├── README.md                    # Documentación y manual de uso
├── moodle_scraper/              # Paquete principal
│   ├── __init__.py
│   ├── config.py                # Carga y validación de variables de configuración
│   ├── session.py               # Gestión de sesión, CSRF logintoken y sesskey
│   ├── parser.py                # Parseo BeautifulSoup4 de cursos, secciones y DOM
│   ├── downloader.py            # Descargador streaming 8KB, Content-Disposition y deduplicación
│   ├── markdown_writer.py       # Conversor HTML->Markdown y creador de teoría
│   ├── course_scraper.py        # Orquestador por curso (secciones, páginas, recursos)
│   ├── cli.py                   # Menú interactivo y selección por consola
│   └── utils.py                 # Sanitización Windows/Linux, Logger coloreado y helpers
└── tests/                       # Suite de pruebas unitarias
    ├── test_utils.py
    ├── test_parser.py
    ├── test_downloader.py
    └── test_markdown_writer.py
```
