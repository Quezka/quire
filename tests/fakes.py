from dataclasses import dataclass, field
from datetime import date

from quire.application.errors import AuthenticationError
from quire.application.ports import (
    Credentials, RegisterAccount, RemoteAssignment, RemoteGrade, RemoteLesson, RemoteSubject,
)


@dataclass
class FakeRegister:
    """In-memory stand-in for a school register."""

    name: str = "Classeviva"
    password: str = "secret"
    student: str = "Ada Lovelace"
    subjects_: list[RemoteSubject] = field(default_factory=list)
    assignments_: list[RemoteAssignment] = field(default_factory=list)
    homework_: list[RemoteAssignment] = field(default_factory=list)
    grades_: list[RemoteGrade] = field(default_factory=list)
    lessons_: list[RemoteLesson] = field(default_factory=list)
    absences_: list = field(default_factory=list)
    notices_: list = field(default_factory=list)
    books_: list = field(default_factory=list)
    documents_: list = field(default_factory=list)
    school_days_: list = field(default_factory=list)
    files: dict = field(default_factory=dict)  # (notice id or document id, number) -> bytes
    opened: list = field(default_factory=list)
    requested: list = field(default_factory=list)
    failing: dict = field(default_factory=dict)  # method name -> exception to raise

    def _maybe_fail(self, name):
        if name in self.failing:
            raise self.failing[name]

    def login(self, credentials: Credentials) -> RegisterAccount:
        if credentials.password != self.password:
            raise AuthenticationError("wrong password")
        return RegisterAccount(self.student)

    def subjects(self):
        self._maybe_fail("subjects")
        return list(self.subjects_)

    def assignments(self, first: date, last: date):
        self._maybe_fail("assignments")
        self.requested.append(("assignments", first, last))
        return [a for a in self.assignments_ if first <= a.day <= last]

    def homework(self):
        self._maybe_fail("homework")
        return list(self.homework_)

    def grades(self):
        self._maybe_fail("grades")
        return list(self.grades_)

    def lessons(self, first: date, last: date):
        self._maybe_fail("lessons")
        self.requested.append(("lessons", first, last))
        return [l for l in self.lessons_ if first <= l.day <= last]

    def absences(self):
        self._maybe_fail("absences")
        return list(self.absences_)

    def notices(self):
        self._maybe_fail("notices")
        return list(self.notices_)

    def open_notice(self, notice):
        self.opened.append(f"{notice.code}:{notice.pub_id}")

    def notice_attachment(self, notice, number):
        return self.files[(f"{notice.code}:{notice.pub_id}", number)]

    def books(self):
        self._maybe_fail("books")
        return list(self.books_)

    def documents(self):
        self._maybe_fail("documents")
        return list(self.documents_)

    def document_file(self, document):
        return self.files[(document.external_id, 0)]

    def school_days(self):
        self._maybe_fail("school_days")
        return list(self.school_days_)


class FakeCloud:
    """An in-memory Firebase: accounts, and records stamped with a server counter."""

    def __init__(self):
        from quire.application.ports import CloudSession
        self._Session = CloudSession
        self.accounts: dict[str, str] = {}  # email -> password
        self.docs: dict[tuple[str, str, str], tuple[int, object]] = {}  # (user, kind, uid)
        self.clock = 0
        self.offline = False
        self.pushes = 0

    def _check(self):
        if self.offline:
            from quire.application.errors import SyncError
            raise SyncError("Can't reach the sync server. Check your internet connection.")

    def _session(self, email):
        return self._Session(f"user-{email}", email, f"token-{email}", f"refresh-{email}")

    def sign_up(self, config, email, password):
        from quire.application.errors import CloudAuthError
        self._check()
        if email in self.accounts:
            raise CloudAuthError("There's already an account with this email: sign in instead.")
        self.accounts[email] = password
        return self._session(email)

    def sign_in(self, config, email, password):
        from quire.application.errors import CloudAuthError
        self._check()
        if self.accounts.get(email) != password:
            raise CloudAuthError("Wrong email or password.")
        return self._session(email)

    def refresh(self, config, refresh_token):
        from quire.application.errors import CloudAuthError
        self._check()
        email = refresh_token.removeprefix("refresh-")
        if email not in self.accounts:
            raise CloudAuthError("Your sign-in has expired: set up sync again.")
        return self._session(email)

    def pull(self, config, session, cursor):
        self._check()
        since = int(cursor or 0)
        mine = sorted((stamp, rec) for (user, _k, _u), (stamp, rec) in self.docs.items()
                      if user == session.user_id and stamp > since)
        return [rec for _s, rec in mine], str(max([since] + [s for s, _r in mine]))

    def push(self, config, session, records):
        self._check()
        self.pushes += 1
        for rec in records:
            self.clock += 1
            self.docs[(session.user_id, rec.kind, rec.uid)] = (self.clock, rec)


class FakeReleases:
    """A release feed that never touches the network."""

    def __init__(self, release=None):
        self.release = release
        self.downloads = []

    def latest(self):
        return self.release

    def download(self, asset, progress):
        progress(asset.size // 2, asset.size)
        progress(asset.size, asset.size)
        self.downloads.append(asset.name)
        return f"/tmp/{asset.name}"


class FakeInstaller:
    def __init__(self, supported=True, takes_over=False):
        self._supported = supported
        self.takes_over = takes_over
        self.installed = []

    def supported(self):
        return self._supported

    def pick(self, assets):
        return next((a for a in assets if a.name.endswith(".deb")), None)

    def install(self, path):
        self.installed.append(path)
        return self.takes_over
