from __future__ import annotations

import base64
import json
import re
import uuid
from dataclasses import dataclass
from datetime import datetime

from ..bus import ChangeBus, Topic
from ..errors import CloudAuthError, SyncNotSetUp, ValidationError
from ..ports import (
    CloudBackend, CloudConfig, CloudSession, Clock, CredentialStore, Credentials, KeyValueStore,
    SyncRecord, SyncStore,
)

TOPICS = {"course": Topic.COURSES, "event": Topic.EVENTS, "task": Topic.TASKS,
          "note": Topic.NOTES, "journal": Topic.JOURNAL, "job": Topic.WORK, "shift": Topic.WORK,
          "focus": Topic.FOCUS}
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PROJECT = re.compile(r"^[a-z0-9][a-z0-9-]{4,28}[a-z0-9]$")


@dataclass(frozen=True)
class SyncStatus:
    set_up: bool
    email: str
    project_id: str
    last_sync: datetime | None
    pending: int  # local changes not sent yet
    problem: str  # the last sync's error, "" if it worked


@dataclass(frozen=True)
class SyncJob:
    """What a sync needs from this device, gathered on the UI thread."""

    config: CloudConfig
    refresh_token: str
    cursor: str | None
    outgoing: tuple[SyncRecord, ...]


@dataclass(frozen=True)
class SyncExchange:
    """What came back from the cloud, to be applied on the UI thread."""

    incoming: tuple[SyncRecord, ...]
    sent: tuple[SyncRecord, ...]
    cursor: str | None
    refresh_token: str


@dataclass(frozen=True)
class SyncResult:
    received: int  # records from other devices applied here
    sent: int


class SyncService:
    """Use cases for syncing Quire between devices through a cloud account.

    Local-first: everything keeps working offline; a sync sends what changed here and takes
    what changed elsewhere, and when both changed the same record the newer change wins.
    Grades and lesson topics are never synced (each device gets them from the register).

    A sync runs in three steps so the network part can run on a worker thread:
    `prepare()` (UI thread) → `exchange()` (any thread, network only) → `finish()` (UI thread).
    """

    PREFIX = "sync."

    def __init__(self, store: SyncStore, cloud: CloudBackend, secrets: CredentialStore,
                 settings: KeyValueStore, clock: Clock, bus: ChangeBus):
        self._store = store
        self._cloud = cloud
        self._secrets = secrets
        self._settings = settings
        self._clock = clock
        self._bus = bus

    def _get(self, name: str) -> str:
        return self._settings.get(self.PREFIX + name) or ""

    def _set(self, name: str, value: str | None):
        self._settings.set(self.PREFIX + name, value)

    def config(self) -> CloudConfig | None:
        project, key = self._get("project"), self._get("api_key")
        return CloudConfig(project, key) if project and key else None

    def status(self) -> SyncStatus:
        last = self._get("last_sync")
        return SyncStatus(self.config() is not None and self._secrets.load() is not None,
                          self._get("email"), self._get("project"),
                          datetime.fromisoformat(last) if last else None,
                          self._store.pending(), self._get("problem"))

    # ---- account ----------------------------------------------------------------

    def phone_link(self, register: Credentials | None = None) -> str:
        """A setup code for the phone app (shown as a QR code): the sync project and this
        computer's sign-in, and optionally the school register login, so the phone is ready
        without typing anything. It carries secrets: it's shown on screen, never sent."""
        config, saved = self.config(), self._secrets.load()
        if config is None or saved is None:
            raise SyncNotSetUp("Set up sync on this computer first.")
        data = {"v": "1", "project": config.project_id, "api_key": config.api_key,
                "email": self._get("email"), "refresh": saved.password}
        if register is not None:
            data.update(cv_user=register.username, cv_pass=register.password)
        raw = json.dumps(data, separators=(",", ":")).encode()
        return "quire-link:" + base64.urlsafe_b64encode(raw).decode().rstrip("=")


    @staticmethod
    def check(project_id: str, api_key: str, email: str, password: str) -> CloudConfig:
        project_id, api_key, email = project_id.strip(), api_key.strip(), email.strip()
        if not _PROJECT.match(project_id):
            raise ValidationError("Copy the project ID from the Firebase console, e.g. "
                                  "quire-sync-1a2b3.")
        if len(api_key) < 20 or " " in api_key:
            raise ValidationError("Copy the Web API key from the Firebase console.")
        if not _EMAIL.match(email):
            raise ValidationError("Type the email address for your sync account.")
        if not password:
            raise ValidationError("Type a password.")
        return CloudConfig(project_id, api_key)

    def authenticate(self, config: CloudConfig, email: str, password: str,
                     create: bool) -> CloudSession:
        """Sign in (or create the account). Network only: run it on a worker thread."""
        email = email.strip()
        if create:
            return self._cloud.sign_up(config, email, password)
        return self._cloud.sign_in(config, email, password)

    def connect(self, config: CloudConfig, session: CloudSession,
                take_cloud_copy: bool = False) -> None:
        """Remember the account on this device. With `take_cloud_copy`, this device's synced
        data is replaced by what's in the cloud at the next sync (for a second device)."""
        if take_cloud_copy:
            self._store.clear_all()
            for topic in set(TOPICS.values()):
                self._bus.publish(topic)
        self._secrets.save(Credentials(session.email, session.refresh_token))
        self._set("project", config.project_id)
        self._set("api_key", config.api_key)
        self._set("email", session.email)
        self._set("cursor", None)  # pull everything once from the new account
        self._set("problem", None)
        if not self._get("device"):
            self._set("device", uuid.uuid4().hex)

    def disconnect(self) -> None:
        """Stop syncing on this device; its data stays here."""
        self._secrets.clear()
        for name in ("project", "api_key", "email", "cursor", "last_sync", "problem"):
            self._set(name, None)

    # ---- syncing ----------------------------------------------------------------

    def prepare(self) -> SyncJob:
        config, saved = self.config(), self._secrets.load()
        if config is None or saved is None:
            raise SyncNotSetUp("Set up sync first.")
        return SyncJob(config, saved.password, self._get("cursor") or None,
                       tuple(self._store.outgoing()))

    def exchange(self, job: SyncJob) -> SyncExchange:
        """Pull what changed elsewhere, then push what changed here and is still newest.
        Network only: run it on a worker thread."""
        session = self._cloud.refresh(job.config, job.refresh_token)
        incoming, cursor = self._cloud.pull(job.config, session, job.cursor)
        newest = {}
        for record in incoming:
            if record.modified > newest.get(record.key, ""):
                newest[record.key] = record.modified
        sent = tuple(r for r in job.outgoing if r.modified >= newest.get(r.key, ""))
        if sent:
            self._cloud.push(job.config, session, list(sent))
        return SyncExchange(tuple(incoming), sent, cursor, session.refresh_token)

    def finish(self, exchange: SyncExchange) -> SyncResult:
        changed = self._store.apply(list(exchange.incoming))
        self._store.mark_sent(list(exchange.sent))
        self._set("cursor", exchange.cursor)
        self._set("last_sync", self._clock.now().isoformat(timespec="seconds"))
        self._set("problem", None)
        saved = self._secrets.load()
        if saved is not None and exchange.refresh_token != saved.password:
            self._secrets.save(Credentials(saved.username, exchange.refresh_token))
        for topic in {TOPICS[kind] for kind, _uid in changed}:
            self._bus.publish(topic)
        return SyncResult(len(changed), len(exchange.sent))

    def failed(self, error: Exception) -> None:
        """Remember why the last sync didn't work, for the status line."""
        self._set("problem", str(error))
        if isinstance(error, CloudAuthError):
            self._secrets.clear()  # the saved sign-in is dead: ask to set up again

    def sync(self) -> SyncResult:
        """All three steps in a row (tests, command line)."""
        try:
            return self.finish(self.exchange(self.prepare()))
        except SyncNotSetUp:
            raise
        except Exception as e:
            self.failed(e)
            raise
