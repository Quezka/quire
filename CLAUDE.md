# Quire

Python 3.10+ / PySide6 desktop app (Linux + Windows). Clean Architecture; see README "Architecture".

- Layers: `quire/domain` → `quire/application` → `quire/infrastructure` + `quire/presentation`; wired in `quire/bootstrap.py`.
- Dependency rule is enforced by `tests/test_architecture.py`; never import PySide6/sqlite3 into domain or application, never import infrastructure into presentation.
- Run: `.venv/bin/quire --demo`. Test: `.venv/bin/python -m pytest -q`.
- Headless UI checks: `QT_QPA_PLATFORM=offscreen`.
- Dates in format strings: don't use `%-d` (breaks on Windows); build day numbers with `d.day`.
- School sync: `SchoolSyncService.fetch()` is network-only and runs on a worker thread; `apply()` writes to SQLite and must run on the UI thread (sqlite connections are thread-bound).
- Device sync: `SyncService.prepare()`/`finish()` run on the UI thread, `exchange()` (network) on a worker. Change tracking is SQLite triggers in `infrastructure/sync_store.py` (uid/modified/dirty columns, tombstones, `sync_flags` switch). A new synced table or column needs its export/upsert there. Tests use `tests/fakes.FakeCloud` and in-memory sign-in storage, never Firebase or the real keyring.
- Classeviva is an unofficial API (`quire/infrastructure/classeviva.py`); tests use canned JSON (`tests/test_classeviva.py`) and `tests/fakes.FakeRegister`, never the network.
- Schema changes: bump `SCHEMA_VERSION` in `infrastructure/sqlite.py` and add an idempotent step in `_migrate()`; cover it in `tests/test_migration.py`.
- Never name a Qt subclass attribute after a Qt method (e.g. `self.done` on a QDialog); UI smoke tests in `tests/test_ui_smoke.py` catch these.
- UI text must be translatable: wrap it in `_()` (or `N_()`/`C_()`), add the Russian to `quire/presentation/locales/ru.py`; `tests/test_i18n.py` enforces it. Never format dates with strftime names; use the i18n name helpers.
