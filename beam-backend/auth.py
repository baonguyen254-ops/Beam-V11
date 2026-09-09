"""Local accounts, scrypt passwords and revocable hashed sessions. No default password."""

import hashlib
import hmac
import secrets
import time
import uuid
from collections import defaultdict, deque
from pathlib import Path

ROLES = {"ADMIN", "CLINICIAN", "OPERATOR", "VIEWER"}
COOKIE = "beam_session"
SESSION_SECONDS = 8 * 3600


def password_hash(password, salt=None):
    if not isinstance(password, str) or not 12 <= len(password) <= 256:
        raise ValueError("Password must contain 12 to 256 characters")
    salt = salt or secrets.token_hex(16)
    return (
        salt
        + ":"
        + hashlib.scrypt(
            password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1
        ).hex()
    )


class Auth:
    def __init__(self, store, data_dir):
        self.store = store
        self.key_path = Path(data_dir) / "bootstrap-key.txt"
        self.attempts = defaultdict(deque)
        if self.needs_setup and not store.get("bootstrap_hash"):
            key = secrets.token_urlsafe(24)
            self.key_path.write_text(key, encoding="utf-8")
            self.key_path.chmod(0o600)
            store.put("bootstrap_hash", self.digest(key))
            store.db.commit()
        if self.needs_setup:
            print(
                "BEAM first setup: read the local bootstrap key at "
                + str(self.key_path)
            )

    @staticmethod
    def digest(value):
        return hashlib.sha256(value.encode()).hexdigest()

    @property
    def needs_setup(self):
        return self.store.db.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0

    def throttle(self, key):
        now = time.monotonic()
        q = self.attempts[key]
        while q and now - q[0] > 60:
            q.popleft()
        if len(q) >= 8:
            raise ValueError("Too many login attempts. Wait one minute.")
        q.append(now)
        if len(self.attempts) > 10000:
            self.attempts = defaultdict(
                deque,
                {k: v for k, v in self.attempts.items() if v and now - v[-1] < 60},
            )

    def create_user(self, username, password, role):
        if not isinstance(username, str) or not 3 <= len(username.strip()) <= 80:
            raise ValueError("Username must contain 3 to 80 characters")
        if role not in ROLES:
            raise ValueError("Invalid role")
        user = {
            "id": str(uuid.uuid4()),
            "username": username.strip().lower(),
            "role": role,
        }
        self.store.db.execute(
            "INSERT INTO users(id,username,password,role) VALUES(?,?,?,?)",
            (user["id"], user["username"], password_hash(password), role),
        )
        self.store.db.commit()
        return user

    def setup(self, key, username, password):
        if (
            not self.needs_setup
            or not isinstance(key, str)
            or not hmac.compare_digest(
                self.digest(key), self.store.get("bootstrap_hash", "")
            )
        ):
            raise ValueError("Setup unavailable or incorrect bootstrap key")
        user = self.create_user(username, password, "ADMIN")
        self.store.put("bootstrap_hash", None)
        self.store.db.commit()
        self.key_path.unlink(missing_ok=True)
        return user

    def login(self, username, password):
        if not isinstance(username, str) or not isinstance(password, str):
            raise ValueError("Invalid credentials")
        row = self.store.db.execute(
            "SELECT * FROM users WHERE username=? AND active=1",
            (username.strip().lower(),),
        ).fetchone()
        stored = row["password"] if row else "0" * 32 + ":" + "0" * 128
        calculated = password_hash(password, stored.split(":")[0])
        if not row or not hmac.compare_digest(calculated, stored):
            raise ValueError("Invalid credentials")
        return {k: row[k] for k in ("id", "username", "role")}

    def session(self, user):
        token = secrets.token_urlsafe(32)
        self.store.db.execute(
            "INSERT INTO sessions VALUES(?,?,?)",
            (self.digest(token), user["id"], time.time() + SESSION_SECONDS),
        )
        self.store.db.commit()
        return token

    def user(self, token):
        if not token or len(token) > 200:
            return None
        row = self.store.db.execute(
            "SELECT u.id,u.username,u.role FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token=? AND s.expires>? AND u.active=1",
            (self.digest(token), time.time()),
        ).fetchone()
        return dict(row) if row else None

    def logout(self, token):
        if token:
            self.store.db.execute(
                "DELETE FROM sessions WHERE token=?", (self.digest(token),)
            )
            self.store.db.commit()
