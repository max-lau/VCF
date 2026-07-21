"""
auth.py
=======
FastAPI APIRouter: User Authentication (#11)
JWT-based authentication with bcrypt password hashing.
Endpoints:
  POST /auth/register       - create account
  POST /auth/login          - get JWT token + permission snapshot
  GET  /auth/me             - get current user info
  GET  /auth/me/permissions - get role + module permissions (Vue frontend)
  POST /auth/refresh        - refresh token
  PUT  /auth/password       - change password
  GET  /auth/users          - list all users (admin only)

Users stored in Supabase Postgres (users table).
Token expiry: 24 hours (configurable via .env JWT_EXPIRE_HOURS).
"""

import bcrypt
import os
import uuid
import logging
import psycopg2
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import Optional
import jwt
from backend.demo1.pg import get_conn

logger = logging.getLogger(__name__)

router = APIRouter()
bearer = HTTPBearer(auto_error=False)

# ---------------------------------------------------------------------------
# In-memory login rate limiter: 5 failures per IP per 15 min -> 429
# ---------------------------------------------------------------------------
from collections import defaultdict
import threading as _threading
_login_failures: dict = defaultdict(list)
_login_lock = _threading.Lock()
_RATE_LIMIT_MAX    = 5
_RATE_LIMIT_WINDOW = 900  # seconds

def _check_rate_limit(ip: str):
    now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).timestamp()
    with _login_lock:
        _login_failures[ip] = [t for t in _login_failures[ip] if now - t < _RATE_LIMIT_WINDOW]
        if len(_login_failures[ip]) >= _RATE_LIMIT_MAX:
            raise HTTPException(429, "Too many failed login attempts. Try again in 15 minutes.")

def _record_failure(ip: str):
    now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).timestamp()
    with _login_lock:
        _login_failures[ip].append(now)

def _clear_failures(ip: str):
    with _login_lock:
        _login_failures.pop(ip, None)


# ── Config ─────────────────────────────────────────────────────────────────────
SECRET_KEY   = os.getenv("JWT_SECRET_KEY", "")
ALGORITHM    = "HS256"
EXPIRE_HOURS = int(os.getenv("JWT_EXPIRE_HOURS", "24"))

# ── Role → tier mapping ────────────────────────────────────────────────────────
ROLE_TIER_MAP = {
    "paraiq_super":    0,
    "firm_admin":      1,
    "admin":           1,
    "senior_attorney": 2,
    "associate":       3,
    "user":            3,
    "paralegal":       4,
    "client_viewer":   5,
    "billing_contact": 6,
}

SCOPED_ROLES = {"paralegal", "client_viewer"}

# System-level firm_id for DDL and cross-firm auth lookups (users table has no RLS).
# Using this constant instead of the literal "default" keeps the audit grep clean
# and makes intentional system-level access explicit.
SYSTEM_FIRM = "default"


# ── DB Setup ───────────────────────────────────────────────────────────────────

def init_auth_table():
    """Create token_blocklist table if not exists (idempotent)."""
    try:
        with get_conn(SYSTEM_FIRM) as conn:  # DDL — not tenant-scoped
            conn.execute("""
                CREATE TABLE IF NOT EXISTS token_blocklist (
                    jti         TEXT PRIMARY KEY,
                    firm_id     TEXT NOT NULL DEFAULT 'default',
                    user_id     INTEGER,
                    blocked_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    expires_at  TIMESTAMPTZ
                )
            """)
        print("[Auth] Users + token_blocklist tables initialized ✓")
    except (psycopg2.Error, OSError) as e:
        logger.warning(f"[Auth] Table init skipped (non-fatal): {e}")


# ── Password helpers ───────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


# ── Permissions helper ─────────────────────────────────────────────────────────

def build_permissions_for_user(user_id: int, firm_id: str = "default") -> dict:
    """
    Builds the permission snapshot for the Vue frontend.
    Looks up role_assignments + module_permissions tables.
    Falls back gracefully if no assignment found.
    """
    try:
        with get_conn(firm_id) as conn:
            # Check if role_assignments table exists to prevent crashes
            table_exists = conn.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE  table_schema = 'public'
                    AND    table_name   = 'role_assignments'
                );
            """).fetchone()["exists"]

            if not table_exists:
                # Fallback directly to users table
                user_row = conn.execute(
                    "SELECT role FROM users WHERE id = %s", (user_id,)
                ).fetchone()
                legacy    = user_row["role"] if user_row else "associate"
                role_name = legacy if legacy in ROLE_TIER_MAP or legacy in ("firm_admin", "admin") else "associate"
                tier      = 1 if role_name in ("firm_admin", "admin") else ROLE_TIER_MAP.get(role_name, 3)
                modules   = {}
            else:
                row = conn.execute("""
                    SELECT r.name AS role_name, r.tier, r.default_open
                    FROM role_assignments ra
                    JOIN roles r ON r.id = ra.role_id
                    WHERE ra.user_id = %s AND ra.firm_id = %s
                """, (user_id, firm_id)).fetchone()

                if not row:
                    user_row = conn.execute(
                        "SELECT role FROM users WHERE id = %s", (user_id,)
                    ).fetchone()
                    legacy    = user_row["role"] if user_row else "associate"
                    role_name = legacy if legacy in ROLE_TIER_MAP or legacy in ("firm_admin", "admin") else "associate"
                    tier      = 1 if role_name in ("firm_admin", "admin") else ROLE_TIER_MAP.get(role_name, 3)
                    modules   = {}
                else:
                    role_name = row["role_name"]
                    tier      = row["tier"]

                    module_rows = conn.execute("""
                        SELECT mp.module, mp.can_read, mp.can_write,
                               mp.can_delete, mp.can_export, mp.can_admin
                        FROM module_permissions mp
                        WHERE mp.role_id = (
                            SELECT role_id FROM role_assignments
                            WHERE user_id = %s AND firm_id = %s
                        )
                    """, (user_id, firm_id)).fetchall()

                    modules = {
                        r["module"]: {
                            "read":   r["can_read"],
                            "write":  r["can_write"],
                            "delete": r["can_delete"],
                            "export": r["can_export"],
                            "admin":  r["can_admin"],
                        }
                        for r in module_rows
                    }

        return {
            "role":      role_name,
            "tier":      tier,
            "is_scoped": role_name in SCOPED_ROLES,
            "modules":   modules,
        }

    except (psycopg2.Error, KeyError, ValueError) as e:
        logger.warning(f"[Auth] Permissions lookup failed for user_id={user_id}, failing open to associate: {e}")
        return {
            "role":      "associate",
            "tier":      3,
            "is_scoped": False,
            "modules":   {},
        }

# ── JWT helpers ────────────────────────────────────────────────────────────────

def create_token(user_id: int, username: str, role: str, firm_id: str = "default") -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=EXPIRE_HOURS)
    if role == "guest_trial":
        firm_id = f"trial_{user_id}"
    payload = {
        "sub":      str(user_id),
        "username": username,
        "role":     role,
        "firm_id":  firm_id,
        "exp":      expire,
        "iat":      datetime.now(timezone.utc),
        "jti":      str(uuid.uuid4()),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def get_current_firm_id(credentials: HTTPAuthorizationCredentials = Depends(bearer)) -> str:
    """
    FastAPI dependency — extracts firm_id from JWT.
    Inject into any endpoint that must be tenant-scoped:

        @router.get("/cases/search")
        def search(firm_id: str = Depends(get_current_firm_id)): ...
    """
    if not credentials:
        raise HTTPException(401, "Authentication required")
    payload = decode_token(credentials.credentials)
    return payload.get("firm_id", "default")


def decode_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        jti = payload.get("jti")
        if jti:
            with get_conn(SYSTEM_FIRM) as conn:  # blocklist — cross-firm lookup
                row = conn.execute(
                    "SELECT 1 FROM token_blocklist WHERE jti=%s", (jti,)
                ).fetchone()
                if row:
                    raise HTTPException(401, "Token has been revoked")
        return payload
    except HTTPException:
        raise
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Token has expired")
    except jwt.InvalidTokenError as e:
        raise HTTPException(401, f"Invalid token: {e}")
    except (psycopg2.Error, KeyError, ValueError) as e:
        logger.warning(f"[Auth] Blocklist check failed, failing open: {e}")
        return payload


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer)) -> dict:
    """Dependency — inject into any endpoint to require authentication."""
    if not credentials:
        raise HTTPException(401, "Authentication required. Pass Bearer token.")
    payload = decode_token(credentials.credentials)
    user_id = int(payload.get("sub", 0))

    with get_conn(SYSTEM_FIRM) as conn:  # users table — cross-firm auth lookup
        user = conn.execute(
            "SELECT id, username, email, role, firm_id, active, created_at, last_login FROM users WHERE id = %s",
            (user_id,)
        ).fetchone()

    if not user:
        raise HTTPException(401, "User not found")
    if not user["active"]:
        raise HTTPException(403, "Account is deactivated")

    return dict(user)


def require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    """Dependency — require admin role."""
    if current_user.get("role") not in ("admin", "firm_admin", "paraiq_super"):
        raise HTTPException(403, "Admin access required")
    return current_user


def require_super(current_user: dict = Depends(get_current_user)) -> dict:
    """Dependency — require paraiq_super (cross-tenant/system data)."""
    if current_user.get("role") != "paraiq_super":
        raise HTTPException(403, "Super-admin access required")
    return current_user


# ── Pydantic models ────────────────────────────────────────────────────────────

class RegisterBody(BaseModel):
    firm_id:  str = "default"
    username: str
    email:    str
    password: str
    role:     Optional[str] = "user"

class LoginBody(BaseModel):
    username: str
    password: str

class ChangePasswordBody(BaseModel):
    current_password: str
    new_password:     str


# ── Routes ─────────────────────────────────────────────────────────────────────

@router.post("/register")
def register(body: RegisterBody):
    """Create a new user account."""
    if len(body.password) < 8:
        raise HTTPException(400, "Password must be at least 8 characters")
    if len(body.username) < 3:
        raise HTTPException(400, "Username must be at least 3 characters")
    if "@" not in body.email:
        raise HTTPException(400, "Invalid email address")

    hashed  = hash_password(body.password)
    firm_id = body.firm_id or "default"

    with get_conn(firm_id) as conn:  # register — tenant-scoped
        existing = conn.execute(
            "SELECT id FROM users WHERE username = %s OR email = %s",
            (body.username, body.email)
        ).fetchone()
        if existing:
            raise HTTPException(409, "Username or email already registered")

        cur = conn.execute("""
            INSERT INTO users (username, email, password_hash, role, created_at, firm_id)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            body.username, body.email, hashed,
            body.role if body.role in ("user", "admin") else "user",
            datetime.now(timezone.utc).isoformat(),
            firm_id,
        ))
        user_id = cur.fetchone()["id"]

    token = create_token(user_id, body.username, "user", firm_id)

    return {
        "success":          True,
        "message":          f"Account created for '{body.username}'",
        "user_id":          user_id,
        "username":         body.username,
        "token":            token,
        "expires_in_hours": EXPIRE_HOURS,
    }


@router.post("/login")
def login(body: LoginBody, request: Request):
    """Authenticate and receive a JWT token + permission snapshot."""
    ip = request.client.host if request.client else "unknown"
    _check_rate_limit(ip)
    with get_conn(SYSTEM_FIRM) as conn:  # login — cross-firm user lookup
        user = conn.execute(
            "SELECT * FROM users WHERE (username = %s OR email = %s) AND active = TRUE",
            (body.username, body.username)
        ).fetchone()

        if not user or not verify_password(body.password, user["password_hash"]):
            _record_failure(ip)
            raise HTTPException(401, "Invalid username or password")

        _clear_failures(ip)
        conn.execute(
            "UPDATE users SET last_login = %s WHERE id = %s",
            (datetime.now(timezone.utc).isoformat(), user["id"])
        )

    user      = dict(user)
    firm_id   = user["firm_id"] if user["firm_id"] else "default"
    token     = create_token(user["id"], user["username"], user["role"], firm_id)
    if user["role"] == "guest_trial":
        firm_id = f"trial_{user['id']}"
    # For guest_trial users, create_token overrides firm_id to trial_{user_id}
    if user["role"] == "guest_trial":
        firm_id = f"trial_{user['id']}"
    perms     = build_permissions_for_user(user["id"], firm_id)

    return {
        "success":          True,
        "token":            token,
        "token_type":       "bearer",
        "username":         user["username"],
        "expires_in_hours": EXPIRE_HOURS,
        "user_id":          user["id"],
        "email":            user["email"],
        "role":             perms["role"],
        "tier":             perms["tier"],
        "firm_id":          firm_id,
        "permissions":      perms,
    }


@router.get("/me")
def get_me(current_user: dict = Depends(get_current_user)):
    """Get current authenticated user info."""
    return {
        "success": True,
        "user": {
            "id":         current_user["id"],
            "username":   current_user["username"],
            "email":      current_user["email"],
            "role":       current_user["role"],
            "created_at": current_user["created_at"],
            "last_login": current_user["last_login"],
        }
    }


@router.get("/me/permissions")
def get_my_permissions(current_user: dict = Depends(get_current_user)):
    """
    Returns the full permission snapshot for the current user.
    Called by the Vue frontend on app mount when token already exists.
    """
    return build_permissions_for_user(current_user["id"], current_user.get("firm_id", "default"))


@router.post("/refresh")
def refresh_token(current_user: dict = Depends(get_current_user)):
    """Issue a fresh token for the current user."""
    token = create_token(
        current_user["id"],
        current_user["username"],
        current_user["role"],
        current_user.get("firm_id", "default"),
    )
    return {
        "success":          True,
        "token":            token,
        "expires_in_hours": EXPIRE_HOURS,
    }


@router.post("/logout")
def logout(credentials: HTTPAuthorizationCredentials = Depends(bearer),
           current_user: dict = Depends(get_current_user)):
    """Invalidate the current JWT by adding its jti to the blocklist."""
    payload = decode_token(credentials.credentials)
    jti = payload.get("jti")
    if not jti:
        return {"success": True, "message": "Logged out"}
    expires_at = payload.get("exp")
    from datetime import datetime, timezone
    expires_dt = datetime.fromtimestamp(expires_at, tz=timezone.utc)
    with get_conn(current_user.get("firm_id", "default")) as conn:  # logout — tenant-scoped blocklist
        conn.execute(
            """INSERT INTO token_blocklist (jti, firm_id, user_id, expires_at)
               VALUES (%s, %s, %s, %s) ON CONFLICT (jti) DO NOTHING""",
            (jti, current_user.get("firm_id", "default"), current_user["id"], expires_dt)
        )
    return {"success": True, "message": "Logged out successfully"}

def purge_expired_blocklist() -> int:
    """Delete expired rows from token_blocklist. Called by scheduler daily at 03:00 UTC."""
    try:
        from backend.demo1.pg import get_conn
        from datetime import datetime, timezone
        with get_conn("default") as conn:  # noqa: intentional — DDL/maintenance, cross-firm
            cur = conn.execute(
                "DELETE FROM token_blocklist WHERE expires_at < %s",
                (datetime.now(timezone.utc),)
            )
            deleted = cur.rowcount if cur else 0
        logger.info(f"[Auth] Blocklist cleanup: {deleted} expired token(s) purged")
        return deleted
    except (psycopg2.Error, OSError, ValueError) as e:
        logger.error(f"[Auth] Blocklist cleanup failed: {e}")
        return 0


@router.put("/password")
def change_password(body: ChangePasswordBody,
                    current_user: dict = Depends(get_current_user)):
    """Change the current user's password."""
    if len(body.new_password) < 8:
        raise HTTPException(400, "New password must be at least 8 characters")

    with get_conn(current_user.get("firm_id", "default")) as conn:  # password change — tenant-scoped
        user = conn.execute(
            "SELECT password_hash FROM users WHERE id = %s", (current_user["id"],)
        ).fetchone()

        if not verify_password(body.current_password, user["password_hash"]):
            raise HTTPException(401, "Current password is incorrect")

        conn.execute(
            "UPDATE users SET password_hash = %s WHERE id = %s",
            (hash_password(body.new_password), current_user["id"])
        )

    return {"success": True, "message": "Password updated successfully"}


@router.get("/users")
def list_users(current_user: dict = Depends(require_admin)):
    """List all users — scoped to current firm."""
    firm_id = current_user.get("firm_id", "default")
    with get_conn(firm_id) as conn:
        rows = conn.execute(
            "SELECT id, username, email, role, active, created_at, last_login FROM users WHERE firm_id=%s ORDER BY id",
            (firm_id,)
        ).fetchall()
    return {
        "success": True,
        "count":   len(rows),
        "users":   [dict(r) for r in rows],
    }


# ── User Management Routes (Firm Admin) ────────────────────────────────────────

class UpdateRoleBody(BaseModel):
    role: str


@router.put("/users/{user_id}/active")
def toggle_user_active(user_id: int, current_user: dict = Depends(require_admin)):
    firm_id = current_user.get("firm_id", "default")
    with get_conn(firm_id) as conn:
        user = conn.execute(
            "SELECT active FROM users WHERE id = %s AND firm_id=%s", (user_id, firm_id)
        ).fetchone()
        if not user:
            raise HTTPException(404, "User not found")

        new_status = not user["active"]
        conn.execute(
            "UPDATE users SET active = %s WHERE id = %s AND firm_id=%s", (new_status, user_id, firm_id)
        )

    return {"success": True, "active": new_status}


@router.put("/users/{user_id}/role")
def update_user_role(user_id: int, body: UpdateRoleBody,
                     current_user: dict = Depends(require_admin)):
    """Update a user's role — scoped to current firm."""
    if body.role not in ROLE_TIER_MAP:
        raise HTTPException(400, f"Invalid role: {body.role}")
    firm_id = current_user.get("firm_id", "default")
    with get_conn(firm_id) as conn:
        user = conn.execute(
            "SELECT id FROM users WHERE id = %s AND firm_id=%s", (user_id, firm_id)
        ).fetchone()
        if not user:
            raise HTTPException(404, "User not found")
        conn.execute(
            "UPDATE users SET role = %s WHERE id = %s AND firm_id=%s", (body.role, user_id, firm_id)
        )
        try:
            role_row = conn.execute(
                "SELECT id FROM roles WHERE name = %s", (body.role,)
            ).fetchone()
            if role_row:
                existing = conn.execute(
                    "SELECT id FROM role_assignments WHERE user_id = %s AND firm_id = %s",
                    (user_id, firm_id)
                ).fetchone()
                if existing:
                    conn.execute(
                        "UPDATE role_assignments SET role_id = %s WHERE user_id = %s AND firm_id = %s",
                        (role_row["id"], user_id, firm_id)
                    )
                else:
                    conn.execute(
                        "INSERT INTO role_assignments (user_id, role_id, firm_id, assigned_at) VALUES (%s, %s, %s, %s)",
                        (user_id, role_row["id"], firm_id, datetime.now(timezone.utc).isoformat())
                    )
        except (psycopg2.Error, KeyError, ValueError) as e:
            logger.warning(f"[Auth] Role assignment sync failed for user_id={user_id} role={body.role}: {e}")
    return {"success": True, "role": body.role, "tier": ROLE_TIER_MAP.get(body.role, 3)}
