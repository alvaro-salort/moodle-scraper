from unittest.mock import Mock

from moodle_scraper.config import (
    ScraperConfig,
    load_config,
    prompt_for_base_url,
    prompt_for_credentials,
)


def test_prompt_for_missing_base_url():
    input_func = Mock(return_value="https://moodle.example.edu")
    config = ScraperConfig(base_url="")

    prompt_for_base_url(config, input_func)

    assert config.base_url == "https://moodle.example.edu/"
    input_func.assert_called_once_with("URL base de Moodle: ")


def test_prompt_does_not_replace_configured_base_url():
    input_func = Mock()
    config = ScraperConfig(base_url="https://moodle.example.edu/")

    prompt_for_base_url(config, input_func)

    assert config.base_url == "https://moodle.example.edu/"
    input_func.assert_not_called()


def test_load_config_keeps_missing_base_url_empty(tmp_path, monkeypatch):
    monkeypatch.delenv("MOODLE_BASE_URL", raising=False)

    config = load_config(env_path=tmp_path / "missing.env", conf_path=tmp_path / "missing.conf")

    assert config.base_url == ""


def test_prompt_for_missing_credentials():
    input_func = Mock(return_value="usuario")
    password_func = Mock(return_value="secreto")
    config = ScraperConfig()

    prompt_for_credentials(config, input_func, password_func)

    assert config.user == "usuario"
    assert config.password == "secreto"
    input_func.assert_called_once_with("Usuario de Moodle: ")
    password_func.assert_called_once_with("Contraseña de Moodle: ")


def test_prompt_does_not_replace_configured_credentials():
    input_func = Mock()
    password_func = Mock()
    config = ScraperConfig(user="usuario", password="secreto")

    prompt_for_credentials(config, input_func, password_func)

    assert config.user == "usuario"
    assert config.password == "secreto"
    input_func.assert_not_called()
    password_func.assert_not_called()


def test_prompt_is_skipped_for_session_cookie():
    input_func = Mock()
    password_func = Mock()
    config = ScraperConfig(session_cookie="cookie")

    prompt_for_credentials(config, input_func, password_func)

    input_func.assert_not_called()
    password_func.assert_not_called()
