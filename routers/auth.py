"""
Auth router — /api/auth
Includes login, OTP forgot password, OTP verification, password reset, and /me.
"""

import os
import random
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional
import httpx
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


class InitAdminRequest(BaseModel):
    email: EmailStr
    password: str


class GoogleLoginRequest(BaseModel):
    credential: str


class StaffEmailRequest(BaseModel):
    email: EmailStr


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
    Authenticate admin or employee using email + password from form data.
    Returns a JWT access token on success.
    """
    input_email = form_data.username.lower()
    is_primary_admin = (input_email == ADMIN_EMAIL.lower())

    current_hash = await get_effective_admin_hash()
    
    # If primary admin
    if is_primary_admin:
        if not current_hash:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Admin password is not initialized yet. Please click 'Forgot password?' or use First Time Setup to set your password.",
            )
        if not verify_password(form_data.password, current_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials. Please verify your email and password.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        access_token = create_access_token(data={"sub": ADMIN_EMAIL})
        return {"access_token": access_token, "token_type": "bearer", "role": "admin"}

    # If employee / staff member
    try:
        col = get_collection("site_settings")
        staff_doc = await col.find_one({"_id": "authorized_staff"})
        if staff_doc:
            staff_list = staff_doc.get("staff", [])
            for member in staff_list:
                if member.get("email", "").lower() == input_email:
                    member_hash = member.get("password_hash")
                    if member_hash and verify_password(form_data.password, member_hash):
                        access_token = create_access_token(data={"sub": input_email})
                        return {"access_token": access_token, "token_type": "bearer", "role": "staff"}
    except Exception as e:
        logger.warning(f"Staff lookup error: {e}")

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid credentials. Please verify your email and password.",
        headers={"WWW-Authenticate": "Bearer"},
    )


@router.post("/google-login")
async def google_login(req: GoogleLoginRequest):
    """
    Authenticate admin or authorized employees using Google OAuth credential.
    Verifies token directly via Google API.
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"https://oauth2.googleapis.com/tokeninfo?id_token={req.credential}"
            )
            if resp.status_code != 200:
                raise HTTPException(status_code=401, detail="Invalid Google OAuth credential")
            payload = resp.json()
    except Exception as e:
        logger.error(f"Google OAuth verification failed: {e}")
        raise HTTPException(status_code=401, detail="Failed to verify Google account")

    email = payload.get("email")
    verified = payload.get("email_verified")
    if not email or str(verified).lower() != "true":
        raise HTTPException(status_code=401, detail="Google account email is not verified")

    email_clean = email.lower()
    role = "admin" if email_clean == ADMIN_EMAIL.lower() else None

    if not role:
        try:
            col = get_collection("site_settings")
            staff_doc = await col.find_one({"_id": "authorized_staff"})
            if staff_doc:
                allowed_emails = [s.lower() for s in staff_doc.get("emails", [])]
                if email_clean in allowed_emails:
                    role = "staff"
        except Exception:
            pass

    if not role:
        raise HTTPException(
            status_code=403,
            detail=f"Access denied: '{email}' is not registered as an administrator or employee for OpenMNC."
        )

    access_token = create_access_token(data={"sub": email_clean})
    return {"access_token": access_token, "token_type": "bearer", "email": email_clean, "role": role}


@router.post("/setup-admin")
async def setup_initial_admin(req: InitAdminRequest):
    """
    Allow setting the admin password if no credentials exist in DB yet.
    """
    if req.email.lower() != ADMIN_EMAIL.lower():
        raise HTTPException(status_code=403, detail=f"Setup is only permitted for primary admin email: {ADMIN_EMAIL}")

    col = get_collection("site_settings")
    existing = await col.find_one({"_id": "admin_credentials"})
    if existing and existing.get("password_hash"):
        raise HTTPException(
            status_code=400,
            detail="Admin credentials have already been configured. Please use standard login or Forgot Password."
        )

    if len(req.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters.")

    new_hash = hash_password(req.password)
    await col.update_one(
        {"_id": "admin_credentials"},
        {
            "$set": {
                "password_hash": new_hash,
                "email": req.email.lower(),
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        },
        upsert=True,
    )
    access_token = create_access_token(data={"sub": req.email.lower()})
    return {
        "status": "ok",
        "message": "Admin credentials successfully configured! You are now logged in.",
        "access_token": access_token,
    }


@router.get("/me")
async def get_me(admin: str = Depends(get_current_admin)):
    """Return currently authenticated administrator or staff member."""
    is_owner = (admin.lower() == ADMIN_EMAIL.lower())
    return {"email": admin, "role": "admin" if is_owner else "staff", "is_owner": is_owner}


@router.get("/staff")
async def list_authorized_staff(admin: str = Depends(get_current_admin)):
    """List all authorized employee emails (admin only)."""
    col = get_collection("site_settings")
    doc = await col.find_one({"_id": "authorized_staff"})
    emails = doc.get("emails", []) if doc else []
    return {"emails": emails, "primary_admin": ADMIN_EMAIL}


@router.post("/staff")
async def add_authorized_staff(req: StaffEmailRequest, admin: str = Depends(get_current_admin)):
    """Add an employee email for dashboard & Google login access (owner only)."""
    if admin.lower() != ADMIN_EMAIL.lower():
        raise HTTPException(status_code=403, detail="Only the primary administrator can manage staff access.")

    email_clean = req.email.lower()
    col = get_collection("site_settings")
    await col.update_one(
        {"_id": "authorized_staff"},
        {"$addToSet": {"emails": email_clean}},
        upsert=True,
    )
    return {"status": "ok", "message": f"Employee '{email_clean}' successfully granted access."}


@router.delete("/staff/{email}")
async def remove_authorized_staff(email: str, admin: str = Depends(get_current_admin)):
    """Revoke an employee's access (owner only)."""
    if admin.lower() != ADMIN_EMAIL.lower():
        raise HTTPException(status_code=403, detail="Only the primary administrator can manage staff access.")

    email_clean = email.lower()
    col = get_collection("site_settings")
    await col.update_one(
        {"_id": "authorized_staff"},
        {"$pull": {"emails": email_clean}},
    )
    return {"status": "ok", "message": f"Employee '{email_clean}' access revoked."}


@router.post("/forgot-password")
async def forgot_password(req: ForgotPasswordRequest):
    """
    Generates a 6-digit OTP for admin password reset.
    Stores it in MongoDB with a 15-minute expiration window.
    """
    if req.email.lower() != ADMIN_EMAIL.lower():
        return {
            "status": "ok",
            "message": "If the email is registered as an administrator, an OTP has been dispatched.",
        }

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
        raise HTTPException(
            status_code=500,
            detail=f"MongoDB connection issue: {str(e)}. Please ensure MongoDB Atlas Network Access allows 0.0.0.0/0."
        )

    return {
        "status": "ok",
        "message": f"OTP generated successfully. Verification Code: {otp_code}",
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
