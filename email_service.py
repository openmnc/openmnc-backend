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
        import email.utils
        # We need to build the MIME message here to pass to the thread
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{cfg['from_name']} <{cfg['from_email']}>"
        msg["To"] = to_email
        msg["Reply-To"] = cfg["from_email"]
        msg["Message-ID"] = f"<{uuid.uuid4()}@openmnc.com>"
        msg["Date"] = email.utils.formatdate(localtime=True)
        msg["X-Mailer"] = "OpenMNC Enterprise Gateway"
        msg["Auto-Submitted"] = "auto-generated"
        msg["X-Auto-Response-Suppress"] = "OOF, AutoReply"
        msg["Precedence"] = "bulk"
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
    subject = f"Your OpenMNC Verification Code: {otp_code}"
    display_name = user_name or to_email.split("@")[0].capitalize()

    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="utf-8">
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
      <title>OpenMNC Verification Code</title>
      <style>
        body {{ margin: 0; padding: 0; background-color: #f8fafc; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #1e293b; }}
        table {{ border-collapse: collapse; }}
        .wrapper {{ width: 100%; table-layout: fixed; background-color: #f8fafc; padding: 40px 16px; }}
        .card {{ max-width: 540px; margin: 0 auto; background: #ffffff; border-radius: 14px; border: 1px solid #e2e8f0; box-shadow: 0 4px 16px rgba(15, 23, 42, 0.05); overflow: hidden; }}
        .header {{ padding: 32px 32px 24px; text-align: center; border-bottom: 1px solid #f1f5f9; }}
        .logo-text {{ font-size: 24px; font-weight: 800; color: #0f172a; letter-spacing: -0.5px; margin: 0; }}
        .logo-accent {{ color: #0891b2; }}
        .badge {{ display: inline-block; background: #ecfeff; color: #0891b2; padding: 4px 12px; border-radius: 9999px; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.8px; margin-top: 10px; }}
        .body {{ padding: 32px; }}
        .title {{ font-size: 19px; font-weight: 700; color: #0f172a; margin: 0 0 12px; }}
        .text {{ font-size: 14px; line-height: 1.6; color: #475569; margin: 0 0 18px; }}
        .otp-box {{ background: #f8fafc; border: 2px dashed #0891b2; border-radius: 12px; padding: 20px; text-align: center; margin: 24px 0; }}
        .otp-code {{ font-size: 36px; font-weight: 800; letter-spacing: 10px; color: #0891b2; font-family: 'Courier New', Courier, monospace; margin: 0; }}
        .otp-sub {{ font-size: 12px; color: #64748b; margin: 8px 0 0; }}
        .footer {{ padding: 24px 32px; background: #f8fafc; border-top: 1px solid #f1f5f9; text-align: center; font-size: 12px; color: #94a3b8; line-height: 1.5; }}
      </style>
    </head>
    <body>
      <div class="wrapper">
        <div class="card">
          <div class="header">
            <table cellpadding="0" cellspacing="0" border="0" style="margin: 0;">
              <tr>
                <td style="vertical-align: middle; padding-right: 10px;">
                  <img src="https://www.openmnc.com/logo.png" alt="OpenMNC" width="36" height="36" style="display: block; border-radius: 4px;" />
                </td>
                <td style="vertical-align: middle;">
                  <h1 class="logo-text" style="margin: 0;">Open<span class="logo-accent">MNC</span></h1>
                </td>
              </tr>
            </table>
            <span class="badge">Security Verification</span>
          </div>
          <div class="body">
            <h2 class="title">Your One-Time Passcode</h2>
            <p class="text">Hello <strong>{display_name}</strong>,</p>
            <p class="text">Use the 6-digit verification code below to authorize your sign-in to the OpenMNC Control Center:</p>
            
            <div class="otp-box">
              <div class="otp-code">{otp_code}</div>
              <p class="otp-sub">Valid for 10 minutes. For security, never share this code with anyone.</p>
            </div>

            <p class="text">If you did not request this login attempt, please disregard this email. Your account remains protected.</p>
          </div>
          <div class="footer">
            <strong>OpenMNC LLP</strong> &bull; Technology &amp; Enterprise Solutions<br>
            Automated Security Dispatch &bull; Official Account Notice<br>
            <a href="https://www.openmnc.com" style="color: #0891b2; text-decoration: none;">openmnc.com</a>
          </div>
        </div>
      </div>
    </body>
    </html>
    """

    text_content = f"""OpenMNC — Security Verification Code

Hello {display_name},

Your one-time verification passcode is: {otp_code}

This code expires in 10 minutes. If you did not request this code, you can safely ignore this email.

OpenMNC Security Team
https://www.openmnc.com
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
    Guarantees that public links strictly use https://www.openmnc.com (never localhost).
    """
    cfg = get_email_config()
    role_display = role.capitalize()
    display_name = recipient_name or to_email.split("@")[0].capitalize()
    subject = f"You're invited to join OpenMNC as {role_display}"

    # Strict protection: NEVER let an email link point to localhost!
    if "localhost" in invite_url or "127.0.0.1" in invite_url:
        from urllib.parse import urlparse
        parsed = urlparse(invite_url)
        path = parsed.path or "/admin/join"
        query = f"?{parsed.query}" if parsed.query else ""
        invite_url = f"https://www.openmnc.com{path}{query}"

    role_descriptions = {
        "admin": "Full system control, team access permissions, applicant review, and system configurations.",
        "editor": "Manage jobs, applicant resumes, services copy, and blog publications.",
        "author": "Draft, edit, and publish blogs, articles, and news releases.",
    }
    role_info = role_descriptions.get(role.lower(), "Collaborate with the OpenMNC team.")

    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="utf-8">
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
      <title>OpenMNC Team Invitation</title>
      <style>
        body {{ margin: 0; padding: 0; background-color: #f8fafc; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #1e293b; }}
        table {{ border-collapse: collapse; }}
        .wrapper {{ width: 100%; table-layout: fixed; background-color: #f8fafc; padding: 40px 16px; }}
        .card {{ max-width: 560px; margin: 0 auto; background: #ffffff; border-radius: 14px; border: 1px solid #e2e8f0; box-shadow: 0 4px 16px rgba(15, 23, 42, 0.05); overflow: hidden; }}
        .header {{ padding: 32px 32px 24px; text-align: center; border-bottom: 1px solid #f1f5f9; }}
        .logo-text {{ font-size: 24px; font-weight: 800; color: #0f172a; letter-spacing: -0.5px; margin: 0; }}
        .logo-accent {{ color: #0891b2; }}
        .badge {{ display: inline-block; background: #ecfeff; color: #0891b2; padding: 4px 12px; border-radius: 9999px; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.8px; margin-top: 10px; }}
        .body {{ padding: 32px; }}
        .title {{ font-size: 20px; font-weight: 700; color: #0f172a; margin: 0 0 12px; }}
        .text {{ font-size: 14px; line-height: 1.6; color: #475569; margin: 0 0 18px; }}
        .role-box {{ background: #f8fafc; border-left: 4px solid #0891b2; border-radius: 8px; padding: 16px; margin: 20px 0; }}
        .role-name {{ font-size: 13px; font-weight: 700; color: #0891b2; text-transform: uppercase; letter-spacing: 0.5px; margin: 0 0 4px; }}
        .role-desc {{ font-size: 13px; color: #475569; margin: 0; line-height: 1.5; }}
        .btn-wrapper {{ text-align: center; margin: 28px 0; }}
        .btn {{ display: inline-block; background-color: #0891b2; color: #ffffff !important; font-weight: 700; font-size: 14px; padding: 14px 28px; border-radius: 8px; text-decoration: none; }}
        .link-note {{ font-size: 12px; color: #64748b; margin: 20px 0 6px; }}
        .link-text {{ font-size: 11px; font-family: 'Courier New', Courier, monospace; color: #0891b2; word-break: break-all; margin: 0 0 20px; background: #f8fafc; padding: 8px 12px; border-radius: 6px; border: 1px solid #e2e8f0; }}
        .notice {{ font-size: 12px; color: #94a3b8; font-style: italic; margin: 16px 0 0; }}
        .footer {{ padding: 24px 32px; background: #f8fafc; border-top: 1px solid #f1f5f9; text-align: center; font-size: 12px; color: #94a3b8; line-height: 1.5; }}
      </style>
    </head>
    <body>
      <div class="wrapper">
        <div class="card">
          <div class="header">
            <table cellpadding="0" cellspacing="0" border="0" style="margin: 0;">
              <tr>
                <td style="vertical-align: middle; padding-right: 10px;">
                  <img src="https://www.openmnc.com/logo.png" alt="OpenMNC" width="36" height="36" style="display: block; border-radius: 4px;" />
                </td>
                <td style="vertical-align: middle;">
                  <h1 class="logo-text" style="margin: 0;">Open<span class="logo-accent">MNC</span></h1>
                </td>
              </tr>
            </table>
            <span class="badge">Team Invitation</span>
          </div>
          <div class="body">
            <h2 class="title">Join the OpenMNC Team</h2>
            <p class="text">Hello <strong>{display_name}</strong>,</p>
            <p class="text">
              <strong>{invited_by}</strong> has granted you official access to the <strong>OpenMNC Control Center</strong> with the role of <strong>{role_display}</strong>.
            </p>

            <div class="role-box">
              <div class="role-name">Assigned Role: {role_display}</div>
              <div class="role-desc">{role_info}</div>
            </div>

            <p class="text">Click the secure button below to activate your account, set your password, and begin collaborating:</p>

            <div class="btn-wrapper">
              <a href="{invite_url}" class="btn" target="_blank" style="color: #ffffff !important; text-decoration: none;">Accept Invitation &amp; Join Team &rarr;</a>
            </div>

            <p class="link-note">If the button above does not open, copy and paste this link into your browser:</p>
            <div class="link-text">{invite_url}</div>

            <p class="notice">
              🔒 This activation link is unique to you and valid for 7 days. If you were not expecting this invitation, you can disregard this email.
            </p>
          </div>
          <div class="footer">
            <strong>OpenMNC LLP</strong> &bull; Technology &amp; Enterprise Solutions<br>
            Automated Workspace Access Gateway &bull; Official Team Notice<br>
            <a href="https://www.openmnc.com" style="color: #0891b2; text-decoration: none;">openmnc.com</a>
          </div>
        </div>
      </div>
    </body>
    </html>
    """

    text_content = f"""OpenMNC — Official Team Invitation

Hello {display_name},

{invited_by} has invited you to join OpenMNC as {role_display}.

Role Overview: {role_info}

Click the secure link below to accept your invitation and activate your account:
{invite_url}

This invitation link is valid for 7 days.

OpenMNC Team
https://www.openmnc.com
"""

    return await _send_email(to_email, subject, html_content, text_content)
