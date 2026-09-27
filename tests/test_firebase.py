"""The Firebase adapter against canned HTTP answers (never the network)."""
import io
import json
import urllib.error
import urllib.parse

import pytest

from quire.application.errors import CloudAuthError, SyncError
from quire.application.ports import CloudConfig, CloudSession, SyncRecord
from quire.infrastructure.firebase import FirebaseCloud, doc_id, from_fields, to_fields

CONFIG = CloudConfig("quire-test", "AIzaKEY")
SESSION = CloudSession("uid1", "me@example.com", "tok", "ref")


class Opener:
    """Answers requests in order and records what was asked."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.requests = []

    def __call__(self, request, timeout=None):
        self.requests.append(request)
        status, body = self.answers.pop(0)
        if isinstance(body, Exception):
            raise body
        payload = json.dumps(body).encode()
        if status >= 400:
            raise urllib.error.HTTPError(request.full_url, status, "err", {}, io.BytesIO(payload))
        return io.BytesIO(payload)


def body(request):
    return json.loads(request.data.decode())


def test_sign_in_returns_a_session_and_sends_the_key():
    opener = Opener((200, {"localId": "uid1", "email": "me@example.com", "idToken": "t",
                           "refreshToken": "r"}))
    session = FirebaseCloud(opener).sign_in(CONFIG, "me@example.com", "pw")
    assert session == CloudSession("uid1", "me@example.com", "t", "r")
    request = opener.requests[0]
    assert "accounts:signInWithPassword?key=AIzaKEY" in request.full_url
    assert body(request) == {"email": "me@example.com", "password": "pw",
                             "returnSecureToken": True}


@pytest.mark.parametrize("code, words", [
    ("INVALID_LOGIN_CREDENTIALS", "Wrong email or password"),
    ("EMAIL_EXISTS", "sign in instead"),
    ("WEAK_PASSWORD : Password should be at least 6 characters", "at least 6"),
    ("OPERATION_NOT_ALLOWED", "Email/Password"),
    ("API key not valid. Please pass a valid API key.", "Web API key"),
])
def test_account_errors_are_explained(code, words):
    opener = Opener((400, {"error": {"code": 400, "message": code}}))
    with pytest.raises(CloudAuthError, match=words):
        FirebaseCloud(opener).sign_up(CONFIG, "me@example.com", "pw")


def test_refresh_uses_the_token_endpoint():
    opener = Opener((200, {"user_id": "uid1", "id_token": "t2", "refresh_token": "r2"}))
    session = FirebaseCloud(opener).refresh(CONFIG, "r1")
    assert (session.token, session.refresh_token) == ("t2", "r2")
    request = opener.requests[0]
    assert request.full_url.startswith("https://securetoken.googleapis.com/")
    assert urllib.parse.parse_qs(request.data.decode()) == {
        "grant_type": ["refresh_token"], "refresh_token": ["r1"]}


def test_records_round_trip_through_firestore_fields():
    record = SyncRecord("task", "ext:classeviva:homework:1", "2026-09-28T10:00:00.000Z",
                        False, {"title": "Esercizi", "done": True})
    assert from_fields(to_fields(record)) == record
    gone = SyncRecord("note", "abc", "2026-09-28T10:00:00.000Z", True, None)
    assert from_fields(to_fields(gone)) == gone
    assert from_fields({"kind": {"stringValue": "x"}}) is None  # damaged: skipped
    assert "/" not in doc_id(SyncRecord("task", "a/b", "t"))


def test_push_commits_with_a_server_timestamp():
    opener = Opener((200, {"writeResults": []}))
    record = SyncRecord("note", "n1", "2026-09-28T10:00:00.000Z", False, {"body": "hi"})
    FirebaseCloud(opener).push(CONFIG, SESSION, [record])
    request = opener.requests[0]
    assert request.full_url.endswith("/projects/quire-test/databases/(default)/documents:commit")
    assert request.headers["Authorization"] == "Bearer tok"
    (write,) = body(request)["writes"]
    assert write["update"]["name"].endswith("/users/uid1/records/note~n1")
    assert write["updateTransforms"] == [{"fieldPath": "synced",
                                          "setToServerValue": "REQUEST_TIME"}]


def doc(uid, synced):
    fields = to_fields(SyncRecord("task", uid, "2026-09-28T10:00:00.000Z", False, {"t": uid}))
    fields["synced"] = {"timestampValue": synced}
    return {"document": {"name": f"projects/p/databases/(default)/documents/users/uid1/"
                                 f"records/task~{uid}", "fields": fields}}


def test_pull_pages_through_everything_after_the_cursor(monkeypatch):
    import quire.infrastructure.firebase as firebase
    monkeypatch.setattr(firebase, "PAGE", 2)
    opener = Opener((200, [doc("a", "2026-09-28T10:00:00.1Z"), doc("b", "2026-09-28T10:00:00.1Z")]),
                    (200, [doc("c", "2026-09-28T10:00:01Z"), {"readTime": "x"}]))
    records, cursor = FirebaseCloud(opener).pull(CONFIG, SESSION, None)
    assert [r.uid for r in records] == ["a", "b", "c"]
    first, second = (body(r)["structuredQuery"] for r in opener.requests)
    assert "startAt" not in first
    assert second["startAt"]["values"][0] == {"timestampValue": "2026-09-28T10:00:00.1Z"}
    assert second["startAt"]["values"][1]["referenceValue"].endswith("task~b")
    assert json.loads(cursor)[1].endswith("task~c")


def test_network_and_permission_problems_are_sync_errors():
    offline = Opener((0, urllib.error.URLError("no route")))
    with pytest.raises(SyncError, match="internet"):
        FirebaseCloud(offline).push(CONFIG, SESSION, [SyncRecord("note", "n", "t")])
    denied = Opener((403, {"error": {"code": 403, "message": "Missing or insufficient permissions."}}))
    with pytest.raises(SyncError, match="security rules"):
        FirebaseCloud(denied).pull(CONFIG, SESSION, None)
    expired = Opener((401, {"error": {"code": 401, "message": "Request had invalid credentials."}}))
    with pytest.raises(CloudAuthError):
        FirebaseCloud(expired).pull(CONFIG, SESSION, None)
