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


def verify_token(token: str) -> str:
    """
    Decode and validate a JWT token.
    Returns the email (sub) on success, raises HTTPException on failure.
    """
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
        return email
    except JWTError:
        raise credentials_exception


async def get_current_admin(token: str = Depends(oauth2_scheme)) -> str:
    """
    FastAPI dependency — extracts and validates admin JWT.
    Raises HTTP 401 if invalid.
    """
    email = verify_token(token)
    if email.lower() != ADMIN_EMAIL.lower():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin access only",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return email
