import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from loguru import logger

# Add project root to sys.path
root_path = Path(__file__).parent.parent.parent
sys.path.append(str(root_path))

from agents.intent_agent.extractor import IntentExtractor

# Validate required environment variables
if not os.getenv("OPENAI_API_KEY"):
    raise RuntimeError("OPENAI_API_KEY not set in environment variables.")

app = FastAPI(
    title="SecureIntent Orchestrator API",
    version="0.1.0",
    description="Agentic Zero-Trust Email Automation System"
)

# Initialize extractor
intent_extractor = IntentExtractor()


# -----------------------------
# Request / Response Models
# -----------------------------

class EmailRequest(BaseModel):
    subject: str
    body: str


class IntentResponse(BaseModel):
    intent: dict
    status: str
    reason: str | None = None


# -----------------------------
# Routes
# -----------------------------

@app.get("/health")
async def health_check():
    return {"status": "ok"}


@app.post("/extract-intent", response_model=IntentResponse)
async def extract_intent(email: EmailRequest):
    """
    Extract structured intent from email content.
    """

    try:
        result = await intent_extractor.extract(
            subject=email.subject,
            body=email.body
        )

        return result

    except Exception as e:
        logger.exception("Intent extraction failed")
        raise HTTPException(
            status_code=500,
            detail=f"Intent extraction failed: {str(e)}"
        )
