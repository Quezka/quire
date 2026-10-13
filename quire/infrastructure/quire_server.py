"""Adapter for the self-hosted Quire sync server (quire-server): accounts and records over its
small JSON API (`docs/PROTOCOL.md` in that repo; `tests/reference_client.py` is the executable
version of what this file does).

It replaces Firebase behind the same `CloudBackend` port. `CloudConfig.project_id` carries the
server's base URL (for example `https://sync.quezka.uk`); `api_key` is unused. Records keep the
shape they always had (kind, uid, modified, deleted, data), so change tracking and the "newest
`modified` wins" rule don't change. Pulling follows an opaque cursor the server hands out, so
device clocks never matter for what gets pulled.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable

from .. import __version__
from ..application.errors import CloudAuthError, SyncError
from ..application.ports import CloudConfig, CloudSession, SyncRecord

BATCH = 400  # records per push call (the server accepts up to 1000)
BATCH_BYTES = 8_000_000  # and 16 MB per request: pictures in notes are big
EXPIRED = {"invalid_refresh_token", "user_not_found", "invalid_token", "missing_token"}


def base_url(config: CloudConfig) -> str:
    """The server's address from the settings: `https://` is assumed when none is typed."""
    url = config.project_id.strip().rstrip("/")
    return url if "://" in url else "https://" + url


def to_json(record: SyncRecord) -> dict:
    return {"kind": record.kind, "uid": record.uid, "modified": record.modified,
            "deleted": record.deleted, "data": None if record.deleted else record.data}


def from_json(raw) -> SyncRecord | None:
    try:
        deleted = bool(raw.get("deleted", False))
        data = raw.get("data")
        if not deleted and not isinstance(data, dict):
            return None
        return SyncRecord(str(raw["kind"]), str(raw["uid"]), str(raw["modified"]), deleted,
                          None if deleted else data)
    except (KeyError, TypeError, AttributeError):
        return None  # not ours, or damaged: skip it


class QuireServerCloud:
    name = "Quire server"

    def __init__(self, opener: Callable = urllib.request.urlopen, timeout: float = 30,
                 device: str = "Quire desktop"):
        self._open = opener
        self._timeout = timeout
        self._device = device

    # ---- HTTP ------------------------------------------------------------------

    def _call(self, config: CloudConfig, method: str, path: str, body: dict | None = None,
              query: dict | None = None, token: str | None = None):
        url = base_url(config) + path
        if query:
            url += "?" + urllib.parse.urlencode(query)
        headers = {"Accept": "application/json", "User-Agent": f"Quire/{__version__}"}
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        if token:
            headers["Authorization"] = f"Bearer {token}"
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with self._open(request, timeout=self._timeout) as response:
                return json.loads(response.read().decode() or "null")
        except urllib.error.HTTPError as e:
            try:
                error = json.loads(e.read().decode()).get("error", {})
            except (ValueError, AttributeError):
                error = {}
            raise _ServerRefused(e.code, error if isinstance(error, dict) else {}) from e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise SyncError("Can't reach the sync server. Check your internet connection.") from e
        except ValueError as e:
            raise SyncError("The sync server sent an answer Quire doesn't understand.") from e

    def _request(self, *args, account: bool = False, **kwargs):
        """One call, with the server's refusals turned into messages for the person."""
        try:
            return self._call(*args, **kwargs)
        except _ServerRefused as e:
            raise self._error(e, account) from e

    @staticmethod
    def _error(e: "_ServerRefused", account: bool) -> Exception:
        message = str(e.error.get("message") or "")
        code = e.error.get("code")
        if code in EXPIRED:
            return CloudAuthError("Your sign-in has expired: set up sync again.")
        if e.status == 429 and message:
            return SyncError(message)  # "wait N seconds": not a dead sign-in
        if account and 400 <= e.status < 500 and message:
            return CloudAuthError(message)  # wrong password, sign-up closed, email in use...
        if e.status == 401:
            return CloudAuthError("Your sign-in has expired: set up sync again.")
        return SyncError(f"The sync server answered with an error ({e.status}).")

    def _authed(self, config: CloudConfig, session: CloudSession, *args, **kwargs):
        """A signed-in call. If the access token ran out meanwhile (they last an hour), get a
        new one from the refresh token and try once more."""
        try:
            return self._call(config, *args, token=session.token, **kwargs)
        except _ServerRefused as e:
            if e.error.get("code") != "token_expired":
                raise self._error(e, False) from e
        fresh = self.refresh(config, session.refresh_token)
        try:
            return self._call(config, *args, token=fresh.token, **kwargs)
        except _ServerRefused as e:
            raise self._error(e, False) from e

    # ---- accounts ----------------------------------------------------------------

    def _session(self, answer, email: str = "") -> CloudSession:
        try:
            return CloudSession(answer["user_id"], answer.get("email") or email, answer["token"],
                                answer["refresh_token"])
        except (KeyError, TypeError) as e:
            raise SyncError("The sync server sent an answer Quire doesn't understand.") from e

    def sign_up(self, config, email, password, invite: str = ""):
        body = {"email": email, "password": password, "device": self._device}
        if invite:
            body["invite"] = invite
        return self._session(self._request(config, "POST", "/v1/signup", body, account=True),
                             email)

    def sign_in(self, config, email, password):
        body = {"email": email, "password": password, "device": self._device}
        return self._session(self._request(config, "POST", "/v1/signin", body, account=True),
                             email)

    def refresh(self, config, refresh_token):
        answer = self._request(config, "POST", "/v1/refresh", {"refresh_token": refresh_token})
        # The refresh token comes back unchanged; keep ours if an older server leaves it out.
        if isinstance(answer, dict):
            answer.setdefault("refresh_token", refresh_token)
        return self._session(answer)

    # ---- records -----------------------------------------------------------------

    def pull(self, config, session, cursor):
        records: list[SyncRecord] = []
        while True:
            answer = self._authed(config, session, "GET", "/v1/records",
                                  query={"after": cursor} if cursor else None)
            try:
                rows, more = answer["records"], bool(answer["more"])
                cursor = answer.get("cursor") or cursor
            except (KeyError, TypeError) as e:
                raise SyncError("The sync server sent an answer Quire doesn't understand.") from e
            for raw in rows:
                record = from_json(raw)
                if record is not None:
                    records.append(record)
            if not more:
                return records, cursor

    def push(self, config, session, records):
        for batch in _batches(records):
            self._authed(config, session, "POST", "/v1/records",
                         body={"records": [to_json(r) for r in batch]})


class _ServerRefused(Exception):
    """The server answered with an error status; turned into a user message by `_error`."""

    def __init__(self, status: int, error: dict):
        super().__init__(status)
        self.status, self.error = status, error


def _batches(records):
    """Groups of records small enough for one call: at most BATCH records, and about
    BATCH_BYTES of data (a group always takes at least one record)."""
    batch, size = [], 0
    for r in records:
        length = len(json.dumps(r.data)) if r.data is not None else 0
        if batch and (len(batch) >= BATCH or size + length > BATCH_BYTES):
            yield batch
            batch, size = [], 0
        batch.append(r)
        size += length
    if batch:
        yield batch
