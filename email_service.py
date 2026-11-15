"""
Transactional Email Service for OpenMNC LLP
Optimized for Brevo (Sendinblue) 300 free emails/day & Gmail SMTP.
Features:
1. Brevo REST API (primary) — pure HTTPS, works on ALL cloud platforms (Render, Vercel, Railway)
2. Multi-port SMTP resilience as fallback: 465 (SSL) -> 587 (STARTTLS) -> 2525
3. SMTP runs in asyncio thread pool executor — never blocks the FastAPI event loop
4. Auto-cleaning of environment variable quotes (handles Render / dotenv quotes)
5. Zero-crash console fallback for local offline development
6. Detailed error propagation — no more silent failures swallowed by generic messages
"""

import os
import asyncio
import smtplib
import ssl
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional, Dict, Any, Tuple
from dotenv import load_dotenv

logger = logging.getLogger("openmnc.email_service")


def clean_val(val: Optional[str], default: str = "") -> str:
    """Strips quotes and whitespace added by Docker, Render, or env files."""
    if val is None:
        return default
    v = str(val).strip()
    if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
        v = v[1:-1].strip()
    return v


def get_email_config() -> Dict[str, Any]:
    """Dynamically reads and sanitizes the latest email configuration from .env and environment."""
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_path):
        load_dotenv(env_path, override=True)
    else:
        load_dotenv(override=True)

    host = clean_val(os.getenv("SMTP_HOST"), "smtp-relay.brevo.com")
    port_str = clean_val(os.getenv("SMTP_PORT"), "465")
    port = int(port_str) if port_str.isdigit() else 465
    user = clean_val(os.getenv("SMTP_USER"))
    password = clean_val(os.getenv("SMTP_PASSWORD"))
    from_name = clean_val(os.getenv("SMTP_FROM_NAME"), "OpenMNC Backend")

    # Brevo requires a verified sender email (not @smtp-brevo.com login)
    from_email = clean_val(os.getenv("SMTP_FROM_EMAIL"))
    if not from_email or from_email.endswith("@smtp-brevo.com"):
        admin_email = clean_val(os.getenv("ADMIN_EMAIL"), "openmnc.contract@gmail.com")
        from_email = admin_email

    # Brevo REST API key (xkeysib-...) — preferred over SMTP on cloud platforms
    brevo_api_key = clean_val(os.getenv("BREVO_API_KEY"))
    resend_key = clean_val(os.getenv("RESEND_API_KEY"))

    is_configured = bool(user and password and host and password != "your_brevo_smtp_key")
    return {
        "host": host,
        "port": port,
        "user": user,
        "password": password,
        "from_name": from_name,
        "from_email": from_email,
        "brevo_api_key": brevo_api_key,
        "resend_key": resend_key,
        "is_configured": is_configured,
    }


def is_smtp_configured() -> bool:
    """Returns True if valid SMTP credentials are configured."""
    return get_email_config()["is_configured"]


def _smtp_send_blocking(cfg: Dict[str, Any], to_email: str, msg: MIMEMultipart) -> Tuple[bool, str]:
    """
    Synchronous SMTP delivery — always call via asyncio.run_in_executor()
    so it never blocks the FastAPI async event loop.
    Tries Port 465 (SSL) -> 587 (STARTTLS) -> 2525 (Alternative).
    """
    if not cfg["is_configured"]:
        return False, "SMTP credentials missing (SMTP_USER or SMTP_PASSWORD empty)"

    attempts = [
        (cfg["host"], 465, "ssl"),
        (cfg["host"], 587, "starttls"),
        (cfg["host"], 2525, "starttls"),
    ]
    # Deduplicate while preserving order
    seen, unique = set(), []
    for a in attempts:
        if a not in seen:
            seen.add(a)
            unique.append(a)

    errors = []
    for host, port, mode in unique:
        try:
            logger.info(f"[SMTP] Attempting {to_email} via {host}:{port} ({mode})")
            if mode == "ssl":
                ctx = ssl.create_default_context()
                with smtplib.SMTP_SSL(host, port, context=ctx, timeout=10) as server:
                    server.ehlo()
                    server.login(cfg["user"], cfg["password"])
                    server.sendmail(cfg["from_email"], [to_email], msg.as_string())
            else:
                with smtplib.SMTP(host, port, timeout=10) as server:
                    server.ehlo()
                    server.starttls()
                    server.ehlo()
                    server.login(cfg["user"], cfg["password"])
                    server.sendmail(cfg["from_email"], [to_email], msg.as_string())
            logger.info(f"[SMTP] Delivered to {to_email} via {host}:{port}")
            return True, f"{host}:{port} ({mode})"
        except Exception as e:
            err = f"{host}:{port}({mode}): {type(e).__name__}: {str(e)}"
            logger.warning(f"[SMTP] Attempt failed: {err}")
            errors.append(err)

    return False, " | ".join(errors)


async def _dispatch_via_brevo_api(
    cfg: Dict[str, Any],
    to_email: str,
    subject: str,
    html_content: str,
    text_content: str,
) -> Tuple[bool, str]:
    """
    Sends email via Brevo's transactional REST API (POST /v3/smtp/email).
    Uses HTTPS port 443 — works on ALL cloud platforms, never blocked.
    Requires BREVO_API_KEY env var (xkeysib-...) from Brevo dashboard -> API Keys.
    """
    import httpx
    api_key = cfg.get("brevo_api_key", "")
    if not api_key:
        return False, "BREVO_API_KEY not set"

    payload = {
        "sender": {"name": cfg["from_name"], "email": cfg["from_email"]},
        "to": [{"email": to_email}],
        "subject": subject,
        "htmlContent": html_content,
        "textContent": text_content,
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.post(
                "https://api.brevo.com/v3/smtp/email",
                headers={
                    "api-key": api_key,
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                json=payload,
            )
        if res.status_code in (200, 201):
            logger.info(f"[BrevoAPI] Email dispatched to {to_email}")
            return True, "brevo_rest_api"
        else:
            body = res.text[:400]
            logger.error(f"[BrevoAPI] HTTP {res.status_code}: {body}")
            return False, f"Brevo API HTTP {res.status_code}: {body}"
    except Exception as e:
        logger.error(f"[BrevoAPI] Exception: {e}")
        return False, f"Brevo API error: {type(e).__name__}: {str(e)}"


async def _dispatch_via_resend(
    cfg: Dict[str, Any],
    to_email: str,
    subject: str,
    html_content: str,
) -> Tuple[bool, str]:
    """Sends email via Resend.com REST API fallback."""
    import httpx
    if not cfg.get("resend_key"):
        return False, "RESEND_API_KEY not set"
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {cfg['resend_key']}"},
                json={
                    "from": f"{cfg['from_name']} <{cfg['from_email']}>",
                    "to": [to_email],
                    "subject": subject,
                    "html": html_content,
                },
            )
        if res.status_code in (200, 201):
            logger.info(f"[Resend] Email dispatched to {to_email}")
            return True, "resend_api"
        else:
            body = res.text[:300]
            logger.error(f"[Resend] HTTP {res.status_code}: {body}")
            return False, f"Resend HTTP {res.status_code}: {body}"
    except Exception as e:
        logger.error(f"[Resend] Exception: {e}")
        return False, f"Resend error: {str(e)}"


async def _send_email(
    to_email: str,
    subject: str,
    html_content: str,
    text_content: str,
) -> Dict[str, Any]:
    """
    Master email dispatcher — tries providers in priority order:
    1. Brevo REST API  (HTTPS — always works on Render/cloud, requires BREVO_API_KEY)
    2. Resend API      (HTTPS — requires RESEND_API_KEY)
    3. SMTP via Brevo  (runs in thread pool — may be blocked on some cloud platforms)
    4. Console mock    (dev fallback when no provider is configured)

    Returns {"status": "sent"|"smtp_failed"|"mock_delivered", "detail": "...", "provider": "..."}
    """
    cfg = get_email_config()

    # 1. Brevo REST API (best for cloud/serverless)
    if cfg.get("brevo_api_key"):
        ok, detail = await _dispatch_via_brevo_api(cfg, to_email, subject, html_content, text_content)
        if ok:
            return {"status": "sent", "provider": "brevo_rest_api", "recipient": to_email, "detail": detail}
        logger.warning(f"[Email] Brevo REST API failed: {detail}")

    # 2. Resend API
    if cfg.get("resend_key"):
        ok, detail = await _dispatch_via_resend(cfg, to_email, subject, html_content)
        if ok:
            return {"status": "sent", "provider": "resend_api", "recipient": to_email, "detail": detail}
        logger.warning(f"[Email] Resend API failed: {detail}")

    # 3. SMTP (run in thread pool so it never blocks the asyncio event loop)
    if cfg["is_configured"]:
        import uuid
        # We need to build the MIME message here to pass to the thread
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{cfg['from_name']} <{cfg['from_email']}>"
        msg["To"] = to_email
        msg["Reply-To"] = cfg["from_email"]
        msg["Message-ID"] = f"<{uuid.uuid4()}@openmnc.com>"
        msg["X-Mailer"] = "OpenMNC Secure Mailer v3"
        msg["Auto-Submitted"] = "auto-generated"
        msg.attach(MIMEText(text_content, "plain"))
        msg.attach(MIMEText(html_content, "html"))

        loop = asyncio.get_event_loop()
        ok, detail = await loop.run_in_executor(None, _smtp_send_blocking, cfg, to_email, msg)
        if ok:
            return {"status": "sent", "provider": "brevo_smtp", "recipient": to_email, "detail": detail}
        else:
            logger.error(f"[Email] All SMTP ports failed for {to_email}: {detail}")
            return {"status": "smtp_failed", "provider": "brevo_smtp", "recipient": to_email, "detail": detail}

    # 4. Dev console fallback (no credentials configured at all)
    logger.info(f"[Email] No email provider configured — mock dispatch to {to_email}")
    print(f"\n{'='*55}")
    print(f"[OPENMNC EMAIL - MOCK DISPATCH]  Subject: {subject}")
    print(f"Recipient: {to_email}")
    print(f"{'='*55}\n")
    return {
        "status": "mock_delivered",
        "provider": "console",
        "recipient": to_email,
        "note": "No email provider configured. Set BREVO_API_KEY or SMTP credentials.",
    }


async def send_otp_email(to_email: str, otp_code: str, user_name: Optional[str] = None) -> Dict[str, Any]:
    """
    Sends a secure 6-digit OTP code to the verified administrator or invited team member.
    """
    cfg = get_email_config()
    subject = f"Your OpenMNC Admin Verification Code: {otp_code}"
    display_name = user_name or to_email.split("@")[0].capitalize()

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8">
      <title>OpenMNC Security Code</title>
      <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background-color: #0a0e1a; color: #e2e8f0; margin: 0; padding: 24px; }}
        .card {{ max-width: 520px; margin: 0 auto; background: #0f172a; border: 1px solid rgba(0, 245, 255, 0.2); border-radius: 16px; padding: 32px; box-shadow: 0 10px 25px rgba(0,0,0,0.5); }}
        .logo {{ font-size: 24px; font-weight: 800; color: #ffffff; margin-bottom: 24px; text-align: center; }}
        .logo span {{ color: #00f5ff; }}
        .badge {{ display: inline-block; background: rgba(0, 245, 255, 0.1); color: #00f5ff; padding: 4px 12px; border-radius: 999px; font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 16px; }}
        .otp-box {{ background: rgba(255, 255, 255, 0.03); border: 2px dashed #00f5ff; border-radius: 12px; padding: 20px; text-align: center; margin: 24px 0; }}
        .otp-code {{ font-size: 38px; font-weight: 800; letter-spacing: 10px; color: #00f5ff; font-family: monospace; }}
        .info {{ color: #94a3b8; font-size: 14px; line-height: 1.6; }}
        .footer {{ margin-top: 32px; padding-top: 20px; border-top: 1px solid rgba(255, 255, 255, 0.08); font-size: 12px; color: #64748b; text-align: center; }}
      </style>
    </head>
    <body>
      <div class="card">
        <div class="logo">Open<span>MNC</span> LLP</div>
        <div style="text-align: center;">
          <span class="badge">Admin Security Verification</span>
        </div>
        <h2 style="color: #ffffff; margin-top: 8px; font-size: 20px; text-align: center;">One-Time Login Passcode</h2>
        <p class="info">Hello <strong>{display_name}</strong>,</p>
        <p class="info">You requested a secure login or password reset for the OpenMNC Control Center. Use the one-time verification passcode below to complete your authorization:</p>
        
        <div class="otp-box">
          <div class="otp-code">{otp_code}</div>
          <p style="margin: 8px 0 0; font-size: 12px; color: #94a3b8;">Valid for 10 minutes. Do not share this code with anyone.</p>
        </div>

        <p class="info">If you did not request this login attempt, your account remains protected. Please contact the primary administrator at <strong>hello@openmnc.com</strong> immediately.</p>

        <div class="footer">
          OpenMNC LLP &bull; Automated Security Gateway<br>
          Powered by Brevo High-Speed SMTP Relay &bull; 24/7 Security
        </div>
      </div>
    </body>
    </html>
    """

    text_content = f"""OpenMNC LLP — Admin Security Code

Hello {display_name},

Your one-time login verification code is: {otp_code}

This code expires in 10 minutes. If you did not request this code, ignore this email.

OpenMNC Security Team
https://openmnc.com
"""

    return await _send_email(to_email, subject, html_content, text_content)


async def send_team_invite_email(
    to_email: str,
    invite_url: str,
    role: str = "Editor",
    invited_by: str = "Administrator",
    recipient_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Sends an official team invitation email with an activation link.
    """
    cfg = get_email_config()
    role_display = role.capitalize()
    display_name = recipient_name or to_email.split("@")[0].capitalize()
    subject = f"Invitation: Join the OpenMNC Team as {role_display}"

    role_descriptions = {
        "admin": "Full system control, team access permissions, applicant review, and system configurations.",
        "editor": "Manage jobs, applicant resumes, services copy, and blog publications.",
        "author": "Draft, edit, and publish blogs, articles, and news releases.",
    }
    role_info = role_descriptions.get(role.lower(), "Collaborate with the OpenMNC team.")

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8">
      <title>OpenMNC Team Invitation</title>
      <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background-color: #0a0e1a; color: #e2e8f0; margin: 0; padding: 24px; }}
        .card {{ max-width: 540px; margin: 0 auto; background: #0f172a; border: 1px solid rgba(0, 245, 255, 0.25); border-radius: 16px; padding: 32px; box-shadow: 0 10px 30px rgba(0,0,0,0.6); }}
        .logo {{ font-size: 26px; font-weight: 800; color: #ffffff; margin-bottom: 20px; text-align: center; }}
        .logo span {{ color: #00f5ff; }}
        .badge {{ display: inline-block; background: rgba(0, 245, 255, 0.12); color: #00f5ff; padding: 5px 14px; border-radius: 999px; font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: 1px; }}
        .btn {{ display: inline-block; background: linear-gradient(135deg, #00f5ff 0%, #00b4d8 100%); color: #0a0e1a; font-weight: 700; font-size: 14px; padding: 14px 28px; border-radius: 10px; text-decoration: none; margin: 24px 0; box-shadow: 0 4px 15px rgba(0, 245, 255, 0.3); }}
        .role-box {{ background: rgba(255, 255, 255, 0.03); border-left: 3px solid #00f5ff; border-radius: 8px; padding: 14px 16px; margin: 18px 0; }}
        .info {{ color: #94a3b8; font-size: 14px; line-height: 1.6; }}
        .link-text {{ word-break: break-all; font-family: monospace; font-size: 11px; color: #38bdf8; }}
        .footer {{ margin-top: 32px; padding-top: 20px; border-top: 1px solid rgba(255, 255, 255, 0.08); font-size: 12px; color: #64748b; text-align: center; }}
      </style>
    </head>
    <body>
      <div class="card">
        <div class="logo">Open<span>MNC</span> LLP</div>
        <div style="text-align: center; margin-bottom: 20px;">
          <span class="badge">Official Team Invitation</span>
        </div>
        
        <h2 style="color: #ffffff; margin-top: 0; font-size: 20px; text-align: center;">You've Been Invited to Join the Team</h2>
        
        <p class="info">Hello <strong>{display_name}</strong>,</p>
        <p class="info">
          <strong>{invited_by}</strong> has granted you official access to the <strong>OpenMNC Control Center</strong> with the role of <strong>{role_display}</strong>.
        </p>

        <div class="role-box">
          <div style="color: #00f5ff; font-weight: 700; font-size: 13px; text-transform: uppercase; margin-bottom: 4px;">
            Role: {role_display}
          </div>
          <div style="color: #cbd5e1; font-size: 13px;">
            {role_info}
          </div>
        </div>

        <p class="info">Click below to activate your account, set your password, and start collaborating:</p>

        <div style="text-align: center;">
          <a href="{invite_url}" class="btn" target="_blank">Accept Invitation &amp; Join Team &rarr;</a>
        </div>

        <p class="info" style="font-size: 12px;">Or copy and paste this secure link into your browser:</p>
        <p class="link-text">{invite_url}</p>

        <p class="info" style="font-size: 12px; margin-top: 20px;">
          🔒 <em>This invitation link is valid for 7 days. If you were not expecting this invitation, you can safely ignore this email.</em>
        </p>

        <div class="footer">
          OpenMNC LLP &bull; Team &amp; Workspace Access Gateway<br>
          Automated Transactional Dispatch via Brevo SMTP Relay
        </div>
      </div>
    </body>
    </html>
    """

    text_content = f"""OpenMNC LLP — Official Team Invitation

Hello {display_name},

{invited_by} has invited you to join OpenMNC as {role_display}.

Click the link below to accept your invitation and activate your account:
{invite_url}

This invitation link is valid for 7 days.

OpenMNC Team
https://openmnc.com
"""

    return await _send_email(to_email, subject, html_content, text_content)



def clean_val(val: Optional[str], default: str = "") -> str:
    """Strips quotes and whitespace added by Docker, Render, or env files."""
    if val is None:
        return default
    v = str(val).strip()
    if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
        v = v[1:-1].strip()
    return v


def get_email_config() -> Dict[str, Any]:
    """Dynamically reads and sanitizes the latest email configuration from .env and environment."""
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_path):
        load_dotenv(env_path, override=True)
    else:
        load_dotenv(override=True)

    host = clean_val(os.getenv("SMTP_HOST"), "smtp-relay.brevo.com")
    port_str = clean_val(os.getenv("SMTP_PORT"), "465")
    port = int(port_str) if port_str.isdigit() else 465
    user = clean_val(os.getenv("SMTP_USER"))
    password = clean_val(os.getenv("SMTP_PASSWORD"))
    from_name = clean_val(os.getenv("SMTP_FROM_NAME"), "OpenMNC Backend")
    
    # Brevo requires a verified sender email (not @smtp-brevo.com login)
    from_email = clean_val(os.getenv("SMTP_FROM_EMAIL"))
    if not from_email or from_email.endswith("@smtp-brevo.com"):
        admin_email = clean_val(os.getenv("ADMIN_EMAIL"), "openmnc.contract@gmail.com")
        from_email = admin_email

    resend_key = clean_val(os.getenv("RESEND_API_KEY"))

    is_configured = bool(user and password and host and password != "your_brevo_smtp_key")
    return {
        "host": host,
        "port": port,
        "user": user,
        "password": password,
        "from_name": from_name,
        "from_email": from_email,
        "resend_key": resend_key,
        "is_configured": is_configured,
    }


def is_smtp_configured() -> bool:
    """Returns True if valid SMTP credentials are configured."""
    return get_email_config()["is_configured"]


def dispatch_smtp_message(cfg: Dict[str, Any], to_email: str, msg: MIMEMultipart) -> Tuple[bool, str]:
    """
    Attempts delivery across multiple ports:
    1. Port 465 (SSL direct) — fastest and most reliable on cloud platforms like Render
    2. Port 587 (STARTTLS)
    3. Port 2525 (Alternative STARTTLS)
    """
    if not cfg["is_configured"]:
        return False, "SMTP credentials missing (SMTP_USER or SMTP_PASSWORD empty)"

    attempts = [
        (cfg["host"], 465, "ssl"),
        (cfg["host"], 587, "starttls"),
        (cfg["host"], 2525, "starttls"),
        ("smtp-relay.brevo.com", 465, "ssl"),
        ("smtp-relay.brevo.com", 587, "starttls"),
    ]
    seen = set()
    unique = []
    for a in attempts:
        if a not in seen:
            seen.add(a)
            unique.append(a)

    errors = []
    for host, port, mode in unique:
        try:
            logger.info(f"[EmailService] Attempting delivery to {to_email} via {host}:{port} ({mode})")
            if mode == "ssl":
                ctx = ssl.create_default_context()
                with smtplib.SMTP_SSL(host, port, context=ctx, timeout=8) as server:
                    server.ehlo()
                    server.login(cfg["user"], cfg["password"])
                    server.sendmail(cfg["from_email"], [to_email], msg.as_string())
            else:
                with smtplib.SMTP(host, port, timeout=8) as server:
                    server.ehlo()
                    server.starttls()
                    server.ehlo()
                    server.login(cfg["user"], cfg["password"])
                    server.sendmail(cfg["from_email"], [to_email], msg.as_string())
            
            success_msg = f"{host}:{port} ({mode})"
            logger.info(f"[EmailService] Email dispatched successfully to {to_email} via {success_msg}")
            return True, success_msg
        except Exception as e:
            err = f"{host}:{port}({mode}): {type(e).__name__}({str(e)})"
            logger.warning(f"[EmailService] Attempt failed: {err}")
            errors.append(err)

    return False, " | ".join(errors)


async def send_otp_email(to_email: str, otp_code: str, user_name: Optional[str] = None) -> Dict[str, Any]:
    """
    Sends a secure 6-digit OTP code to the verified administrator or invited team member.
    """
    cfg = get_email_config()
    subject = f"Your OpenMNC Admin Verification Code: {otp_code}"
    display_name = user_name or to_email.split("@")[0].capitalize()

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8">
      <title>OpenMNC Security Code</title>
      <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background-color: #0a0e1a; color: #e2e8f0; margin: 0; padding: 24px; }}
        .card {{ max-width: 520px; margin: 0 auto; background: #0f172a; border: 1px solid rgba(0, 245, 255, 0.2); border-radius: 16px; padding: 32px; box-shadow: 0 10px 25px rgba(0,0,0,0.5); }}
        .logo {{ font-size: 24px; font-weight: 800; color: #ffffff; margin-bottom: 24px; text-align: center; }}
        .logo span {{ color: #00f5ff; }}
        .badge {{ display: inline-block; background: rgba(0, 245, 255, 0.1); color: #00f5ff; padding: 4px 12px; border-radius: 999px; font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 16px; }}
        .otp-box {{ background: rgba(255, 255, 255, 0.03); border: 2px dashed #00f5ff; border-radius: 12px; padding: 20px; text-align: center; margin: 24px 0; }}
        .otp-code {{ font-size: 38px; font-weight: 800; letter-spacing: 10px; color: #00f5ff; font-family: monospace; }}
        .info {{ color: #94a3b8; font-size: 14px; line-height: 1.6; }}
        .footer {{ margin-top: 32px; padding-top: 20px; border-top: 1px solid rgba(255, 255, 255, 0.08); font-size: 12px; color: #64748b; text-align: center; }}
      </style>
    </head>
    <body>
      <div class="card">
        <div class="logo">Open<span>MNC</span> LLP</div>
        <div style="text-align: center;">
          <span class="badge">Admin Security Verification</span>
        </div>
        <h2 style="color: #ffffff; margin-top: 8px; font-size: 20px; text-align: center;">One-Time Login Passcode</h2>
        <p class="info">Hello <strong>{display_name}</strong>,</p>
        <p class="info">You requested a secure login or password reset for the OpenMNC Control Center. Use the one-time verification passcode below to complete your authorization:</p>
        
        <div class="otp-box">
          <div class="otp-code">{otp_code}</div>
          <p style="margin: 8px 0 0; font-size: 12px; color: #94a3b8;">Valid for 10 minutes. Do not share this code with anyone.</p>
        </div>

        <p class="info">If you did not request this login attempt, your account remains protected. Please contact the primary administrator at <strong>hello@openmnc.com</strong> immediately.</p>

        <div class="footer">
          OpenMNC LLP &bull; Automated Security Gateway<br>
          Powered by Brevo High-Speed SMTP Relay &bull; 24/7 Security
        </div>
      </div>
    </body>
    </html>
    """

    text_content = f"""OpenMNC LLP — Admin Security Code

Hello {display_name},

Your one-time login verification code is: {otp_code}

This code expires in 10 minutes. If you did not request this code, ignore this email.

OpenMNC Security Team
https://openmnc.com
"""

    import uuid
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{cfg['from_name']} <{cfg['from_email']}>"
    msg["To"] = to_email
    msg["Reply-To"] = cfg["from_email"]
    msg["Message-ID"] = f"<{uuid.uuid4()}@openmnc.com>"
    msg["X-Mailer"] = "OpenMNC Secure Mailer v2"
    msg["Auto-Submitted"] = "auto-generated"
    msg.attach(MIMEText(text_content, "plain"))
    msg.attach(MIMEText(html_content, "html"))

    # 1. Attempt Multi-Port SMTP Delivery
    if cfg["is_configured"]:
        ok, detail = dispatch_smtp_message(cfg, to_email, msg)
        if ok:
            return {"status": "sent", "provider": "brevo_smtp", "recipient": to_email, "detail": detail}
        else:
            logger.error(f"[EmailService] All SMTP ports failed: {detail}")

    # 2. Resend API fallback if configured
    if cfg["resend_key"]:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(
                    "https://api.resend.com/emails",
                    headers={"Authorization": f"Bearer {cfg['resend_key']}"},
                    json={
                        "from": f"{cfg['from_name']} <{cfg['from_email']}>",
                        "to": [to_email],
                        "subject": subject,
                        "html": html_content,
                    },
                )
                if res.status_code in (200, 201):
                    logger.info(f"[EmailService] Resend API dispatched OTP to {to_email}")
                    return {"status": "sent", "provider": "resend", "recipient": to_email}
        except Exception as e:
            logger.error(f"[EmailService] Resend dispatch error: {e}")

    # 3. Development Fallback (Logs to console)
    logger.info(f"[EmailService] Fallback Mock Dispatch: OTP for {to_email} is {otp_code}")
    print(f"\n=======================================================")
    print(f"[OPENMNC SECURITY DISPATCH]")
    print(f"Recipient: {to_email}")
    print(f"6-Digit OTP Code: {otp_code}")
    print(f"Validity: 10 minutes")
    print(f"SMTP Configured: {cfg['is_configured']} (Host: {cfg['host']})")
    print(f"=======================================================\n")

    return {
        "status": "mock_delivered",
        "provider": "console",
        "recipient": to_email,
        "note": "SMTP not configured or failed. Code logged for security.",
    }


async def send_team_invite_email(
    to_email: str,
    invite_url: str,
    role: str = "Editor",
    invited_by: str = "Administrator",
    recipient_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Sends an official team invitation email with an activation link via Brevo SMTP relay.
    """
    cfg = get_email_config()
    role_display = role.capitalize()
    display_name = recipient_name or to_email.split("@")[0].capitalize()
    subject = f"Invitation: Join the OpenMNC Team as {role_display}"

    role_descriptions = {
        "admin": "Full system control, team access permissions, applicant review, and system configurations.",
        "editor": "Manage jobs, applicant resumes, services copy, and blog publications.",
        "author": "Draft, edit, and publish blogs, articles, and news releases.",
    }
    role_info = role_descriptions.get(role.lower(), "Collaborate with the OpenMNC team.")

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8">
      <title>OpenMNC Team Invitation</title>
      <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background-color: #0a0e1a; color: #e2e8f0; margin: 0; padding: 24px; }}
        .card {{ max-width: 540px; margin: 0 auto; background: #0f172a; border: 1px solid rgba(0, 245, 255, 0.25); border-radius: 16px; padding: 32px; box-shadow: 0 10px 30px rgba(0,0,0,0.6); }}
        .logo {{ font-size: 26px; font-weight: 800; color: #ffffff; margin-bottom: 20px; text-align: center; }}
        .logo span {{ color: #00f5ff; }}
        .badge {{ display: inline-block; background: rgba(0, 245, 255, 0.12); color: #00f5ff; padding: 5px 14px; border-radius: 999px; font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: 1px; }}
        .btn {{ display: inline-block; background: linear-gradient(135deg, #00f5ff 0%, #00b4d8 100%); color: #0a0e1a; font-weight: 700; font-size: 14px; padding: 14px 28px; border-radius: 10px; text-decoration: none; margin: 24px 0; box-shadow: 0 4px 15px rgba(0, 245, 255, 0.3); }}
        .role-box {{ background: rgba(255, 255, 255, 0.03); border-left: 3px solid #00f5ff; border-radius: 8px; padding: 14px 16px; margin: 18px 0; }}
        .info {{ color: #94a3b8; font-size: 14px; line-height: 1.6; }}
        .link-text {{ word-break: break-all; font-family: monospace; font-size: 11px; color: #38bdf8; }}
        .footer {{ margin-top: 32px; padding-top: 20px; border-top: 1px solid rgba(255, 255, 255, 0.08); font-size: 12px; color: #64748b; text-align: center; }}
      </style>
    </head>
    <body>
      <div class="card">
        <div class="logo">Open<span>MNC</span> LLP</div>
        <div style="text-align: center; margin-bottom: 20px;">
          <span class="badge">Official Team Invitation</span>
        </div>
        
        <h2 style="color: #ffffff; margin-top: 0; font-size: 20px; text-align: center;">You've Been Invited to Join the Team</h2>
        
        <p class="info">Hello <strong>{display_name}</strong>,</p>
        <p class="info">
          <strong>{invited_by}</strong> has granted you official access to the <strong>OpenMNC Control Center</strong> with the role of <strong>{role_display}</strong>.
        </p>

        <div class="role-box">
          <div style="color: #00f5ff; font-weight: 700; font-size: 13px; text-transform: uppercase; margin-bottom: 4px;">
            Role: {role_display}
          </div>
          <div style="color: #cbd5e1; font-size: 13px;">
            {role_info}
          </div>
        </div>

        <p class="info">Click below to activate your account, set your password, and start collaborating:</p>

        <div style="text-align: center;">
          <a href="{invite_url}" class="btn" target="_blank">Accept Invitation & Join Team &rarr;</a>
        </div>

        <p class="info" style="font-size: 12px;">Or copy and paste this secure link into your browser:</p>
        <p class="link-text">{invite_url}</p>

        <p class="info" style="font-size: 12px; margin-top: 20px;">
          🔒 <em>This invitation link is valid for 7 days. If you were not expecting this invitation, you can safely ignore this email.</em>
        </p>

        <div class="footer">
          OpenMNC LLP &bull; Team & Workspace Access Gateway<br>
          Automated Transactional Dispatch via Brevo SMTP Relay
        </div>
      </div>
    </body>
    </html>
    """

    text_content = f"""OpenMNC LLP — Official Team Invitation

Hello {display_name},

{invited_by} has invited you to join OpenMNC as {role_display}.

Click the link below to accept your invitation and activate your account:
{invite_url}

This invitation link is valid for 7 days.

OpenMNC Team
https://openmnc.com
"""

    import uuid
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{cfg['from_name']} <{cfg['from_email']}>"
    msg["To"] = to_email
    msg["Reply-To"] = cfg["from_email"]
    msg["Message-ID"] = f"<{uuid.uuid4()}@openmnc.com>"
    msg["X-Mailer"] = "OpenMNC Secure Mailer v2"
    msg["Auto-Submitted"] = "auto-generated"
    msg.attach(MIMEText(text_content, "plain"))
    msg.attach(MIMEText(html_content, "html"))

    # 1. Attempt Multi-Port SMTP Delivery
    if cfg["is_configured"]:
        ok, detail = dispatch_smtp_message(cfg, to_email, msg)
        if ok:
            return {"status": "sent", "provider": "brevo_smtp", "recipient": to_email, "detail": detail}
        else:
            logger.error(f"[EmailService] All SMTP ports failed for invite to {to_email}: {detail}")
            # Don't silently fall through to mock — return a real error so the API can surface it
            return {"status": "smtp_failed", "provider": "brevo_smtp", "recipient": to_email, "detail": detail}

    # 2. Resend API fallback (only if SMTP is not configured at all)
    if cfg["resend_key"]:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(
                    "https://api.resend.com/emails",
                    headers={"Authorization": f"Bearer {cfg['resend_key']}"},
                    json={
                        "from": f"{cfg['from_name']} <{cfg['from_email']}>",
                        "to": [to_email],
                        "subject": subject,
                        "html": html_content,
                    },
                )
                if res.status_code in (200, 201):
                    logger.info(f"[EmailService] Resend API dispatched invite to {to_email}")
                    return {"status": "sent", "provider": "resend", "recipient": to_email}
                else:
                    err_body = res.text[:300]
                    logger.error(f"[EmailService] Resend API error {res.status_code}: {err_body}")
                    return {"status": "resend_failed", "detail": f"Resend HTTP {res.status_code}: {err_body}"}
        except Exception as e:
            logger.error(f"[EmailService] Resend dispatch error: {e}")
            return {"status": "resend_failed", "detail": str(e)}

    # 3. Development Fallback (only when NO email provider is configured at all)
    logger.info(f"[EmailService] Mock Dispatch Invite: {to_email} -> {invite_url}")
    print(f"\n=======================================================")
    print(f"[OPENMNC INVITATION DISPATCH]")
    print(f"Recipient: {to_email}")
    print(f"Role: {role_display}")
    print(f"Join URL: {invite_url}")
    print(f"Validity: 7 days")
    print(f"=======================================================\n")

    return {
        "status": "mock_delivered",
        "provider": "console",
        "recipient": to_email,
        "invite_url": invite_url,
    }
