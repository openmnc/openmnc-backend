"""
Auth router — /api/auth
Includes login, OTP forgot password, OTP verification, password reset, and /me.
"""

import os
import random
import secrets
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional
import httpx
from pydantic import BaseModel, EmailStr, Field
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.security import OAuth2PasswordRequestForm
from jose import jwt, JWTError

from auth import (
    create_access_token,
    verify_password,
    hash_password,
    get_current_admin,
    get_current_user,
    require_admin,
    require_editor,
    require_author,
    ADMIN_EMAIL,
    ADMIN_PASSWORD_HASH,
    JWT_SECRET,
    JWT_ALGORITHM,
)
from database import get_collection
from email_service import send_otp_email, send_team_invite_email, is_smtp_configured

logger = logging.getLogger("openmnc.auth")
router = APIRouter(prefix="/api/auth", tags=["auth"])

PERMANENT_OWNER_EMAILS = {
    "amit@openmnc.com",
    "openmnc.contract@gmail.com",
}


class OtpRequest(BaseModel):
    email: EmailStr


class OtpLoginRequest(BaseModel):
    email: EmailStr
    otp: str


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


class TeamInviteRequest(BaseModel):
    email: EmailStr
    role: str = Field("editor", pattern="^(admin|editor|author)$")
    name: Optional[str] = None


class ResendInviteRequest(BaseModel):
    email: EmailStr


class AcceptInviteRequest(BaseModel):
    token: str
    password: str = Field(..., min_length=6)
    name: Optional[str] = None


async def get_effective_admin_info() -> tuple[str, str]:
    """Fetch stored email and password hash from DB or fallback to environment variable."""
    try:
        col = get_collection("site_settings")
        doc = await col.find_one({"_id": "admin_credentials"})
        if doc and "password_hash" in doc:
            return doc.get("email", ADMIN_EMAIL).lower(), doc["password_hash"]
    except Exception as e:
        logger.warning(f"Could not read admin credentials from DB: {e}")
    return ADMIN_EMAIL.lower(), ADMIN_PASSWORD_HASH


async def is_email_authorized_for_admin_or_team(email: str) -> tuple[bool, str, Optional[str]]:
    """
    Validates if an email is authorized to access the OpenMNC Control Center:
    1. Primary Administrator (Owner)
    2. Active team members in team_members collection
    3. Pending invited members in team_invitations collection
    Returns: (is_authorized, role, display_name)
    """
    clean_email = email.strip().lower()
    stored_admin_email, _ = await get_effective_admin_info()

    # 1. Primary Owner / Admin check
    allowed_admin_emails = {
        stored_admin_email.lower(),
        ADMIN_EMAIL.lower(),
        os.getenv("SMTP_FROM_EMAIL", "").lower(),
        *PERMANENT_OWNER_EMAILS,
    }
    allowed_admin_emails.discard("")

    if clean_email in allowed_admin_emails:
        return True, "admin", "Founder & Owner"

    # 2. Check team_members
    try:
        team_col = get_collection("team_members")
        member = await team_col.find_one({"_id": clean_email})
        if member:
            if member.get("status") == "revoked":
                return False, "", None
            return True, member.get("role", "editor"), member.get("name")
    except Exception as e:
        logger.warning(f"Error checking team_members: {e}")

    # 3. Check pending team_invitations
    try:
        invites_col = get_collection("team_invitations")
        invite = await invites_col.find_one({"email": clean_email, "accepted": False})
        if invite:
            return True, invite.get("role", "editor"), invite.get("name")
    except Exception as e:
        logger.warning(f"Error checking team_invitations: {e}")

    return False, "", None


@router.post("/request-otp")
async def request_login_otp(req: OtpRequest):
    """
    Requests a 6-digit OTP code for passwordless login or verification.
    STRICT SECURITY RULE:
    Only primary admin or administrator-invited team members can request or receive OTP!
    If any unauthorized email submits a request, access is blocked immediately with a 403.
    Includes a 60-second cooldown rate-limiter to prevent spamming.
    """
    email_clean = req.email.strip().lower()
    authorized, role, name = await is_email_authorized_for_admin_or_team(email_clean)

    if not authorized:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access Denied: '{email_clean}' has not been invited by an OpenMNC administrator. Only verified admins or invited team members can receive an OTP. Contact admin at {ADMIN_EMAIL} for an invite."
        )

    # 60-Second Cooldown Check
    try:
        col = get_collection("admin_otps")
        existing_otp = await col.find_one({"email": email_clean})
        if existing_otp and "created_at" in existing_otp:
            cat = existing_otp["created_at"]
            if isinstance(cat, str):
                cat = datetime.fromisoformat(cat)
            if cat.tzinfo is None:
                cat = cat.replace(tzinfo=timezone.utc)
            elapsed = (datetime.now(timezone.utc) - cat).total_seconds()
            if elapsed < 60:
                wait_sec = int(60 - elapsed) + 1
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Please wait {wait_sec}s before requesting a new verification code."
                )
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"Cooldown check error: {e}")

    otp_code = str(random.randint(100000, 999999))
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)

    try:
        col = get_collection("admin_otps")
        await col.update_one(
            {"email": email_clean},
            {
                "$set": {
                    "otp": otp_code,
                    "role": role,
                    "name": name or "",
                    "expires_at": expires_at,
                    "created_at": datetime.now(timezone.utc),
                }
            },
            upsert=True,
        )
    except Exception as e:
        logger.error(f"Failed to record OTP in DB: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Database error while generating OTP: {str(e)}"
        )

    # Dispatch email (Real SMTP if configured, or safe mock dispatch)
    dispatch_res = await send_otp_email(email_clean, otp_code, name)

    return {
        "status": "ok",
        "message": f"Verification code sent to {email_clean}. Please check your inbox (and spam folder).",
        "email": email_clean,
        "expires_in_minutes": 10,
        "dispatch_status": dispatch_res.get("status"),
        "otp_debug": otp_code if dispatch_res.get("status") == "mock_delivered" else None,
    }


@router.post("/otp-login")
async def otp_login(req: OtpLoginRequest):
    """
    Direct OTP Passwordless Login for authorized Admins and invited Team Members.
    Verifies 6-digit OTP and issues full JWT access token directly into Control Center.
    """
    email_clean = req.email.strip().lower()
    authorized, role, name = await is_email_authorized_for_admin_or_team(email_clean)

    if not authorized:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access Denied: '{email_clean}' is not authorized. Please contact an administrator."
        )

    try:
        col = get_collection("admin_otps")
        record = await col.find_one({"email": email_clean})
    except Exception as e:
        raise HTTPException(status_code=500, detail="Database lookup failed.")

    if not record or record.get("otp") != req.otp.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or incorrect 6-digit OTP code. Please verify and try again."
        )

    # Check expiration
    expires_at = record.get("expires_at")
    if expires_at:
        if isinstance(expires_at, str):
            expires_at = datetime.fromisoformat(expires_at)
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) > expires_at:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="OTP code has expired (10 minute limit). Please request a new code."
            )

    # Invalidate used OTP
    await col.delete_one({"email": email_clean})

    now_iso = datetime.now(timezone.utc).isoformat()
    # If invited member, auto-activate them on successful OTP login
    team_col = get_collection("team_members")
    await team_col.update_one(
        {"_id": email_clean},
        {
            "$set": {
                "email": email_clean,
                "role": role,
                "status": "active",
                "auth_provider": "otp_email",
                "last_login": now_iso,
            }
        },
        upsert=True,
    )
    invites_col = get_collection("team_invitations")
    await invites_col.update_one({"email": email_clean}, {"$set": {"accepted": True, "accepted_at": now_iso}})

    # Issue JWT Token
    access_token = create_access_token(data={"sub": email_clean, "role": role})

    return {
        "status": "ok",
        "access_token": access_token,
        "token_type": "bearer",
        "email": email_clean,
        "role": role,
        "name": name or email_clean.split("@")[0].capitalize(),
    }


@router.post("/login")
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    """
    Authenticate admin or team member using email + password from form data.
    Returns a JWT access token containing their authorized role (admin | editor | author).
    """
    input_email = form_data.username.lower()
    stored_admin_email, current_hash = await get_effective_admin_info()
    allowed_primary = {stored_admin_email, ADMIN_EMAIL.lower(), os.getenv("SMTP_FROM_EMAIL", "").lower()}
    allowed_primary.discard("")
    is_primary_admin = (input_email in allowed_primary)

    # 1. Primary Owner/Admin check
    if is_primary_admin:
        if not current_hash:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Admin password is not initialized yet. Please click '★ First Time Here? Set Admin Password' below.",
            )
        if not verify_password(form_data.password, current_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials. Please verify your email and password.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        access_token = create_access_token(data={"sub": input_email, "role": "admin"})
        return {"access_token": access_token, "token_type": "bearer", "role": "admin", "email": input_email}

    # 2. Team Members check (MongoDB collection: team_members)
    try:
        col = get_collection("team_members")
        member = await col.find_one({"_id": input_email})
        if member:
            if member.get("status") == "revoked":
                raise HTTPException(status_code=403, detail="Your team access has been revoked by an administrator.")
            member_hash = member.get("password_hash")
            if member_hash and verify_password(form_data.password, member_hash):
                role = member.get("role", "editor")
                await col.update_one({"_id": input_email}, {"$set": {"last_login": datetime.now(timezone.utc).isoformat()}})
                access_token = create_access_token(data={"sub": input_email, "role": role})
                return {"access_token": access_token, "token_type": "bearer", "role": role, "email": input_email}
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"Team member lookup error: {e}")

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid credentials. Please verify your email and password.",
        headers={"WWW-Authenticate": "Bearer"},
    )


@router.post("/google-login")
async def google_login(req: GoogleLoginRequest):
    """
    Authenticate admin or team member using Google OAuth credential.
    Auto-activates pending team invitations!
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
    stored_admin_email, _ = await get_effective_admin_info()

    # 1. Primary Owner is always admin
    if email_clean == stored_admin_email or email_clean == ADMIN_EMAIL.lower():
        access_token = create_access_token(data={"sub": email_clean, "role": "admin"})
        return {"access_token": access_token, "token_type": "bearer", "email": email_clean, "role": "admin"}

    # 2. Check team_members
    team_col = get_collection("team_members")
    member = await team_col.find_one({"_id": email_clean})
    if member:
        if member.get("status") == "revoked":
            raise HTTPException(status_code=403, detail="Your team access has been revoked by an administrator.")
        role = member.get("role", "editor")
        await team_col.update_one({"_id": email_clean}, {"$set": {"last_login": datetime.now(timezone.utc).isoformat(), "status": "active"}})
        access_token = create_access_token(data={"sub": email_clean, "role": role})
        return {"access_token": access_token, "token_type": "bearer", "email": email_clean, "role": role}

    # 3. Check pending team_invitations (Auto-accept via Google)
    invites_col = get_collection("team_invitations")
    invite = await invites_col.find_one({"email": email_clean, "accepted": False})
    if invite:
        role = invite.get("role", "editor")
        now_iso = datetime.now(timezone.utc).isoformat()
        # Activate member
        await team_col.update_one(
            {"_id": email_clean},
            {
                "$set": {
                    "email": email_clean,
                    "name": payload.get("name", ""),
                    "role": role,
                    "status": "active",
                    "auth_provider": "google",
                    "created_at": now_iso,
                    "last_login": now_iso,
                }
            },
            upsert=True,
        )
        await invites_col.update_one({"_id": invite["_id"]}, {"$set": {"accepted": True, "accepted_at": now_iso}})
        access_token = create_access_token(data={"sub": email_clean, "role": role})
        return {"access_token": access_token, "token_type": "bearer", "email": email_clean, "role": role}

    raise HTTPException(
        status_code=403,
        detail=f"Access denied: '{email}' has not been invited by an OpenMNC administrator."
    )


@router.get("/me")
async def get_me(user: dict = Depends(get_current_user)):
    """Return currently authenticated team member info."""
    return user


# ---------------------------------------------------------------------------
# Team & Role-Based Access Control (RBAC) Management
# ---------------------------------------------------------------------------

@router.get("/team")
async def list_team_and_invites(user: dict = Depends(require_admin)):
    """
    Tier 1 Admin only: Lists all team members and pending invitations.
    Owner accounts (amit@openmnc.com) are explicitly highlighted and protected.
    """
    team_col = get_collection("team_members")
    invites_col = get_collection("team_invitations")
    stored_admin_email, _ = await get_effective_admin_info()
    all_owner_emails = {stored_admin_email.lower(), ADMIN_EMAIL.lower(), *PERMANENT_OWNER_EMAILS}

    # Active/invited members
    members = []
    cursor = team_col.find({"status": {"$ne": "revoked"}}).sort("created_at", -1)
    async for doc in cursor:
        member_email = doc["_id"].lower()
        is_owner = member_email in all_owner_emails
        members.append({
            "email": member_email,
            "name": doc.get("name", ""),
            "role": "admin" if is_owner else doc.get("role", "editor"),
            "status": "active" if is_owner else doc.get("status", "active"),
            "auth_provider": doc.get("auth_provider", "credentials"),
            "last_login": doc.get("last_login"),
            "is_owner": is_owner,
        })

    # Always ensure primary owner (amit@openmnc.com) is in members list if not present
    primary_email = "amit@openmnc.com"
    if not any(m["email"] == primary_email for m in members):
        members.insert(0, {
            "email": primary_email,
            "name": "Amit Barai (Founder & Owner)",
            "role": "admin",
            "status": "active",
            "auth_provider": "credentials",
            "is_owner": True,
        })

    # Pending invitations
    invites = []
    inv_cursor = invites_col.find({"accepted": False}).sort("created_at", -1)
    async for doc in inv_cursor:
        invites.append({
            "id": str(doc["_id"]),
            "email": doc["email"],
            "role": doc["role"],
            "name": doc.get("name", ""),
            "token": doc["token"],
            "created_at": doc.get("created_at"),
            "expires_at": doc.get("expires_at"),
        })

    return {
        "primary_admin": stored_admin_email,
        "owner_emails": list(all_owner_emails),
        "members": members,
        "invitations": invites,
    }


@router.post("/team/invite")
async def invite_team_member(req: TeamInviteRequest, user: dict = Depends(require_admin)):
    """
    Tier 1 Admin only: Invites a team member with a specified role (editor, author, or admin).
    1. Checks that email is not the Owner or an already active member.
    2. Generates a secure 7-day invitation link.
    3. Dispatches official invitation email via Brevo SMTP relay.
    """
    email_clean = req.email.strip().lower()
    stored_admin_email, _ = await get_effective_admin_info()
    all_owner_emails = {stored_admin_email.lower(), ADMIN_EMAIL.lower(), *PERMANENT_OWNER_EMAILS}

    if email_clean in all_owner_emails:
        raise HTTPException(status_code=400, detail="The Founder / Primary Administrator is already active.")

    team_col = get_collection("team_members")
    existing_active = await team_col.find_one({"_id": email_clean, "status": "active"})
    if existing_active:
        raise HTTPException(
            status_code=400,
            detail=f"'{email_clean}' is already an active and connected team member. You cannot send duplicate invitations to an active user."
        )

    token = secrets.token_urlsafe(24)
    now = datetime.now(timezone.utc)
    expires_at = (now + timedelta(days=7)).isoformat()

    invites_col = get_collection("team_invitations")
    # Cancel any previous pending invites for this email
    await invites_col.delete_many({"email": email_clean})

    await invites_col.insert_one({
        "email": email_clean,
        "role": req.role,
        "name": req.name or "",
        "token": token,
        "invited_by": user.get("email", "Admin"),
        "created_at": now.isoformat(),
        "expires_at": expires_at,
        "accepted": False,
    })

    # Record in team_members with status='invited'
    await team_col.update_one(
        {"_id": email_clean},
        {
            "$set": {
                "email": email_clean,
                "name": req.name or "",
                "role": req.role,
                "status": "invited",
                "updated_at": now.isoformat(),
            }
        },
        upsert=True,
    )

    frontend_base = os.getenv("FRONTEND_URL", "http://localhost:5173").rstrip("/")
    invite_url = f"{frontend_base}/admin/join?token={token}"
    inviter = user.get("email", "Admin")

    # Send real invitation email via Brevo SMTP
    dispatch_res = await send_team_invite_email(
        to_email=email_clean,
        invite_url=invite_url,
        role=req.role,
        invited_by=inviter,
        recipient_name=req.name,
    )

    return {
        "status": "ok",
        "message": f"Invitation email sent to {email_clean} for role '{req.role.upper()}'!",
        "token": token,
        "email": email_clean,
        "role": req.role,
        "expires_at": expires_at,
        "invite_url": invite_url,
        "dispatch_status": dispatch_res.get("status"),
    }


@router.post("/team/resend-invite")
async def resend_team_invitation(req: ResendInviteRequest, user: dict = Depends(require_admin)):
    """
    Tier 1 Admin only: Resends an existing pending invitation email via Brevo SMTP.
    """
    email_clean = req.email.strip().lower()
    invites_col = get_collection("team_invitations")
    invite = await invites_col.find_one({"email": email_clean, "accepted": False})

    if not invite:
        raise HTTPException(
            status_code=404,
            detail=f"No pending invitation found for '{email_clean}'. Please generate a new invite."
        )

    token = invite.get("token") or secrets.token_urlsafe(24)
    frontend_base = os.getenv("FRONTEND_URL", "http://localhost:5173").rstrip("/")
    invite_url = f"{frontend_base}/admin/join?token={token}"

    dispatch_res = await send_team_invite_email(
        to_email=email_clean,
        invite_url=invite_url,
        role=invite.get("role", "editor"),
        invited_by=user.get("email", "Admin"),
        recipient_name=invite.get("name"),
    )

    return {
        "status": "ok",
        "message": f"Invitation email successfully resent to {email_clean} via Brevo SMTP!",
        "dispatch_status": dispatch_res.get("status"),
        "invite_url": invite_url,
    }


@router.delete("/team/{email}")
async def revoke_team_member(email: str, user: dict = Depends(require_admin)):
    """
    Tier 1 Admin only: Revokes a team member's access or cancels an invitation.
    STRICT SECURITY RULE:
    The Owner account (amit@openmnc.com) is permanently protected and CANNOT be deleted or revoked!
    """
    email_clean = email.strip().lower()
    stored_admin_email, _ = await get_effective_admin_info()
    all_owner_emails = {stored_admin_email.lower(), ADMIN_EMAIL.lower(), *PERMANENT_OWNER_EMAILS}

    if email_clean in all_owner_emails:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Security Violation: The Owner Administrator account ({email_clean}) is permanently protected and cannot be revoked or deleted."
        )

    team_col = get_collection("team_members")
    invites_col = get_collection("team_invitations")

    await team_col.update_one(
        {"_id": email_clean},
        {"$set": {"status": "revoked", "revoked_at": datetime.now(timezone.utc).isoformat()}},
    )
    await invites_col.delete_many({"email": email_clean})

    return {"status": "ok", "message": f"Access for {email_clean} has been revoked."}


@router.get("/team/verify-invite")
async def verify_invitation(token: str = Query(..., description="Invitation token")):
    """
    Public: Verifies an invitation token before accepting.
    """
    invites_col = get_collection("team_invitations")
    invite = await invites_col.find_one({"token": token, "accepted": False})
    if not invite:
        raise HTTPException(status_code=404, detail="Invalid or expired invitation link.")

    return {
        "status": "ok",
        "valid": True,
        "email": invite["email"],
        "role": invite["role"],
        "name": invite.get("name", ""),
    }


@router.post("/team/accept-invite")
async def accept_invitation(req: AcceptInviteRequest):
    """
    Public: Accepts an invitation, sets password, and logs in immediately.
    """
    invites_col = get_collection("team_invitations")
    invite = await invites_col.find_one({"token": req.token, "accepted": False})
    if not invite:
        raise HTTPException(status_code=400, detail="Invalid or expired invitation token.")

    email_clean = invite["email"].lower()
    role = invite.get("role", "editor")
    new_hash = hash_password(req.password)
    now_iso = datetime.now(timezone.utc).isoformat()

    team_col = get_collection("team_members")
    await team_col.update_one(
        {"_id": email_clean},
        {
            "$set": {
                "email": email_clean,
                "name": req.name or invite.get("name", ""),
                "role": role,
                "password_hash": new_hash,
                "status": "active",
                "auth_provider": "credentials",
                "created_at": now_iso,
                "last_login": now_iso,
            }
        },
        upsert=True,
    )

    await invites_col.update_one({"_id": invite["_id"]}, {"$set": {"accepted": True, "accepted_at": now_iso}})

    access_token = create_access_token(data={"sub": email_clean, "role": role})
    return {
        "status": "ok",
        "message": f"Welcome to OpenMNC! You have joined as {role.upper()}.",
        "access_token": access_token,
        "email": email_clean,
        "role": role,
    }


# ---------------------------------------------------------------------------
# Initial Admin Setup & Recovery
# ---------------------------------------------------------------------------

@router.post("/setup-admin")
async def setup_initial_admin(req: InitAdminRequest):
    """
    Allow setting the admin credentials if not yet initialized.
    Accepts amit@openmnc.com or the owner's chosen admin email.
    """
    col = get_collection("site_settings")
    existing = await col.find_one({"_id": "admin_credentials"})
    if existing and existing.get("password_hash"):
        raise HTTPException(
            status_code=400,
            detail="Admin credentials have already been configured. Please use standard login or Forgot Password."
        )

    if len(req.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters.")

    user_email = req.email.lower()
    new_hash = hash_password(req.password)
    await col.update_one(
        {"_id": "admin_credentials"},
        {
            "$set": {
                "password_hash": new_hash,
                "email": user_email,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        },
        upsert=True,
    )
    # Also register in team_members as owner admin
    team_col = get_collection("team_members")
    await team_col.update_one(
        {"_id": user_email},
        {
            "$set": {
                "email": user_email,
                "name": "Owner Admin",
                "role": "admin",
                "password_hash": new_hash,
                "status": "active",
                "auth_provider": "credentials",
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        },
        upsert=True,
    )
    access_token = create_access_token(data={"sub": user_email, "role": "admin"})
    return {
        "status": "ok",
        "message": f"Admin credentials successfully initialized for {user_email}!",
        "access_token": access_token,
    }


@router.post("/forgot-password")
async def forgot_password(req: ForgotPasswordRequest):
    """
    Generates a 6-digit OTP for admin password reset.
    Validates that only authorized admins or invited team members can reset password.
    Dispatches OTP via real SMTP or secure system dispatch.
    """
    email_clean = req.email.strip().lower()
    authorized, role, name = await is_email_authorized_for_admin_or_team(email_clean)

    if not authorized:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access Denied: '{email_clean}' is not authorized. Please contact an OpenMNC administrator."
        )

    # 60-Second Cooldown Check
    try:
        col = get_collection("admin_otps")
        existing_otp = await col.find_one({"email": email_clean})
        if existing_otp and "created_at" in existing_otp:
            cat = existing_otp["created_at"]
            if isinstance(cat, str):
                cat = datetime.fromisoformat(cat)
            if cat.tzinfo is None:
                cat = cat.replace(tzinfo=timezone.utc)
            elapsed = (datetime.now(timezone.utc) - cat).total_seconds()
            if elapsed < 60:
                wait_sec = int(60 - elapsed) + 1
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Please wait {wait_sec}s before requesting a new password reset code."
                )
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"Cooldown check error: {e}")

    otp_code = str(random.randint(100000, 999999))
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)

    try:
        col = get_collection("admin_otps")
        await col.update_one(
            {"email": email_clean},
            {
                "$set": {
                    "otp": otp_code,
                    "expires_at": expires_at,
                    "created_at": datetime.now(timezone.utc),
                }
            },
            upsert=True,
        )
    except Exception as e:
        logger.error(f"Failed to record OTP: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"MongoDB connection issue: {str(e)}. Please ensure MongoDB Atlas Network Access allows 0.0.0.0/0."
        )

    dispatch_res = await send_otp_email(email_clean, otp_code, name)

    return {
        "status": "ok",
        "message": f"Password reset OTP sent to {email_clean}. Please check your inbox.",
        "otp_debug": otp_code if dispatch_res.get("status") == "mock_delivered" else None,
    }


@router.post("/verify-otp")
async def verify_otp(req: VerifyOtpRequest):
    """
    Verifies the submitted OTP.
    Returns a short-lived reset token for password update.
    """
    email_clean = req.email.strip().lower()
    authorized, _, _ = await is_email_authorized_for_admin_or_team(email_clean)
    if not authorized:
        raise HTTPException(status_code=403, detail="Invalid authorization for this email.")

    try:
        col = get_collection("admin_otps")
        record = await col.find_one({"email": email_clean})
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
