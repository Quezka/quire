"""The Quire server adapter against canned HTTP answers (never the network)."""
import io
import json
import urllib.error
import urllib.parse

import pytest

from quire.application.errors import CloudAuthError, SyncError
from quire.application.ports import CloudConfig, CloudSession, SyncRecord
from quire.infrastructure.quire_server import (
    BATCH, QuireServerCloud, base_url, from_json, to_json, _batches,
)

CONFIG = CloudConfig("https://sync.example.com", "")
SESSION = CloudSession("u1", "me@example.com", "tok", "ref")
SESSION_ANSWER = {"user_id": "u1", "email": "me@example.com", "token": "t",
                  "refresh_token": "r", "expires_in": 3600}


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


def refused(status, code, message="m"):
    return status, {"error": {"code": code, "message": message}}


def body(request):
    return json.loads(request.data.decode())


def rec(uid="a", modified="2026-10-10T10:00:00.000Z", deleted=False, **data):
    return SyncRecord("task", uid, modified, deleted, None if deleted else (data or {"t": uid}))


def test_sign_in_returns_a_session_and_labels_the_device():
    opener = Opener((200, SESSION_ANSWER))
    session = QuireServerCloud(opener, device="Laptop").sign_in(CONFIG, "me@example.com", "pw")
    assert session == CloudSession("u1", "me@example.com", "t", "r")
    request = opener.requests[0]
    assert request.full_url == "https://sync.example.com/v1/signin"
    assert request.get_method() == "POST"
    assert body(request) == {"email": "me@example.com", "password": "pw", "device": "Laptop"}
    assert request.headers["User-agent"].startswith("Quire/")


def test_sign_up_sends_the_invite_only_when_given():
    opener = Opener((200, SESSION_ANSWER), (200, SESSION_ANSWER))
    cloud = QuireServerCloud(opener)
    cloud.sign_up(CONFIG, "me@example.com", "pw")
    cloud.sign_up(CONFIG, "me@example.com", "pw", invite="open-sesame")
    assert "invite" not in body(opener.requests[0])
    assert body(opener.requests[1])["invite"] == "open-sesame"


@pytest.mark.parametrize("status, code, message", [
    (401, "invalid_credentials", "Wrong email or password."),
    (403, "signup_closed", "Sign-ups are closed on this server."),
    (409, "email_exists", "That email is already registered."),
    (400, "weak_password", "Choose a longer password."),
])
def test_account_refusals_show_the_servers_message(status, code, message):
    opener = Opener(refused(status, code, message))
    with pytest.raises(CloudAuthError, match=message):
        QuireServerCloud(opener).sign_up(CONFIG, "me@example.com", "pw")


def test_too_many_attempts_is_a_plain_sync_error_with_the_servers_message():
    opener = Opener(refused(429, "too_many_attempts", "Wait 30 seconds."))
    with pytest.raises(SyncError, match="Wait 30 seconds") as e:
        QuireServerCloud(opener).sign_in(CONFIG, "me@example.com", "pw")
    assert not isinstance(e.value, CloudAuthError)  # the saved sign-in is still good


def test_refresh_keeps_the_refresh_token_the_server_returns():
    opener = Opener((200, {"user_id": "u1", "token": "t2", "refresh_token": "r1",
                           "expires_in": 3600}))
    session = QuireServerCloud(opener).refresh(CONFIG, "r1")
    assert (session.user_id, session.token, session.refresh_token) == ("u1", "t2", "r1")
    assert body(opener.requests[0]) == {"refresh_token": "r1"}
    assert "Authorization" not in opener.requests[0].headers


def test_refresh_keeps_our_token_if_the_answer_leaves_it_out():
    opener = Opener((200, {"user_id": "u1", "token": "t2"}))
    assert QuireServerCloud(opener).refresh(CONFIG, "r1").refresh_token == "r1"


def test_a_dead_refresh_token_means_set_up_sync_again():
    opener = Opener(refused(401, "invalid_refresh_token"))
    with pytest.raises(CloudAuthError, match="expired"):
        QuireServerCloud(opener).refresh(CONFIG, "old")


def test_pull_follows_the_cursor_until_there_is_no_more():
    opener = Opener(
        (200, {"records": [to_json(rec("a")), to_json(rec("b"))], "cursor": "c1", "more": True}),
        (200, {"records": [to_json(rec("c", deleted=True))], "cursor": "c2", "more": False}))
    records, cursor = QuireServerCloud(opener).pull(CONFIG, SESSION, None)
    assert [r.uid for r in records] == ["a", "b", "c"]
    assert records[2].deleted and records[2].data is None
    assert cursor == "c2"
    first, second = opener.requests
    assert first.full_url == "https://sync.example.com/v1/records"  # no cursor the first time
    assert urllib.parse.parse_qs(urllib.parse.urlparse(second.full_url).query) == {"after": ["c1"]}
    assert first.headers["Authorization"] == "Bearer tok"
    assert first.get_method() == "GET"


def test_pull_skips_damaged_records_but_keeps_the_rest():
    good = to_json(rec("ok"))
    opener = Opener((200, {"records": [{"kind": "task"}, "junk", good,
                                       {**good, "uid": "x", "data": "not an object"}],
                           "cursor": "c", "more": False}))
    records, _ = QuireServerCloud(opener).pull(CONFIG, SESSION, "old")
    assert [r.uid for r in records] == ["ok"]


def test_pull_with_nothing_new_keeps_the_cursor():
    opener = Opener((200, {"records": [], "cursor": "", "more": False}))
    assert QuireServerCloud(opener).pull(CONFIG, SESSION, "c9") == ([], "c9")


def test_an_expired_access_token_is_refreshed_once_and_the_call_retried():
    opener = Opener(refused(401, "token_expired"),
                    (200, {"user_id": "u1", "token": "fresh", "refresh_token": "ref"}),
                    (200, {"records": [], "cursor": "c", "more": False}))
    QuireServerCloud(opener).pull(CONFIG, SESSION, None)
    assert [r.full_url.rsplit("/", 1)[1] for r in opener.requests] == ["records", "refresh",
                                                                       "records"]
    assert opener.requests[2].headers["Authorization"] == "Bearer fresh"


def test_expired_twice_gives_up_instead_of_looping():
    opener = Opener(refused(401, "token_expired"),
                    (200, {"user_id": "u1", "token": "fresh", "refresh_token": "ref"}),
                    refused(401, "token_expired"))
    with pytest.raises(CloudAuthError):
        QuireServerCloud(opener).pull(CONFIG, SESSION, None)
    assert len(opener.requests) == 3


def test_a_revoked_account_asks_for_a_new_sign_in():
    with pytest.raises(CloudAuthError, match="expired"):
        QuireServerCloud(Opener(refused(401, "user_not_found"))).pull(CONFIG, SESSION, None)


def test_push_sends_records_in_the_shape_the_server_expects():
    opener = Opener((200, {"stored": 2, "cursor": "c"}))
    QuireServerCloud(opener).push(CONFIG, SESSION, [rec("a", n=1), rec("b", deleted=True)])
    request = opener.requests[0]
    assert request.full_url == "https://sync.example.com/v1/records"
    assert request.headers["Authorization"] == "Bearer tok"
    assert body(request) == {"records": [
        {"kind": "task", "uid": "a", "modified": "2026-10-10T10:00:00.000Z", "deleted": False,
         "data": {"n": 1}},
        {"kind": "task", "uid": "b", "modified": "2026-10-10T10:00:00.000Z", "deleted": True,
         "data": None}]}


def test_push_splits_big_batches_by_count_and_size():
    many = [rec(str(i)) for i in range(BATCH * 2 + 1)]
    assert [len(b) for b in _batches(many)] == [BATCH, BATCH, 1]
    pictures = [rec(str(i), data="x" * 3_000_000) for i in range(5)]
    assert [len(b) for b in _batches(pictures)] == [2, 2, 1]
    assert list(_batches([])) == []


def test_a_rejected_push_is_an_error_not_silence():
    opener = Opener(refused(413, "payload_too_large", "Send less."))
    with pytest.raises(SyncError, match="answered with an error"):
        QuireServerCloud(opener).push(CONFIG, SESSION, [rec()])


@pytest.mark.parametrize("failure", [urllib.error.URLError("no route"), TimeoutError(),
                                     ConnectionResetError()])
def test_an_unreachable_server_is_explained(failure):
    with pytest.raises(SyncError, match="Can't reach the sync server"):
        QuireServerCloud(Opener((0, failure))).sign_in(CONFIG, "me@example.com", "pw")


def test_an_answer_that_isnt_json_is_explained():
    class Garbage(Opener):
        def __call__(self, request, timeout=None):
            return io.BytesIO(b"<html>Bad gateway</html>")

    with pytest.raises(SyncError, match="doesn't understand"):
        QuireServerCloud(Garbage()).pull(CONFIG, SESSION, None)
    with pytest.raises(SyncError, match="doesn't understand"):
        QuireServerCloud(Opener((200, {"nothing": "useful"}))).sign_in(CONFIG, "a@b.c", "pw")


def test_a_proxy_error_page_is_a_sync_error():
    class Page(Opener):
        def __call__(self, request, timeout=None):
            raise urllib.error.HTTPError(request.full_url, 502, "bad", {}, io.BytesIO(b"<html>"))

    with pytest.raises(SyncError, match="502"):
        QuireServerCloud(Page()).pull(CONFIG, SESSION, None)


@pytest.mark.parametrize("typed, url", [
    ("https://sync.example.com", "https://sync.example.com"),
    ("https://sync.example.com/", "https://sync.example.com"),
    ("  sync.example.com  ", "https://sync.example.com"),
    ("http://192.168.1.106:8080/", "http://192.168.1.106:8080"),
])
def test_the_address_is_tidied(typed, url):
    assert base_url(CloudConfig(typed, "")) == url


def test_records_round_trip_through_json():
    record = rec("a", n=1, text="ciao")
    assert from_json(to_json(record)) == record
    gone = rec("b", deleted=True)
    assert from_json(to_json(gone)) == gone
    assert from_json({"kind": "x"}) is None
