"""
JWT authentication utilities for OpenMNC backend.
"""

import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from dotenv import load_dotenv
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

load_dotenv()

JWT_SECRET: str = os.getenv("JWT_SECRET", "changeme-super-secret")
JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRE_HOURS: int = int(os.getenv("JWT_EXPIRE_HOURS", "24"))
ADMIN_EMAIL: str = os.getenv("ADMIN_EMAIL", "amit@openmnc.com")
ADMIN_PASSWORD_HASH: str = os.getenv("ADMIN_PASSWORD_HASH", "")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain-text password against its bcrypt hash."""
    try:
        import bcrypt
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except Exception:
        return pwd_context.verify(plain_password, hashed_password)


def hash_password(plain_password: str) -> str:
    """Hash a plain-text password with bcrypt."""
    try:
        import bcrypt
        return bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    except Exception:
        return pwd_context.hash(plain_password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a signed JWT access token."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta if expires_delta else timedelta(hours=JWT_EXPIRE_HOURS)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    """Decode and validate a JWT token payload."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        email: str | None = payload.get("sub")
        if email is None:
            raise credentials_exception
        return payload
    except JWTError:
        raise credentials_exception


def verify_token(token: str) -> str:
    """Returns the email (sub) from JWT token."""
    payload = decode_token(token)
    return payload["sub"]


async def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    """
    Extracts authenticated user email and verified role from token and DB.
    Roles: 'admin' (tier 1), 'editor' (tier 2), 'author' (tier 3)
    """
    payload = decode_token(token)
    email = payload.get("sub", "").lower()
    token_role = payload.get("role")

    # Primary owner is always admin
    if email == ADMIN_EMAIL.lower():
        return {"email": email, "role": "admin", "is_owner": True}

    from database import get_collection
    try:
        team_col = get_collection("team_members")
        member = await team_col.find_one({"_id": email})
        if member:
            if member.get("status") == "revoked":
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Your team access has been revoked. Contact the administrator."
                )
            return {
                "email": email,
                "role": member.get("role", token_role or "editor"),
                "is_owner": False,
                "name": member.get("name", ""),
            }

        # Check authorized_staff list for backwards compatibility
        settings_col = get_collection("site_settings")
        staff_doc = await settings_col.find_one({"_id": "authorized_staff"})
        if staff_doc:
            allowed_list = [s.lower() for s in staff_doc.get("emails", [])]
            if email in allowed_list:
                return {"email": email, "role": token_role or "editor", "is_owner": False}
    except HTTPException:
        raise
    except Exception:
        pass

    if token_role in ["admin", "editor", "author"]:
        return {"email": email, "role": token_role, "is_owner": False}

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Unauthorized account. Please accept an administrator invitation.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def require_role(allowed_roles: list[str]):
    """Factory dependency enforcing RBAC role checks."""
    async def role_checker(user: dict = Depends(get_current_user)) -> dict:
        if user["role"] not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied: {', '.join(allowed_roles)} privileges required (your role: {user['role']}).",
            )
        return user
    return role_checker


# Tier 1: Admin only (Team invitations, site settings, system configs)
require_admin = require_role(["admin"])

# Tier 2: Editor & Admin (Full business operations: blogs, services, careers, applicants, leads)
require_editor = require_role(["admin", "editor"])

# Tier 3: Author, Editor & Admin (Content creation: blogs and services)
require_author = require_role(["admin", "editor", "author"])


async def get_current_admin(token: str = Depends(oauth2_scheme)) -> str:
    """FastAPI dependency returning current authorized user email string."""
    user = await get_current_user(token)
    return user["email"]
