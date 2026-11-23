from __future__ import annotations

import hashlib
import json
import re
import secrets
import threading
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from http import HTTPStatus
from pathlib import Path
from typing import Any

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from sentriface.secure_storage import connect_database


AUTH_COOKIE_NAME = "sentriface_auth"
SESSION_HOURS = 8
SESSION_IDLE_MINUTES = 30
MAX_ENDED_SESSIONS = 2048
# One operator uses one browser window. Windows check in every
# WINDOW_HEARTBEAT_SECONDS; an owner unseen for WINDOW_STALE_SECONDS is closed.
WINDOW_HEARTBEAT_SECONDS = 15
WINDOW_STALE_SECONDS = 45
MAX_ENDED_WINDOWS = 256
WINDOW_ID_PATTERN = re.compile(r"^[A-Za-z0-9-]{8,64}$")
SESSION_END_MESSAGES = {
    "account_disabled": "An administrator disabled this account.",
    "access_changed": "An administrator changed this account's access.",
    "account_updated": "An administrator updated this account. Sign in again to continue.",
    "password_reset": "This account's password was reset. Sign in with the new password.",
    "password_changed": "This account's password was changed. Sign in with the new password.",
    "account_removed": "This account is no longer available.",
    "expired": "Your session expired. Sign in again to continue.",
    "idle_timeout": "You were signed out after a period of inactivity.",
    "signed_in_elsewhere": "You signed in from another window. Only one window can be used at a time.",
}
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES = 15
USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,63}$")
PASSWORD_HASHER = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4, hash_len=32, salt_len=16)
RECOVERY_RISK_ACKNOWLEDGEMENT_VERSION = "2026-07-30-v1"
RECOVERY_RISK_SETTING = "recovery_without_disaster_recovery_acknowledgement"

ROLE_CAPABILITIES: dict[str, frozenset[str]] = {
    "viewer": frozenset({"view", "recognize"}),
    "operator": frozenset({"view", "recognize", "add"}),
    "custodian": frozenset({"view", "recognize", "add", "destroy", "backups", "backup_delete"}),
    "technician": frozenset({"view", "recognize", "backups", "technical"}),
    "administrator": frozenset({
        "view", "recognize", "add", "destroy", "backups", "backup_delete",
        "technical", "administer", "database_restore", "recovery", "license_administer",
    }),
}
ROLE_DESCRIPTIONS = {
    "viewer": "View people and run recognition.",
    "operator": "Viewer access plus enrollment and queue/review changes.",
    "custodian": "Operator access plus archive, delete, restore, and backup deletion.",
    "technician": "View access plus logs, machine diagnostics, and backup creation/export.",
    "administrator": "All capabilities, including accounts, licensing, recovery configuration, and database restore.",
}


class AuthError(RuntimeError):
    def __init__(self, message: str, code: str, status: int) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


@dataclass(frozen=True)
class AuthUser:
    user_id: str
    username: str
    display_name: str
    roles: tuple[str, ...]
    disabled: bool
    created_at: str
    updated_at: str
    last_login_at: str | None
    must_change_password: bool = False

    @property
    def capabilities(self) -> frozenset[str]:
        result: set[str] = set()
        for role in self.roles:
            result.update(ROLE_CAPABILITIES.get(role, ()))
        return frozenset(result)

    def has(self, capability: str) -> bool:
        return capability in self.capabilities

    def as_dict(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "username": self.username,
            "display_name": self.display_name,
            "roles": list(self.roles),
            "capabilities": sorted(self.capabilities),
            "disabled": self.disabled,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_login_at": self.last_login_at,
            "must_change_password": self.must_change_password,
        }


@dataclass
class _Session:
    user_id: str
    expires_at: datetime
    last_seen_at: datetime
    window_id: str | None = None
    window_seen_at: datetime | None = None
    replaced_windows: list[str] = field(default_factory=list)
    password_stamp: str | None = None


class AuthService:
    def __init__(self, db_path: Path, database_key: bytes) -> None:
        self.db_path = db_path
        self.database_key = database_key
        self._sessions: dict[str, _Session] = {}
        # In-memory only: why a recently ended session token stopped working.
        self._ended_sessions: dict[str, str] = {}
        # Windows whose session a newer sign-in ended, so they can say why.
        self._ended_windows: dict[str, str] = {}
        self._lock = threading.RLock()
        self._dummy_hash = PASSWORD_HASHER.hash(secrets.token_urlsafe(32))

    def setup_required(self) -> bool:
        with self._connect() as connection:
            return int(connection.execute("SELECT COUNT(*) FROM app_users").fetchone()[0]) == 0

    def signup_initial(self, username: str, display_name: str, password: str, window_id: str | None = None) -> tuple[AuthUser, str]:
        username, normalized = _validate_username(username)
        display_name = _validate_display_name(display_name, username)
        _validate_password(password, username)
        now = _now()
        user_id = str(uuid.uuid4())
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            if int(connection.execute("SELECT COUNT(*) FROM app_users").fetchone()[0]):
                raise AuthError("Initial signup is already complete", "setup_complete", HTTPStatus.CONFLICT)
            connection.execute(
                """INSERT INTO app_users(
                    user_id, username, username_norm, display_name, password_hash, roles,
                    disabled, failed_attempts, locked_until, created_at, updated_at, last_login_at
                ) VALUES (?, ?, ?, ?, ?, ?, 0, 0, NULL, ?, ?, ?)""",
                (user_id, username, normalized, display_name, PASSWORD_HASHER.hash(password),
                 json.dumps(["administrator"]), now, now, now),
            )
            self._audit(connection, user_id, user_id, "initial-signup", {})
        user = self.get_user(user_id)
        return user, self._issue_session(user_id, window_id)

    def login(self, username: str, password: str, window_id: str | None = None) -> tuple[AuthUser, str]:
        _, normalized = _validate_username(username)
        password = password if isinstance(password, str) and len(password) <= 256 else ""
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM app_users WHERE username_norm = ?", (normalized,)).fetchone()
            if row is None:
                self._dummy_verify(password)
                raise _invalid_credentials()
            user = _user_from_row(row)
            if user.disabled:
                self._dummy_verify(password)
                raise AuthError("This account is disabled", "account_disabled", HTTPStatus.FORBIDDEN)
            locked_until = _parse_time(row["locked_until"])
            if locked_until and locked_until > datetime.now(timezone.utc):
                raise AuthError("Too many failed attempts. Try again later", "account_locked", HTTPStatus.TOO_MANY_REQUESTS)
            try:
                PASSWORD_HASHER.verify(row["password_hash"], password)
            except (VerifyMismatchError, VerificationError, InvalidHashError):
                failures = int(row["failed_attempts"]) + 1
                lock_until = datetime.now(timezone.utc) + timedelta(minutes=LOCKOUT_MINUTES) if failures >= MAX_FAILED_ATTEMPTS else None
                connection.execute(
                    "UPDATE app_users SET failed_attempts = ?, locked_until = ?, updated_at = ? WHERE user_id = ?",
                    (0 if lock_until else failures, lock_until.isoformat(timespec="seconds") if lock_until else None, _now(), user.user_id),
                )
                self._audit(connection, user.user_id, user.user_id, "login-failed", {"locked": bool(lock_until)})
                connection.commit()
                if lock_until:
                    raise AuthError("Too many failed attempts. Account locked for 15 minutes", "account_locked", HTTPStatus.TOO_MANY_REQUESTS)
                raise _invalid_credentials()
            now = _now()
            password_hash = PASSWORD_HASHER.hash(password) if PASSWORD_HASHER.check_needs_rehash(row["password_hash"]) else row["password_hash"]
            # Rehash only if the password is still the one just verified, so a
            # password change that commits meanwhile is never overwritten.
            connection.execute(
                "UPDATE app_users SET password_hash = CASE WHEN password_hash = ? THEN ? ELSE password_hash END, "
                "failed_attempts = 0, locked_until = NULL, last_login_at = ?, updated_at = ? WHERE user_id = ?",
                (row["password_hash"], password_hash, now, now, user.user_id),
            )
            self._audit(connection, user.user_id, user.user_id, "login", {})
        user = self.get_user(user.user_id)
        return user, self._issue_session(user.user_id, window_id)

    def authenticate(self, token: str | None, window_id: str | None = None, *, touch: bool = True) -> AuthUser | None:
        if not token:
            return None
        digest = _digest(token)
        now = datetime.now(timezone.utc)
        window_id = _window_id(window_id)
        with self._lock:
            session = self._sessions.get(digest)
            if session is None:
                return None
            if window_id and window_id in self._ended_windows and session.window_id != window_id:
                # The browser shares one cookie across windows; a newer sign-in
                # elsewhere ended this window's session even though the cookie is live.
                return None
            if session.expires_at <= now:
                self._end_session(digest, "expired")
                return None
            if now - session.last_seen_at > timedelta(minutes=SESSION_IDLE_MINUTES):
                self._end_session(digest, "idle_timeout")
                return None
            if touch:
                session.last_seen_at = now
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM app_users WHERE user_id = ?", (session.user_id,)).fetchone()
        if row is None:
            with self._lock:
                self._end_session(digest, "account_removed")
            return None
        user = _user_from_row(row)
        if session.password_stamp is not None and session.password_stamp != _digest(row["password_hash"]):
            # Another process (the emergency reset command) replaced the password.
            with self._lock:
                self._end_session(digest, "password_reset")
            return None
        if user.disabled:
            with self._lock:
                self._end_session(digest, "account_disabled")
            return None
        return user

    def session_end_reason(self, token: str | None, window_id: str | None = None) -> str | None:
        """Return why this token's session ended, if it ended recently."""
        window_id = _window_id(window_id)
        with self._lock:
            if window_id and window_id in self._ended_windows:
                return self._ended_windows[window_id]
            if not token:
                return None
            return self._ended_sessions.get(_digest(token))

    def use_window(self, token: str | None, window_id: str | None, *, claim: bool = False) -> str:
        """Return this window's state: active, in_use, replaced, or none."""
        window_id = _window_id(window_id)
        if not token or not window_id:
            return "none"
        now = datetime.now(timezone.utc)
        with self._lock:
            session = self._sessions.get(_digest(token))
            if session is None:
                return "none"
            owner_closed = (
                session.window_id is None
                or session.window_seen_at is None
                or now - session.window_seen_at > timedelta(seconds=WINDOW_STALE_SECONDS)
            )
            if claim or owner_closed or session.window_id == window_id:
                if session.window_id and session.window_id != window_id:
                    session.replaced_windows = [*session.replaced_windows[-15:], session.window_id]
                session.replaced_windows = [item for item in session.replaced_windows if item != window_id]
                session.window_id = window_id
                session.window_seen_at = now
                return "active"
            return "replaced" if window_id in session.replaced_windows else "in_use"

    def release_window(self, token: str | None, window_id: str | None) -> None:
        window_id = _window_id(window_id)
        if not token or not window_id:
            return
        with self._lock:
            session = self._sessions.get(_digest(token))
            if session is not None and session.window_id == window_id:
                session.window_id = None
                session.window_seen_at = None

    def logout(self, token: str | None) -> None:
        if token:
            with self._lock:
                digest = _digest(token)
                self._sessions.pop(digest, None)
                self._ended_sessions.pop(digest, None)

    def get_user(self, user_id: str) -> AuthUser:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM app_users WHERE user_id = ?", (user_id,)).fetchone()
        if row is None:
            raise AuthError("Unknown account", "account_not_found", HTTPStatus.NOT_FOUND)
        return _user_from_row(row)

    def list_users(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM app_users ORDER BY username_norm").fetchall()
        return [_user_from_row(row).as_dict() for row in rows]

    def create_user(self, actor: AuthUser, username: str, display_name: str, password: str, roles: list[str]) -> dict[str, Any]:
        username, normalized = _validate_username(username)
        display_name = _validate_display_name(display_name, username)
        _validate_password(password, username)
        roles = _validate_roles(roles)
        user_id, now = str(uuid.uuid4()), _now()
        try:
            with self._connect() as connection:
                connection.execute(
                    """INSERT INTO app_users(
                        user_id, username, username_norm, display_name, password_hash, roles,
                        disabled, failed_attempts, locked_until, created_at, updated_at, last_login_at,
                        must_change_password
                    ) VALUES (?, ?, ?, ?, ?, ?, 0, 0, NULL, ?, ?, NULL, 1)""",
                    (user_id, username, normalized, display_name, PASSWORD_HASHER.hash(password), json.dumps(roles), now, now),
                )
                self._audit(connection, actor.user_id, user_id, "account-created", {"roles": roles})
        except Exception as exc:
            if "UNIQUE constraint failed" in str(exc):
                raise AuthError("That username is already in use", "username_exists", HTTPStatus.CONFLICT) from exc
            raise
        return self.get_user(user_id).as_dict()

    def update_user(self, actor: AuthUser, user_id: str, display_name: str, roles: list[str], disabled: bool) -> dict[str, Any]:
        target = self.get_user(user_id)
        display_name = _validate_display_name(display_name, target.username)
        roles = _validate_roles(roles)
        with self._connect() as connection:
            if "administrator" in target.roles and (disabled or "administrator" not in roles) and self._enabled_admin_count(connection) <= 1:
                raise AuthError("At least one enabled administrator must remain", "last_administrator", HTTPStatus.CONFLICT)
            connection.execute(
                "UPDATE app_users SET display_name = ?, roles = ?, disabled = ?, updated_at = ? WHERE user_id = ?",
                (display_name, json.dumps(roles), int(disabled), _now(), user_id),
            )
            self._audit(connection, actor.user_id, user_id, "account-updated", {"roles": roles, "disabled": disabled})
        if disabled and not target.disabled:
            reason = "account_disabled"
        elif sorted(roles) != sorted(target.roles):
            reason = "access_changed"
        else:
            reason = "account_updated"
        self._revoke_user_sessions(user_id, reason)
        return self.get_user(user_id).as_dict()

    def reset_password(self, actor: AuthUser, user_id: str, password: str) -> None:
        target = self.get_user(user_id)
        _validate_password(password, target.username)
        with self._connect() as connection:
            connection.execute(
                "UPDATE app_users SET password_hash = ?, failed_attempts = 0, locked_until = NULL, must_change_password = 1, updated_at = ? WHERE user_id = ?",
                (PASSWORD_HASHER.hash(password), _now(), user_id),
            )
            self._audit(connection, actor.user_id, user_id, "password-reset", {})
        self._revoke_user_sessions(user_id, "password_reset")

    def change_password(self, user: AuthUser, current_password: str, new_password: str) -> None:
        _validate_password(new_password, user.username)
        with self._connect() as connection:
            row = connection.execute("SELECT password_hash FROM app_users WHERE user_id = ?", (user.user_id,)).fetchone()
            try:
                PASSWORD_HASHER.verify(row["password_hash"], current_password)
            except (VerifyMismatchError, VerificationError, InvalidHashError) as exc:
                raise AuthError("Current password is incorrect", "invalid_current_password", HTTPStatus.UNAUTHORIZED) from exc
            connection.execute(
                "UPDATE app_users SET password_hash = ?, must_change_password = 0, updated_at = ? WHERE user_id = ?",
                (PASSWORD_HASHER.hash(new_password), _now(), user.user_id),
            )
            self._audit(connection, user.user_id, user.user_id, "password-changed", {})
        self._revoke_user_sessions(user.user_id, "password_changed")

    def set_required_password(self, user: AuthUser, token: str | None, new_password: str) -> AuthUser:
        """Replace an administrator-set password; the current session continues."""
        _validate_password(new_password, user.username)
        with self._connect() as connection:
            row = connection.execute("SELECT password_hash, must_change_password FROM app_users WHERE user_id = ?", (user.user_id,)).fetchone()
            if row is None or not row["must_change_password"]:
                raise AuthError("This account does not need a new password", "password_change_not_required", HTTPStatus.CONFLICT)
            try:
                PASSWORD_HASHER.verify(row["password_hash"], new_password)
            except (VerifyMismatchError, VerificationError, InvalidHashError):
                pass
            else:
                raise AuthError("Choose a password different from the one the administrator set", "password_reused", HTTPStatus.UNPROCESSABLE_ENTITY)
            connection.execute(
                "UPDATE app_users SET password_hash = ?, must_change_password = 0, updated_at = ? WHERE user_id = ?",
                (PASSWORD_HASHER.hash(new_password), _now(), user.user_id),
            )
            self._audit(connection, user.user_id, user.user_id, "required-password-set", {})
            stamp = _digest(connection.execute("SELECT password_hash FROM app_users WHERE user_id = ?", (user.user_id,)).fetchone()["password_hash"])
        keep = _digest(token) if token else None
        with self._lock:
            for digest, session in list(self._sessions.items()):
                if session.user_id == user.user_id and digest != keep:
                    self._end_session(digest, "password_changed")
                elif digest == keep:
                    session.password_stamp = stamp
        return self.get_user(user.user_id)

    def emergency_reset_administrator(self, username: str, new_password: str) -> AuthUser:
        _, normalized = _validate_username(username)
        _validate_password(new_password, username)
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM app_users WHERE username_norm = ?", (normalized,)).fetchone()
            if row is None or "administrator" not in _roles(row["roles"]):
                raise AuthError("That account is not an administrator", "administrator_not_found", HTTPStatus.NOT_FOUND)
            user = _user_from_row(row)
            connection.execute(
                "UPDATE app_users SET password_hash = ?, disabled = 0, failed_attempts = 0, locked_until = NULL, must_change_password = 0, updated_at = ? WHERE user_id = ?",
                (PASSWORD_HASHER.hash(new_password), _now(), user.user_id),
            )
            self._audit(connection, None, user.user_id, "os-custodian-password-reset", {})
        self._revoke_user_sessions(user.user_id, "password_reset")
        return self.get_user(user.user_id)

    def role_catalog(self) -> list[dict[str, Any]]:
        return [{"role": role, "description": ROLE_DESCRIPTIONS[role], "capabilities": sorted(capabilities)} for role, capabilities in ROLE_CAPABILITIES.items()]

    def recovery_risk_acknowledgement(self) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT value FROM app_settings WHERE key = ?",
                (RECOVERY_RISK_SETTING,),
            ).fetchone()
        if row is None:
            return None
        try:
            value = json.loads(row["value"])
        except (TypeError, json.JSONDecodeError):
            return None
        return value if isinstance(value, dict) else None

    def acknowledge_recovery_risk(
        self,
        actor: AuthUser,
        acknowledgement_version: str,
    ) -> dict[str, Any]:
        if not actor.has("recovery"):
            raise AuthError(
                "Only an administrator may accept the machine-wide disaster-recovery risk",
                "permission_denied",
                HTTPStatus.FORBIDDEN,
            )
        if acknowledgement_version != RECOVERY_RISK_ACKNOWLEDGEMENT_VERSION:
            raise AuthError(
                "The disaster-recovery acknowledgement is missing or out of date",
                "acknowledgement_required",
                HTTPStatus.UNPROCESSABLE_ENTITY,
            )
        acknowledgement = {
            "version": RECOVERY_RISK_ACKNOWLEDGEMENT_VERSION,
            "acknowledged_at": _now(),
            "acknowledged_by_user_id": actor.user_id,
            "acknowledged_by": actor.display_name or actor.username,
        }
        encoded = json.dumps(acknowledgement, sort_keys=True, separators=(",", ":"))
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO app_settings(key, value, updated_at, updated_by_user_id)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(key) DO UPDATE SET
                       value = excluded.value,
                       updated_at = excluded.updated_at,
                       updated_by_user_id = excluded.updated_by_user_id""",
                (
                    RECOVERY_RISK_SETTING,
                    encoded,
                    acknowledgement["acknowledged_at"],
                    actor.user_id,
                ),
            )
            self._audit(
                connection,
                actor.user_id,
                actor.user_id,
                "disaster-recovery-risk-acknowledged",
                {"version": RECOVERY_RISK_ACKNOWLEDGEMENT_VERSION},
            )
        return acknowledgement
    def _issue_session(self, user_id: str, window_id: str | None = None) -> str:
        """Start the only session; one operator uses SentriFace at a time."""
        token, now = secrets.token_urlsafe(32), datetime.now(timezone.utc)
        window_id = _window_id(window_id)
        with self._connect() as connection:
            row = connection.execute("SELECT password_hash FROM app_users WHERE user_id = ?", (user_id,)).fetchone()
        stamp = _digest(row["password_hash"]) if row is not None else None
        with self._lock:
            for digest, session in list(self._sessions.items()):
                for ended_window in (session.window_id, *session.replaced_windows):
                    if ended_window and ended_window != window_id:
                        self._ended_windows.pop(ended_window, None)
                        self._ended_windows[ended_window] = "signed_in_elsewhere"
                self._end_session(digest, "signed_in_elsewhere")
            while len(self._ended_windows) > MAX_ENDED_WINDOWS:
                self._ended_windows.pop(next(iter(self._ended_windows)))
            if window_id:
                self._ended_windows.pop(window_id, None)
            self._sessions[_digest(token)] = _Session(
                user_id, now + timedelta(hours=SESSION_HOURS), now,
                window_id=window_id, window_seen_at=now if window_id else None,
                password_stamp=stamp,
            )
        return token

    def _revoke_user_sessions(self, user_id: str, reason: str) -> None:
        with self._lock:
            for digest, session in list(self._sessions.items()):
                if session.user_id == user_id:
                    self._end_session(digest, reason)

    def _end_session(self, digest: str, reason: str) -> None:
        # Callers hold self._lock.
        self._sessions.pop(digest, None)
        self._ended_sessions.pop(digest, None)
        self._ended_sessions[digest] = reason
        while len(self._ended_sessions) > MAX_ENDED_SESSIONS:
            self._ended_sessions.pop(next(iter(self._ended_sessions)))

    @staticmethod
    def _enabled_admin_count(connection) -> int:
        rows = connection.execute("SELECT roles FROM app_users WHERE disabled = 0").fetchall()
        return sum("administrator" in _roles(row["roles"]) for row in rows)

    @staticmethod
    def _audit(connection, actor_id: str | None, target_id: str | None, action: str, details: dict[str, Any]) -> None:
        connection.execute(
            "INSERT INTO auth_audit(audit_id, actor_user_id, target_user_id, action, details, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), actor_id, target_id, action, json.dumps(details, sort_keys=True, separators=(",", ":")), _now()),
        )

    def _dummy_verify(self, password: str) -> None:
        try:
            PASSWORD_HASHER.verify(self._dummy_hash, password)
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            pass

    @contextmanager
    def _connect(self):
        connection = connect_database(self.db_path, self.database_key, timeout=30, row_factory=True)
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()


def session_ended_payload(service: AuthService, token: str | None, window_id: str | None = None) -> dict[str, str] | None:
    reason = service.session_end_reason(token, window_id)
    if reason is None:
        return None
    return {"reason": reason, "message": SESSION_END_MESSAGES.get(reason, "Your session ended. Sign in again to continue.")}


def auth_status_payload(
    service: AuthService,
    user: AuthUser | None,
    token: str | None = None,
    window_id: str | None = None,
    window: str = "none",
) -> dict[str, Any]:
    return {
        "session_ended": None if user is not None else session_ended_payload(service, token, window_id),
        "window": window if user is not None else "none",
        "window_heartbeat_seconds": WINDOW_HEARTBEAT_SECONDS,
        "setup_required": service.setup_required(),
        "authenticated": user is not None,
        "user": user.as_dict() if user else None,
        "roles": service.role_catalog(),
        "session_idle_minutes": SESSION_IDLE_MINUTES,
        "session_hours": SESSION_HOURS,
    }


def _validate_username(value: str) -> tuple[str, str]:
    username = str(value or "").strip()
    if not USERNAME_PATTERN.fullmatch(username):
        raise AuthError("Username must be 3-64 characters using letters, numbers, dot, underscore, or hyphen", "invalid_username", HTTPStatus.UNPROCESSABLE_ENTITY)
    return username, username.casefold()


def _validate_display_name(value: str, fallback: str) -> str:
    display_name = str(value or "").strip() or fallback
    if len(display_name) > 80 or any(ord(character) < 32 for character in display_name):
        raise AuthError("Display name must be at most 80 printable characters", "invalid_display_name", HTTPStatus.UNPROCESSABLE_ENTITY)
    return display_name


def _validate_password(password: str, username: str) -> None:
    if not isinstance(password, str) or not 12 <= len(password) <= 256:
        raise AuthError("Password must be between 12 and 256 characters", "weak_password", HTTPStatus.UNPROCESSABLE_ENTITY)
    if password.casefold() == username.casefold():
        raise AuthError("Password must not match the username", "weak_password", HTTPStatus.UNPROCESSABLE_ENTITY)


def _validate_roles(value: list[str]) -> list[str]:
    if not isinstance(value, list):
        raise AuthError("Roles must be a list", "invalid_roles", HTTPStatus.UNPROCESSABLE_ENTITY)
    roles = sorted({str(role).strip().casefold() for role in value})
    if not roles or any(role not in ROLE_CAPABILITIES for role in roles):
        raise AuthError("Choose at least one recognized role", "invalid_roles", HTTPStatus.UNPROCESSABLE_ENTITY)
    return roles


def _user_from_row(row) -> AuthUser:
    return AuthUser(
        row["user_id"], row["username"], row["display_name"], tuple(_roles(row["roles"])), bool(row["disabled"]),
        row["created_at"], row["updated_at"], row["last_login_at"], bool(row["must_change_password"]),
    )


def _window_id(value: str | None) -> str | None:
    value = str(value or "")
    return value if WINDOW_ID_PATTERN.fullmatch(value) else None


def _roles(value: str) -> list[str]:
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        parsed = []
    return sorted({str(role) for role in parsed if str(role) in ROLE_CAPABILITIES})


def _invalid_credentials() -> AuthError:
    return AuthError("Username or password is incorrect", "invalid_credentials", HTTPStatus.UNAUTHORIZED)


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None
