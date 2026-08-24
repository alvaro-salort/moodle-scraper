"""
Gestor de Sesión y Autenticación para Moodle 4.x (ITU UNCUYO).
Maneja cookies persistentes, extracción de logintoken CSRF y obtención de sesskey.
"""

import re
import requests
from typing import Optional, Tuple
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter

from moodle_scraper.config import ScraperConfig
from moodle_scraper.utils import Logger


class MoodleAuthError(Exception):
    """Excepción lanzada cuando la autenticación en Moodle falla."""
    pass


class MoodleSession:
    """Administra la sesión HTTP, autenticación y llamadas a la API/Web de Moodle."""

    def __init__(self, config: ScraperConfig):
        self.config = config
        self.session = requests.Session()
        self.sesskey: Optional[str] = None
        self.is_authenticated: bool = False
        self.user_fullname: Optional[str] = None

        # Configurar reintentos automáticos para errores de red transitorios (500, 502, 503, 504)
        retries = Retry(
            total=config.max_retries,
            backoff_factor=1.0,
            status_forcelist=[500, 502, 503, 504],
            raise_on_status=False
        )
        adapter = HTTPAdapter(max_retries=retries)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

        # Configurar cabeceras de navegador moderno
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
            "Connection": "keep-alive"
        })

    def _resolve_url(self, endpoint: str) -> str:
        """Construye una URL absoluta a partir de un endpoint relativo."""
        return urljoin(self.config.base_url, endpoint)

    def extract_logintoken(self) -> Tuple[str, str]:
        """
        Realiza una petición GET a login/index.php para extraer el token CSRF (logintoken)
        y el anchor requerido por Moodle 4.x.
        """
        login_url = self._resolve_url("login/index.php")
        Logger.info(f"Obteniendo página de login y token CSRF: {login_url}")
        
        try:
            resp = self.session.get(login_url, timeout=self.config.timeout)
            resp.raise_for_status()
        except requests.RequestException as e:
            raise MoodleAuthError(f"No se pudo conectar a la página de login de Moodle: {e}")

        soup = BeautifulSoup(resp.text, "html.parser")
        
        # Buscar input oculto 'logintoken'
        token_input = soup.find("input", {"name": "logintoken"})
        logintoken = token_input.get("value", "") if token_input else ""
        
        # Buscar input 'anchor' si existe
        anchor_input = soup.find("input", {"name": "anchor"})
        anchor = anchor_input.get("value", "") if anchor_input else ""

        # Moodle 4.x puede incluir logintoken directamente en el formulario
        if not logintoken:
            # Buscar en regex como respaldo
            match = re.search(r'name=["\']logintoken["\']\s+value=["\']([^"\']+)["\']', resp.text)
            if match:
                logintoken = match.group(1)

        if not logintoken:
            Logger.warn("No se encontró 'logintoken' en el formulario de login. Continuando sin él.")

        return logintoken, anchor

    def login(self, username: Optional[str] = None, password: Optional[str] = None) -> bool:
        """
        Realiza el flujo completo de login contra Moodle 4.x:
        1. GET login/index.php -> extraer logintoken
        2. POST login/index.php -> enviar credenciales
        3. Validar sesión y extraer sesskey del usuario
        """
        user = username or self.config.user
        pwd = password or self.config.password

        if not user or not pwd:
            raise MoodleAuthError("Credenciales incompletas. Verifique MOODLE_USER y MOODLE_PASSWORD.")

        logintoken, anchor = self.extract_logintoken()

        login_post_url = self._resolve_url("login/index.php")
        payload = {
            "anchor": anchor,
            "logintoken": logintoken,
            "username": user,
            "password": pwd,
            "rememberusername": "1"
        }

        Logger.info(f"Autenticando usuario '{user}' en Moodle...")
        try:
            resp = self.session.post(
                login_post_url,
                data=payload,
                timeout=self.config.timeout,
                allow_redirects=True
            )
            resp.raise_for_status()
        except requests.RequestException as e:
            raise MoodleAuthError(f"Error de red durante el intento de login: {e}")

        # Comprobar si hubo error en la página devuelta
        soup = BeautifulSoup(resp.text, "html.parser")
        
        # Detección de mensajes de error típicos de Moodle
        error_elem = (
            soup.find("div", {"id": "loginerrormessage"})
            or soup.find("div", class_=re.compile(r"alert-danger|notifyproblem"))
            or soup.find("span", class_="error")
        )
        
        if error_elem:
            error_text = error_elem.get_text(strip=True)
            raise MoodleAuthError(f"Error de autenticación reportado por Moodle: {error_text}")

        # Comprobar si seguimos en la página de login con formulario activo
        if "login/index.php" in resp.url and soup.find("input", {"name": "password"}):
            raise MoodleAuthError("Fallo de autenticación: Las credenciales fueron rechazadas por Moodle.")

        # Extraer sesskey y datos del usuario de la respuesta
        self.sesskey = self._extract_sesskey(resp.text)
        self.user_fullname = self._extract_user_fullname(soup)
        self.is_authenticated = True

        Logger.success(f"Autenticación exitosa! Sesión iniciada como: {self.user_fullname or user}")
        if self.sesskey:
            Logger.info(f"Clave de sesión (sesskey) obtenida: {self.sesskey}")

        return True

    def _extract_sesskey(self, html_content: str) -> Optional[str]:
        """Extrae el sesskey de configuraciones de Javascript o enlaces en el HTML."""
        # 1. Buscar en objeto M.cfg de JavaScript
        match = re.search(r'["\']sesskey["\']\s*:\s*["\']([a-zA-Z0-9]+)["\']', html_content)
        if match:
            return match.group(1)
        
        # 2. Buscar en enlaces de logout o parámetros url ?sesskey=...
        match = re.search(r'[?&]sesskey=([a-zA-Z0-9]+)', html_content)
        if match:
            return match.group(1)

        # 3. Buscar en inputs hidden
        match = re.search(r'<input[^>]+name=["\']sesskey["\'][^>]+value=["\']([a-zA-Z0-9]+)["\']', html_content)
        if match:
            return match.group(1)

        return None

    def _extract_user_fullname(self, soup: BeautifulSoup) -> Optional[str]:
        """Intenta extraer el nombre completo del usuario conectado desde el navbar."""
        user_menu = (
            soup.find("div", class_="userbutton")
            or soup.find("span", class_="usertext")
            or soup.find("div", class_="usermenu")
        )
        if user_menu:
            return user_menu.get_text(strip=True)
        return None

    def get(self, url_or_endpoint: str, **kwargs) -> requests.Response:
        """Petición GET envuelta con URL resolution y timeout por defecto."""
        target_url = self._resolve_url(url_or_endpoint)
        kwargs.setdefault("timeout", self.config.timeout)
        return self.session.get(target_url, **kwargs)

    def post(self, url_or_endpoint: str, **kwargs) -> requests.Response:
        """Petición POST envuelta con URL resolution y timeout por defecto."""
        target_url = self._resolve_url(url_or_endpoint)
        kwargs.setdefault("timeout", self.config.timeout)
        return self.session.post(target_url, **kwargs)
