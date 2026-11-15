"""
Deploy Webhook Service for OpenMNC LLP
Triggers Vercel / Netlify rebuild webhooks whenever CMS content changes
(Blog articles, Services, or Careers) so that static pre-renders and AI SEO schemas
are instantly updated for search crawlers (Perplexity, ChatGPT, Google).
"""

import os
import logging
import httpx

logger = logging.getLogger("openmnc.webhook_service")

VERCEL_DEPLOY_HOOK_URL = os.getenv("VERCEL_DEPLOY_HOOK_URL", "")
NETLIFY_BUILD_HOOK_URL = os.getenv("NETLIFY_BUILD_HOOK_URL", "")


async def trigger_deploy_hook(reason: str = "CMS Content Update") -> bool:
    """
    Sends an async POST request to the Vercel/Netlify deploy hook.
    Ensures pre-rendered static HTML and JSON-LD schemas are refreshed.
    """
    target_url = VERCEL_DEPLOY_HOOK_URL or NETLIFY_BUILD_HOOK_URL
    if not target_url:
        logger.info(f"[DeployHook] No hook configured (VERCEL_DEPLOY_HOOK_URL unset). Reason: {reason}")
        return False

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.post(target_url, json={"trigger": reason, "service": "OpenMNC Backend"})
            if res.status_code in (200, 201, 204):
                logger.info(f"[DeployHook] Rebuild triggered successfully for: {reason}")
                return True
            else:
                logger.warning(f"[DeployHook] Hook returned {res.status_code}: {res.text}")
                return False
    except Exception as e:
        logger.error(f"[DeployHook] Error invoking deploy hook: {e}")
        return False
