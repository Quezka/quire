"""Keep store/packaging metadata consistent with quire/__init__.py."""
import ast
import configparser
import importlib.util
import xml.etree.ElementTree as ET

import pytest
from pathlib import Path

import quire

ROOT = Path(__file__).resolve().parent.parent
PACKAGING = ROOT / "packaging"
METAINFO = PACKAGING / f"{quire.APP_ID}.metainfo.xml"
DESKTOP = PACKAGING / f"{quire.APP_ID}.desktop"


def metainfo():
    return ET.parse(METAINFO).getroot()


def test_metainfo_identifies_app_and_developer():
    root = metainfo()
    assert root.findtext("id") == quire.APP_ID
    assert root.findtext("name") == quire.APP_NAME
    developer = root.find("developer")
    assert developer.get("id") == quire.DEVELOPER_ID
    assert developer.findtext("name") == quire.DEVELOPER
    assert root.findtext("launchable") == DESKTOP.name
    assert root.find("url[@type='homepage']").text == quire.HOMEPAGE


def test_current_version_is_the_newest_release():
    releases = metainfo().findall("releases/release")
    assert releases, "metainfo has no <release> entries"
    assert releases[0].get("version") == quire.__version__, (
        f"add <release version=\"{quire.__version__}\"> at the top of {METAINFO.name}")


def test_desktop_file_points_at_app_id():
    entry = configparser.ConfigParser(interpolation=None)
    entry.optionxform = str
    entry.read(DESKTOP, encoding="utf-8")
    assert entry["Desktop Entry"]["Icon"] == quire.APP_ID
    assert entry["Desktop Entry"]["Exec"].split()[0] == "quire"


def test_windows_version_file_is_valid_python(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("build_script", ROOT / "scripts" / "build.py")
    build = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build)
    monkeypatch.setattr(build, "BUILD", tmp_path)
    text = build.write_windows_version_file().read_text(encoding="utf-8")
    ast.parse(text)
    assert f"'CompanyName', '{quire.DEVELOPER}'" in text
    assert f"'ProductVersion', '{quire.__version__}'" in text


def load_release_notes():
    spec = importlib.util.spec_from_file_location("release_notes",
                                                  ROOT / "scripts" / "release_notes.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_changelog_has_notes_for_current_version():
    notes = load_release_notes().notes_for(quire.__version__)
    assert notes and not notes.startswith("## ")


def test_release_notes_stop_at_the_next_version():
    text = "# Changelog\n\n## [1.1.0] - x\n- new\n\n## [1.0.0] - y\n- old\n"
    assert load_release_notes().notes_for("1.1.0", text) == "- new"
    with pytest.raises(SystemExit):
        load_release_notes().notes_for("9.9.9", text)


def test_version_is_semver():
    import re
    assert re.fullmatch(r"\d+\.\d+\.\d+", quire.__version__)
