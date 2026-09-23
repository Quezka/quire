# Quire

Python 3.10+ / PySide6 desktop app (Linux + Windows). Clean Architecture; see README "Architecture".

- Layers: `quire/domain` → `quire/application` → `quire/infrastructure` + `quire/presentation`; wired in `quire/bootstrap.py`.
- Dependency rule is enforced by `tests/test_architecture.py`; never import PySide6/sqlite3 into domain or application, never import infrastructure into presentation.
- Run: `.venv/bin/quire --demo`. Test: `.venv/bin/python -m pytest -q`.
- Headless UI checks: `QT_QPA_PLATFORM=offscreen`.
- Dates in format strings: don't use `%-d` (breaks on Windows); build day numbers with `d.day`.
