"""
Google Workspace Integration Service for OpenMNC LLP
1. Zero-Storage Resume Handling:
   - Resumes are stored on Google Drive (never binary bloat on MongoDB free 512MB tier).
2. Google Sheets Auto-Sync:
   - When a candidate applies, their details (name, email, phone, job, drive link, timestamp)
     are synced directly to HR's Google Sheet via Google Service Account or Google Apps Script Webhook.
"""

import os
import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional

logger = logging.getLogger("openmnc.google_service")

# Environment configurations
GOOGLE_APPS_SCRIPT_WEBHOOK_URL = os.getenv("GOOGLE_APPS_SCRIPT_WEBHOOK_URL", "")
GOOGLE_SERVICE_ACCOUNT_JSON = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "")
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "")


async def append_candidate_to_google_sheet(candidate_data: Dict[str, Any]) -> bool:
    """
    Appends candidate application row directly to Google Sheets.
    Supports either:
    1. GOOGLE_APPS_SCRIPT_WEBHOOK_URL (Zero external library setup, 1-click Google Apps Script URL)
    2. Direct Google Sheets API via service account credentials
    """
    timestamp = candidate_data.get("applied_at", datetime.now(timezone.utc).isoformat())
    payload = {
        "timestamp": str(timestamp),
        "job_title": candidate_data.get("job_title", ""),
        "candidate_name": candidate_data.get("candidate_name", ""),
        "candidate_email": candidate_data.get("candidate_email", ""),
        "candidate_phone": candidate_data.get("candidate_phone", ""),
        "resume_google_drive_url": candidate_data.get("resume_google_drive_url", ""),
        "portfolio_url": candidate_data.get("portfolio_or_github_url", ""),
        "linkedin_url": candidate_data.get("linkedin_url", ""),
        "status": candidate_data.get("status", "Applied"),
    }

    # Method 1: Google Apps Script Webhook (Recommended & Instant for HR)
    if GOOGLE_APPS_SCRIPT_WEBHOOK_URL:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(GOOGLE_APPS_SCRIPT_WEBHOOK_URL, json=payload)
                if res.status_code in (200, 201, 302):
                    logger.info("Successfully pushed candidate to Google Sheet via Webhook")
                    return True
                else:
                    logger.warning(f"Google Apps Script returned status {res.status_code}: {res.text}")
        except Exception as e:
            logger.error(f"Failed to post to Google Apps Script webhook: {e}")

    # Method 2: Google Service Account
    if GOOGLE_SERVICE_ACCOUNT_JSON and GOOGLE_SHEET_ID:
        try:
            # If Google client libraries are available
            from google.oauth2 import service_account
            from googleapiclient.discovery import build

            creds_dict = json.loads(GOOGLE_SERVICE_ACCOUNT_JSON)
            creds = service_account.Credentials.from_service_account_info(
                creds_dict,
                scopes=["https://www.googleapis.com/auth/spreadsheets"],
            )
            service = build("sheets", "v4", credentials=creds)
            values = [[
                payload["timestamp"],
                payload["job_title"],
                payload["candidate_name"],
                payload["candidate_email"],
                payload["candidate_phone"],
                payload["resume_google_drive_url"],
                payload["portfolio_url"],
                payload["linkedin_url"],
                payload["status"],
            ]]
            body = {"values": values}
            service.spreadsheets().values().append(
                spreadsheetId=GOOGLE_SHEET_ID,
                range="Sheet1!A:I",
                valueInputOption="USER_ENTERED",
                body=body,
            ).execute()
            logger.info("Successfully appended candidate to Google Sheet via Sheets API")
            return True
        except Exception as e:
            logger.error(f"Failed to append to Google Sheets API: {e}")

    logger.info("Candidate registered in database. Google Sheets integration ready when env vars are set.")
    return False
