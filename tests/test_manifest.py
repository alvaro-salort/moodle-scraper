"""
Pruebas del manifest de descargas y su verificación.
"""

from pathlib import Path

from moodle_scraper.manifest import RunManifest, sha256_file, verify_directory


def test_manifest_roundtrip_and_current_file(tmp_path):
    payload = tmp_path / "Tema 1" / "documento.pdf"
    payload.parent.mkdir(parents=True)
    payload.write_bytes(b"contenido")
    digest = sha256_file(payload)

    manifest = RunManifest(tmp_path, course_id="101", course_name="Curso")
    manifest.record(
        "https://moodle.test/pluginfile.php/1/documento.pdf",
        payload,
        size=payload.stat().st_size,
        sha256=digest,
        remote_size=payload.stat().st_size,
        remote_mtime=1700000000,
    )
    manifest.save()

    reloaded = RunManifest(tmp_path)
    entry = reloaded.get(
        "https://moodle.test/pluginfile.php/1/documento.pdf",
        payload.parent,
    )

    assert entry is not None
    assert entry["local_path"] == "Tema 1/documento.pdf"
    assert entry["sha256"] == digest
    assert reloaded.is_current(
        "https://moodle.test/pluginfile.php/1/documento.pdf",
        payload.parent,
        expected_size=payload.stat().st_size,
        expected_mtime=1700000000,
    ) == payload


def test_manifest_is_not_current_when_size_or_mtime_changes(tmp_path):
    payload = tmp_path / "documento.pdf"
    payload.write_bytes(b"contenido")
    url = "https://moodle.test/pluginfile.php/1/documento.pdf"

    manifest = RunManifest(tmp_path)
    manifest.record(url, payload, size=payload.stat().st_size, remote_size=9, remote_mtime=100)

    assert manifest.is_current(url, expected_size=9, expected_mtime=100) == payload
    assert manifest.is_current(url, expected_size=10, expected_mtime=100) is None
    assert manifest.is_current(url, expected_size=9, expected_mtime=101) is None


def test_manifest_not_current_when_file_missing(tmp_path):
    payload = tmp_path / "documento.pdf"
    payload.write_bytes(b"contenido")
    url = "https://moodle.test/pluginfile.php/1/documento.pdf"

    manifest = RunManifest(tmp_path)
    manifest.record(url, payload, size=payload.stat().st_size)
    payload.unlink()

    assert manifest.is_current(url) is None


def test_manifest_keeps_same_url_in_different_sections(tmp_path):
    url = "https://moodle.test/pluginfile.php/1/compartido.pdf"
    manifest = RunManifest(tmp_path)

    for section in ("Tema 1", "Tema 2"):
        payload = tmp_path / section / "compartido.pdf"
        payload.parent.mkdir(parents=True)
        payload.write_bytes(section.encode("utf-8"))
        manifest.record(url, payload, size=payload.stat().st_size)

    assert manifest.get(url, tmp_path / "Tema 1")["local_path"] == "Tema 1/compartido.pdf"
    assert manifest.get(url, tmp_path / "Tema 2")["local_path"] == "Tema 2/compartido.pdf"


def test_manifest_verify_detects_tampering(tmp_path):
    payload = tmp_path / "documento.pdf"
    payload.write_bytes(b"contenido")
    url = "https://moodle.test/pluginfile.php/1/documento.pdf"

    manifest = RunManifest(tmp_path)
    manifest.record(url, payload, size=payload.stat().st_size, sha256=sha256_file(payload))
    manifest.save()

    assert manifest.verify() == []

    payload.write_bytes(b"otro contenido distinto")
    issues = manifest.verify()

    assert len(issues) == 1
    assert "tamaño" in issues[0] or "SHA-256" in issues[0]


def test_verify_directory_finds_nested_manifests(tmp_path):
    course_a = tmp_path / "Curso A"
    course_b = tmp_path / "Curso B"
    for course in (course_a, course_b):
        course.mkdir()
        payload = course / "documento.pdf"
        payload.write_bytes(b"contenido")
        manifest = RunManifest(course)
        manifest.record(
            "https://moodle.test/pluginfile.php/1/documento.pdf",
            payload,
            size=payload.stat().st_size,
            sha256=sha256_file(payload),
        )
        manifest.save()

    assert verify_directory(tmp_path) == []

    (course_b / "documento.pdf").write_bytes(b"cambiado")
    issues = verify_directory(tmp_path)

    assert len(issues) == 1
    assert "Curso B" in issues[0]
