import base64
import json
import os
from typing import Dict, Any

from fastapi import APIRouter, Header, HTTPException, Request

from db.models import create_email
from shared.logger import logger

webhook_router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


@webhook_router.post("/gmail")
async def gmail_webhook(
    request: Request,
    x_webhook_secret: str = Header(None)
):
    """
    Handle Google Cloud Pub/Sub push notifications for Gmail.
    
    Expects a payload like:
    {
        "message": {
            "data": "base64_encoded_json",
            "messageId": "..."
        }
    }
    """
    # 1. Validate secret token (prevents unauthorized hits)
    expected_secret = os.getenv("GMAIL_WEBHOOK_SECRET")
    if expected_secret and x_webhook_secret != expected_secret:
        logger.warning("Unauthorized webhook attempt")
        raise HTTPException(status_code=401, detail="Unauthorized")

    payload = await request.json()
    
    # 2. Extract Pub/Sub data
    try:
        data_b64 = payload.get("message", {}).get("data")
        if not data_b64:
            raise ValueError("Missing message data")
            
        # Decode base64 data
        decoded_data = json.loads(base64.b64decode(data_b64).decode("utf-8"))
        email_address = decoded_data.get("emailAddress")
        history_id = decoded_data.get("historyId")
        
        logger.info(f"Received Gmail push for {email_address} (historyId: {history_id})")

        # NOTE: In a real flow, we would now use the historyId to fetch 
        # the actual message content via Gmail API. 
        # For now, we just log the event.
        
        return {"status": "accepted", "historyId": history_id}

    except Exception as e:
        logger.error(f"Error processing Gmail webhook: {str(e)}")
        raise HTTPException(status_code=400, detail="Invalid payload")
