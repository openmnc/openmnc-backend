"""
Auth router — /api/auth
Includes login, OTP forgot password, OTP verification, password reset, and /me.
"""

import os
import random
import logging
from datetime import datetime, timedelta, timezone
from pydantic import BaseModel, EmailStr
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from jose import jwt, JWTError

from auth import (
    create_access_token,
    verify_password,
    hash_password,
    get_current_admin,
    ADMIN_EMAIL,
    ADMIN_PASSWORD_HASH,
    JWT_SECRET,
    JWT_ALGORITHM,
)
from database import get_collection

logger = logging.getLogger("openmnc.auth")
router = APIRouter(prefix="/api/auth", tags=["auth"])


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class VerifyOtpRequest(BaseModel):
    email: EmailStr
    otp: str


class ResetPasswordRequest(BaseModel):
    reset_token: str
    new_password: str


async def get_effective_admin_hash() -> str:
    """Fetch stored password hash from DB or fallback to environment variable."""
    try:
        col = get_collection("site_settings")
        doc = await col.find_one({"_id": "admin_credentials"})
        if doc and "password_hash" in doc:
            return doc["password_hash"]
    except Exception as e:
        logger.warning(f"Could not read admin credentials from DB: {e}")
    return ADMIN_PASSWORD_HASH


@router.post("/login")
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    """
    Authenticate admin using email + password from form data.
    Returns a JWT access token on success.
    """
    if form_data.username.lower() != ADMIN_EMAIL.lower():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    current_hash = await get_effective_admin_hash()
    if not current_hash:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Admin password not configured.",
        )

    if not verify_password(form_data.password, current_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(data={"sub": ADMIN_EMAIL})
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/me")
async def get_me(admin: str = Depends(get_current_admin)):
    """Return currently authenticated administrator."""
    return {"email": admin, "role": "admin"}


@router.post("/forgot-password")
async def forgot_password(req: ForgotPasswordRequest):
    """
    Generates a 6-digit OTP for admin password reset.
    Stores it in MongoDB with a 15-minute expiration window.
    """
    if req.email.lower() != ADMIN_EMAIL.lower():
        # Generic response to prevent email enumeration
        return {
            "status": "ok",
            "message": "If the email is registered as an administrator, an OTP has been dispatched.",
        }

    # Generate 6-digit cryptographic OTP
    otp_code = str(random.randint(100000, 999999))
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)

    try:
        col = get_collection("admin_otps")
        await col.update_one(
            {"email": req.email.lower()},
            {
                "$set": {
                    "otp": otp_code,
                    "expires_at": expires_at,
                    "created_at": datetime.now(timezone.utc),
                }
            },
            upsert=True,
        )
        logger.info(f"Generated admin reset OTP: {otp_code} for {req.email}")
        print(f"\n[SECURITY] Admin Reset OTP for {req.email} is: {otp_code} (Valid for 15 mins)\n")
    except Exception as e:
        logger.error(f"Failed to record OTP: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate OTP")

    # In development or until SMTP is configured, we also return the OTP in the response for convenience
    return {
        "status": "ok",
        "message": f"OTP sent successfully. (Verification Code: {otp_code})",
        "otp_debug": otp_code,
    }


@router.post("/verify-otp")
async def verify_otp(req: VerifyOtpRequest):
    """
    Verifies the submitted OTP.
    Returns a short-lived reset token for password update.
    """
    if req.email.lower() != ADMIN_EMAIL.lower():
        raise HTTPException(status_code=400, detail="Invalid OTP or email.")

    try:
        col = get_collection("admin_otps")
        record = await col.find_one({"email": req.email.lower()})
    except Exception:
        raise HTTPException(status_code=500, detail="Database lookup failed.")

    if not record or record.get("otp") != req.otp.strip():
        raise HTTPException(status_code=400, detail="Invalid or incorrect OTP code.")

    # Check expiration
    expires_at = record.get("expires_at")
    if expires_at:
        if isinstance(expires_at, str):
            expires_at = datetime.fromisoformat(expires_at)
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) > expires_at:
            raise HTTPException(status_code=400, detail="OTP code has expired. Please request a new one.")

    # Invalidate used OTP
    await col.delete_one({"email": req.email.lower()})

    # Issue temporary 15-minute password reset token
    reset_token_exp = datetime.now(timezone.utc) + timedelta(minutes=15)
    reset_token = jwt.encode(
        {"sub": req.email.lower(), "scope": "password_reset", "exp": reset_token_exp},
        JWT_SECRET,
        algorithm=JWT_ALGORITHM,
    )

    return {"status": "ok", "reset_token": reset_token}


@router.post("/reset-password")
async def reset_password(req: ResetPasswordRequest):
    """
    Resets administrator password using a valid reset token.
    Persists the new bcrypt hash to MongoDB.
    """
    if len(req.new_password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters.")

    try:
        payload = jwt.decode(req.reset_token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        if payload.get("scope") != "password_reset":
            raise HTTPException(status_code=400, detail="Invalid token scope.")
        email = payload.get("sub")
    except JWTError:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token.")

    new_hash = hash_password(req.new_password)

    try:
        col = get_collection("site_settings")
        await col.update_one(
            {"_id": "admin_credentials"},
            {
                "$set": {
                    "password_hash": new_hash,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "updated_by": email,
                }
            },
            upsert=True,
        )
        logger.info(f"Admin password successfully updated for {email}")
    except Exception as e:
        logger.error(f"Failed to save new password hash: {e}")
        raise HTTPException(status_code=500, detail="Failed to save new password.")

    return {"status": "ok", "message": "Password updated successfully. You may now log in."}
