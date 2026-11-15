"""
Transactional Email Service for OpenMNC LLP
Optimized for Brevo (Sendinblue) 300 free emails/day & Gmail SMTP.
Features:
1. Dynamic environment variable reload (reads latest .env changes on the fly)
2. Brevo sender auto-detection (ensures valid verified sender)
3. Zero-crash console fallback for testing
"""

import os
import sys
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional, Dict, Any
from dotenv import load_dotenv

logger = logging.getLogger("openmnc.email_service")


def get_email_config() -> Dict[str, Any]:
    """Dynamically reads the latest email configuration from .env."""
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_path):
        load_dotenv(env_path, override=True)
    else:
        load_dotenv(override=True)
    host = os.getenv("SMTP_HOST", "smtp-relay.brevo.com")
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("SMTP_USER", "").strip()
    password = os.getenv("SMTP_PASSWORD", "").strip()
    from_name = os.getenv("SMTP_FROM_NAME", "OpenMNC Security Team").strip()
    
    # Brevo requires a real sender email (not @smtp-brevo.com login)
    from_email = os.getenv("SMTP_FROM_EMAIL", "").strip()
    if not from_email or from_email.endswith("@smtp-brevo.com"):
        admin_email = os.getenv("ADMIN_EMAIL", "amit@openmnc.com")
        from_email = admin_email

    resend_key = os.getenv("RESEND_API_KEY", "").strip()

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

    # 1. Attempt SMTP (Brevo or Gmail)
    if cfg["is_configured"]:
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = f"{cfg['from_name']} <{cfg['from_email']}>"
            msg["To"] = to_email

            msg.attach(MIMEText(text_content, "plain"))
            msg.attach(MIMEText(html_content, "html"))

            with smtplib.SMTP(cfg["host"], cfg["port"], timeout=12) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(cfg["user"], cfg["password"])
                server.sendmail(cfg["from_email"], [to_email], msg.as_string())

            logger.info(f"[EmailService] Real OTP email dispatched successfully to {to_email} via {cfg['host']}")
            print(f"\n[Brevo SMTP] Real email sent successfully to {to_email}!")
            return {"status": "sent", "provider": "brevo_smtp", "recipient": to_email}
        except smtplib.SMTPAuthenticationError as e:
            logger.error(f"[EmailService] Brevo authentication failed. Check your SMTP_USER and SMTP_PASSWORD: {e}")
            print(f"\n[Brevo Error] Authentication failed: {e}\nPlease check your SMTP key.")
        except Exception as e:
            logger.error(f"[EmailService] SMTP send error: {e}")
            print(f"\n[Brevo Error] SMTP send error: {e}")

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
        .btn:hover {{ background: #00f5ff; }}
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

    # 1. Attempt Brevo SMTP
    if cfg["is_configured"]:
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = f"{cfg['from_name']} <{cfg['from_email']}>"
            msg["To"] = to_email

            msg.attach(MIMEText(text_content, "plain"))
            msg.attach(MIMEText(html_content, "html"))

            with smtplib.SMTP(cfg["host"], cfg["port"], timeout=12) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(cfg["user"], cfg["password"])
                server.sendmail(cfg["from_email"], [to_email], msg.as_string())

            logger.info(f"[EmailService] Invitation email dispatched to {to_email} via Brevo")
            print(f"\n[Brevo SMTP] Team invitation sent successfully to {to_email}!")
            return {"status": "sent", "provider": "brevo_smtp", "recipient": to_email}
        except Exception as e:
            logger.error(f"[EmailService] SMTP error sending team invite: {e}")
            print(f"\n[Brevo Error] SMTP invite error: {e}")

    # 2. Resend API fallback
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
        except Exception as e:
            logger.error(f"[EmailService] Resend dispatch error: {e}")

    # 3. Development Fallback
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


if __name__ == "__main__":
    import asyncio
    target = sys.argv[1] if len(sys.argv) > 1 else "amit@openmnc.com"
    print(f"Testing Brevo SMTP dispatch to: {target}...")
    result = asyncio.run(send_otp_email(target, "123456", "Amit Barai"))
    print(f"Result: {result}")
