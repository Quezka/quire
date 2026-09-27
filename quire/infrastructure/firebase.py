"""Adapter for Firebase: email/password accounts (Identity Toolkit) and Cloud Firestore,
through their REST APIs (no Google SDK needed).

Each account's records live in `users/<account id>/records/<kind>~<uid>`; the security rules
shown in the setup dialog let an account read and write only its own folder. Every write
stamps a server time (`synced`), and pulling asks for documents after the last one seen in
(synced, name) order, so device clocks never matter for what gets pulled.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable

from ..application.errors import CloudAuthError, SyncError
from ..application.ports import CloudConfig, CloudSession, SyncRecord

AUTH_URL = "https://identitytoolkit.googleapis.com/v1/accounts:{action}?key={key}"
TOKEN_URL = "https://securetoken.googleapis.com/v1/token?key={key}"
FIRESTORE = "https://firestore.googleapis.com/v1"
PAGE = 300
BATCH = 400  # Firestore allows 500 writes per commit

AUTH_MESSAGES = {
    "EMAIL_EXISTS": "There's already an account with this email: sign in instead.",
    "EMAIL_NOT_FOUND": "No account with this email: create one first.",
    "INVALID_PASSWORD": "Wrong email or password.",
    "INVALID_LOGIN_CREDENTIALS": "Wrong email or password.",
    "INVALID_EMAIL": "That email address doesn't look right.",
    "MISSING_PASSWORD": "Type a password.",
    "USER_DISABLED": "This account has been disabled in the Firebase console.",
    "OPERATION_NOT_ALLOWED": "Turn on Email/Password sign-in in the Firebase console "
                             "(Authentication → Sign-in method).",
    "TOO_MANY_ATTEMPTS_TRY_LATER": "Too many attempts: wait a few minutes and try again.",
    "TOKEN_EXPIRED": "Your sign-in has expired: set up sync again.",
    "INVALID_REFRESH_TOKEN": "Your sign-in has expired: set up sync again.",
    "USER_NOT_FOUND": "This account no longer exists: set up sync again.",
    "API_KEY_INVALID": "The Web API key isn't right: copy it again from the Firebase console.",
}


def _auth_message(code: str) -> str:
    # Codes may carry details, e.g. "WEAK_PASSWORD : Password should be at least 6 characters".
    base = code.split(":")[0].strip()
    if base == "WEAK_PASSWORD":
        return "Choose a password of at least 6 characters."
    if base.startswith("API key not valid"):
        return AUTH_MESSAGES["API_KEY_INVALID"]
    return AUTH_MESSAGES.get(base, f"Firebase refused the sign-in ({base}).")


def doc_id(record: SyncRecord) -> str:
    return f"{record.kind}~{record.uid}".replace("/", "%2F")


def to_fields(record: SyncRecord) -> dict:
    return {
        "kind": {"stringValue": record.kind},
        "uid": {"stringValue": record.uid},
        "modified": {"stringValue": record.modified},
        "deleted": {"booleanValue": record.deleted},
        # One JSON string: the payload's shape can change without touching the schema.
        "data": {"stringValue": json.dumps(record.data)} if record.data is not None
        else {"nullValue": None},
    }


def from_fields(fields: dict) -> SyncRecord | None:
    try:
        data = fields.get("data", {})
        return SyncRecord(fields["kind"]["stringValue"], fields["uid"]["stringValue"],
                          fields["modified"]["stringValue"],
                          fields.get("deleted", {}).get("booleanValue", False),
                          json.loads(data["stringValue"]) if "stringValue" in data else None)
    except (KeyError, TypeError, ValueError):
        return None  # not ours, or damaged: skip it


class FirebaseCloud:
    name = "Firebase"

    def __init__(self, opener: Callable = urllib.request.urlopen, timeout: float = 30):
        self._open = opener
        self._timeout = timeout

    # ---- HTTP ------------------------------------------------------------------

    def _post(self, url: str, body: dict, token: str | None = None, form: bool = False,
              auth: bool = False):
        if form:
            data = urllib.parse.urlencode(body).encode()
            headers = {"Content-Type": "application/x-www-form-urlencoded"}
        else:
            data = json.dumps(body).encode()
            headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        request = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with self._open(request, timeout=self._timeout) as response:
                return json.loads(response.read().decode() or "null")
        except urllib.error.HTTPError as e:
            try:
                error = json.loads(e.read().decode()).get("error", {})
            except (ValueError, AttributeError):
                error = {}
            raise self._error(e.code, error, auth) from e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise SyncError("Can't reach the sync server. Check your internet connection.") from e
        except ValueError as e:
            raise SyncError("The sync server sent an answer Quire doesn't understand.") from e

    @staticmethod
    def _error(status: int, error, auth: bool) -> Exception:
        message = error.get("message", "") if isinstance(error, dict) else str(error)
        if auth and 400 <= status < 500:  # the account endpoints explain with a code
            return CloudAuthError(_auth_message(message))
        if status == 401:
            return CloudAuthError("Your sign-in has expired: set up sync again.")
        if status == 403:
            return SyncError("Firestore refused access. Check that the database exists and "
                             "that the security rules from the setup dialog are published.")
        if status == 404:
            return SyncError("Firestore database not found. Check the project ID and create "
                             "the database in the Firebase console.")
        return SyncError(f"The sync server answered with an error ({status}).")

    # ---- accounts ----------------------------------------------------------------

    def _account(self, action: str, config: CloudConfig, email: str,
                 password: str) -> CloudSession:
        r = self._post(AUTH_URL.format(action=action, key=config.api_key),
                       {"email": email, "password": password, "returnSecureToken": True},
                       auth=True)
        return CloudSession(r["localId"], r.get("email", email), r["idToken"], r["refreshToken"])

    def sign_up(self, config, email, password):
        return self._account("signUp", config, email, password)

    def sign_in(self, config, email, password):
        return self._account("signInWithPassword", config, email, password)

    def refresh(self, config, refresh_token):
        r = self._post(TOKEN_URL.format(key=config.api_key),
                       {"grant_type": "refresh_token", "refresh_token": refresh_token},
                       form=True, auth=True)
        return CloudSession(r["user_id"], "", r["id_token"], r["refresh_token"])

    # ---- records -----------------------------------------------------------------

    @staticmethod
    def _root(config: CloudConfig) -> str:
        return f"projects/{config.project_id}/databases/(default)/documents"

    def pull(self, config, session, cursor):
        parent = f"{self._root(config)}/users/{session.user_id}"
        records: list[SyncRecord] = []
        while True:
            query = {
                "from": [{"collectionId": "records"}],
                "orderBy": [{"field": {"fieldPath": "synced"}, "direction": "ASCENDING"},
                            {"field": {"fieldPath": "__name__"}, "direction": "ASCENDING"}],
                "limit": PAGE,
            }
            if cursor:
                synced, name = json.loads(cursor)
                query["startAt"] = {"values": [{"timestampValue": synced},
                                               {"referenceValue": name}], "before": False}
            rows = self._post(f"{FIRESTORE}/{parent}:runQuery", {"structuredQuery": query},
                              session.token) or []
            documents = [row["document"] for row in rows if "document" in row]
            for doc in documents:
                record = from_fields(doc.get("fields", {}))
                if record is not None:
                    records.append(record)
                synced = doc.get("fields", {}).get("synced", {}).get("timestampValue")
                if synced:
                    cursor = json.dumps([synced, doc["name"]])
            if len(documents) < PAGE:
                return records, cursor

    def push(self, config, session, records):
        base = f"{self._root(config)}/users/{session.user_id}/records"
        for start in range(0, len(records), BATCH):
            writes = [{
                "update": {"name": f"{base}/{doc_id(r)}", "fields": to_fields(r)},
                "updateTransforms": [{"fieldPath": "synced", "setToServerValue": "REQUEST_TIME"}],
            } for r in records[start:start + BATCH]]
            self._post(f"{FIRESTORE}/{self._root(config)}:commit", {"writes": writes},
                       session.token)
