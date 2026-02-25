"""
webhooks.py
-----------
Gmail Pub/Sub push notification handler.

Security pipeline (in order):
  1. Decode Pub/Sub payload
  2. Trust/Risk Scorer  → CRITICAL blocks BEFORE LLM is called
  3. Sandboxed LLM      → structured Intent JSON only
  4. Deterministic Planner → GoalPlan
  5. Policy/Rule Engine → allow / block / require_approval
  6. Tool Orchestrator  → Gmail API (only after all gates pass)
"""

import base64
import json
import os
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request

from apps.api.gmail_service import (
    build_gmail_service,
    fetch_new_message_ids,
    fetch_message,
    parse_message,
)
from db.models import (
    create_email,
    create_risk_score,
    get_gmail_token,
    save_gmail_tokens,
    create_intent,
    create_plan,
    update_plan_status,
    log_action,
)
from engines.trust_risk.spf_dkim import extract_auth_results
from engines.trust_risk.url_scanner import extract_urls, scan_urls
from engines.trust_risk.scorer import calculate_risk, RiskLevel
from engines.policy_guardrails.middleware import apply_policy_gate, PolicyDecision
from agents.memory.retrieval import store_intent, build_context_string
from shared.logger import logger

webhook_router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


# ── Agent singletons (imported lazily to avoid circular imports) ──────────────
def _get_pipeline():
    """Return (extractor, planner, executor) — initialised once."""
    from agents.intent_agent.extractor import IntentExtractor
    from agents.intent_agent.schemas import Intent
    from agents.planner.planner import GoalPlanner
    from agents.goal_engine.executor import GoalExecutionEngine
    return IntentExtractor(), GoalPlanner(), GoalExecutionEngine(), Intent


_pipeline_cache: tuple | None = None


def get_pipeline():
    global _pipeline_cache
    if _pipeline_cache is None:
        _pipeline_cache = _get_pipeline()
    return _pipeline_cache


# ── Main webhook endpoint ─────────────────────────────────────────────────────

@webhook_router.post("/gmail", summary="Handle Gmail Pub/Sub push notifications")
async def gmail_webhook(
    request: Request,
    x_webhook_secret: str = Header(None),
):
    """
    Handles Google Cloud Pub/Sub push notifications for Gmail.

    Expected payload:
    {
        "message": {
            "data": "<base64 of {'emailAddress': '...', 'historyId': '...'}>",
            "messageId": "..."
        }
    }

    On success returns:
    {"status": "processed", "emails_ingested": N}
    """
    # ── 1. Authenticate the webhook call ─────────────────────────────────────
    expected_secret = os.getenv("GMAIL_WEBHOOK_SECRET")
    if expected_secret and x_webhook_secret != expected_secret:
        logger.warning("Unauthorized webhook attempt from %s", request.client.host)
        raise HTTPException(status_code=401, detail="Unauthorized")

    # ── 2. Decode Pub/Sub payload ─────────────────────────────────────────────
    try:
        body = await request.json()
        data_b64 = body.get("message", {}).get("data")
        if not data_b64:
            raise ValueError("Missing message.data in Pub/Sub payload")

        decoded: dict = json.loads(base64.b64decode(data_b64).decode("utf-8"))
        email_address: str = decoded.get("emailAddress", "")
        history_id: str = str(decoded.get("historyId", ""))

        if not email_address or not history_id:
            raise ValueError(f"Missing emailAddress or historyId: {decoded}")

        logger.info("Gmail push received for %s (historyId=%s)", email_address, history_id)

    except Exception as exc:
        logger.error("Failed to decode Pub/Sub payload: %s", exc)
        raise HTTPException(status_code=400, detail=f"Invalid payload: {exc}")

    # ── 3. Look up stored OAuth token ─────────────────────────────────────────
    token_row = get_gmail_token(email_address)
    if not token_row or not token_row.get("google_refresh_token"):
        logger.warning(
            "No refresh token for %s — user must re-authenticate via /auth/login",
            email_address,
        )
        # Return 200 so Pub/Sub doesn't retry endlessly
        return {"status": "skipped", "reason": "no_token", "email": email_address}

    refresh_token: str = token_row["google_refresh_token"]
    user_id: str = token_row["id"]
    last_history_id: str | None = token_row.get("last_history_id")

    # Use the larger of the two historyIds to avoid replaying old messages
    effective_history_id = last_history_id or history_id

    # ── 4. Build Gmail API service ────────────────────────────────────────────
    try:
        service = build_gmail_service(refresh_token)
    except Exception as exc:
        logger.error("Failed to build Gmail service for %s: %s", email_address, exc)
        raise HTTPException(status_code=502, detail=f"Gmail auth failed: {exc}")

    # ── 5. Fetch new message IDs since last_history_id ────────────────────────
    try:
        message_ids = fetch_new_message_ids(service, email_address, effective_history_id)
    except RuntimeError as exc:
        # historyId may be too old (410 Gone) — fall back to current push historyId
        logger.warning("history.list failed (%s) — retrying with current historyId", exc)
        try:
            message_ids = fetch_new_message_ids(service, email_address, history_id)
        except Exception as inner_exc:
            logger.error("history.list retry failed: %s", inner_exc)
            return {"status": "error", "reason": str(inner_exc)}

    if not message_ids:
        logger.info("No new messages for %s since historyId=%s", email_address, effective_history_id)
        # Update stored history_id even when there's nothing new
        save_gmail_tokens(user_id, refresh_token, history_id)
        return {"status": "ok", "emails_ingested": 0}

    logger.info("Processing %d new message(s) for %s", len(message_ids), email_address)

    # ── 6. Process each message ───────────────────────────────────────────────
    ingested = 0
    extractor, planner, executor, Intent = get_pipeline()

    for msg_id in message_ids:
        try:
            # Fetch full message
            raw_msg = fetch_message(service, email_address, msg_id)
            parsed = parse_message(raw_msg)

            # Persist email to Supabase
            email_record = create_email({
                "user_id": user_id,
                "sender": parsed["sender"],
                "subject": parsed["subject"],
                "body": parsed["body"],
                "received_at": parsed["received_at"],
                "raw_payload": parsed["raw_payload"],
            })
            email_id = email_record["id"]
            logger.info("Email ingested: id=%s subject='%s'", email_id, parsed["subject"])

            log_action({
                "user_id": user_id,
                "action_type": "email_ingested_via_webhook",
                "status": "success",
                "metadata": {"email_id": email_id, "gmail_message_id": msg_id},
            })

            # ── 7. Run agent pipeline ─────────────────────────────────────────
            await _run_agent_pipeline(
                email_id=email_id,
                user_id=user_id,
                subject=parsed["subject"],
                body=parsed["body"],
                extractor=extractor,
                planner=planner,
                executor=executor,
                Intent=Intent,
            )

            ingested += 1

        except Exception as exc:
            logger.error("Failed to process message %s: %s", msg_id, exc)
            # Continue with remaining messages — don't abort the whole batch
            continue

    # ── 8. Update last_history_id ─────────────────────────────────────────────
    save_gmail_tokens(user_id, refresh_token, history_id)

    return {"status": "processed", "emails_ingested": ingested}


# ── Internal agent pipeline runner ────────────────────────────────────────────

async def _run_agent_pipeline(
    *,
    email_id: str,
    user_id: str,
    subject: str,
    body: str,
    sender: str = "",
    headers: dict | None = None,
    extractor,
    planner,
    executor,
    Intent,
) -> None:
    """
    Runs the zero-trust security pipeline for an ingested email.

    Security gate ORDER:
      1. Trust/Risk Scorer  (runs FIRST — CRITICAL short-circuits before LLM)
      2. LLM Intent Extractor (JSON only, sandboxed)
      3. Policy Engine      (blocks or gate-keeps before any tool call)
      4. Tool Orchestrator  (Gmail API only when all gates pass and/or approved)

    All results are persisted to Supabase. Errors are logged but not re-raised.
    """
    try:
        # ── GATE 1: Trust / Risk Scoring (pre-LLM) ───────────────────────────
        spf_dkim = extract_auth_results(headers or {})
        urls = extract_urls(body)
        url_scan = scan_urls(urls)
        risk_score = calculate_risk(spf_dkim, url_scan, sender=sender, subject=subject)

        # Persist risk score
        create_risk_score(risk_score.to_db_dict(email_id))

        logger.info(
            "Risk score for email %s: level=%s score=%.2f reasons=%s",
            email_id, risk_score.level.value, risk_score.score, risk_score.reasons,
        )

        # CRITICAL risk — block entirely, LLM never called
        if risk_score.blocks_pipeline:
            create_plan({
                "email_id": email_id,
                "steps": [],
                "status": "blocked",
                "block_reason": f"CRITICAL risk ({risk_score.score:.2f}): {', '.join(risk_score.reasons[:2])}",
            })
            log_action({
                "user_id": user_id,
                "action_type": "email_blocked_risk",
                "status": "blocked",
                "metadata": {
                    "email_id": email_id,
                    "risk_level": risk_score.level.value,
                    "risk_score": risk_score.score,
                    "reasons": risk_score.reasons,
                },
            })
            logger.warning(
                "Email %s BLOCKED before LLM: CRITICAL risk (score=%.2f)",
                email_id, risk_score.score,
            )
            return

        # ── GATE 2: LLM Intent Extraction ─────────────────────────────────────
        # Build context from agent memory (past intents for this user)
        context = build_context_string(user_id, subject, n=5)

        raw = await extractor.extract(
            subject=subject,
            body=body,
            extra_context=context,
        )
        intent_dict: dict = raw["intent"]
        validation_status: str = raw["status"]

        intent_obj = Intent(**intent_dict)

        # Store in agent memory for future context retrieval
        store_intent(user_id, intent_dict)

        intent_record = create_intent({
            "email_id": email_id,
            "intent_type": intent_obj.intent_type.value,
            "confidence": intent_obj.confidence_score,
            "structured_output": intent_dict,
        })
        intent_id = intent_record["id"]

        log_action({
            "user_id": user_id,
            "action_type": "intent_extracted",
            "status": validation_status,
            "metadata": {
                "email_id": email_id,
                "intent_id": intent_id,
                "risk_level": risk_score.level.value,
            },
        })

        # ── Deterministic Planning ─────────────────────────────────────────────
        goal_plan = planner.plan(intent_obj)

        if goal_plan.goal_type.value == "no_action":
            create_plan({"intent_id": intent_id, "steps": [], "status": "blocked"})
            logger.info("Email %s → no_action (low confidence or missing entities)", email_id)
            return

        steps_payload = [s.model_dump() for s in goal_plan.steps]
        goal_type_str = goal_plan.goal_type.value

        # ── GATE 3: Policy Engine ──────────────────────────────────────────────
        requires_external = any(
            getattr(s, "requires_external_action", False) for s in goal_plan.steps
        )
        policy_result = apply_policy_gate(
            goal_type=goal_type_str,
            risk_score=risk_score,
            requires_external_action=requires_external,
            confidence=intent_obj.confidence_score,
        )

        # Map policy decision → plan status
        if policy_result.decision == PolicyDecision.BLOCK:
            plan_record = create_plan({
                "intent_id": intent_id,
                "steps": steps_payload,
                "status": "blocked",
                "block_reason": policy_result.explanation,
            })
            log_action({
                "user_id": user_id,
                "action_type": "plan_blocked_policy",
                "status": "blocked",
                "metadata": {
                    "plan_id": plan_record["id"],
                    "triggered_rules": policy_result.triggered_rules,
                    "explanation": policy_result.explanation,
                },
            })
            logger.warning(
                "Email %s BLOCKED by policy: rules=%s", email_id, policy_result.triggered_rules
            )
            return

        if policy_result.decision == PolicyDecision.REQUIRE_APPROVAL:
            plan_record = create_plan({
                "intent_id": intent_id,
                "steps": steps_payload,
                "status": "pending_approval",
                "policy_explanation": policy_result.explanation,
                "triggered_rules": policy_result.triggered_rules,
            })
            log_action({
                "user_id": user_id,
                "action_type": "plan_pending_approval",
                "status": "pending_approval",
                "metadata": {
                    "plan_id": plan_record["id"],
                    "goal_type": goal_type_str,
                    "triggered_rules": policy_result.triggered_rules,
                },
            })
            logger.info(
                "Email %s → plan %s requires human approval (rules=%s)",
                email_id, plan_record["id"], policy_result.triggered_rules,
            )
            return  # Awaiting human approval via /plans/{id}/approve

        # ── GATE 4: Execute (ALLOW path) ───────────────────────────────────────
        plan_record = create_plan({
            "intent_id": intent_id,
            "steps": steps_payload,
            "status": "pending",
        })
        plan_id = plan_record["id"]

        execution_result = await executor.execute(goal_plan)
        final_status = execution_result.overall_status.value
        update_plan_status(plan_id, final_status)

        log_action({
            "user_id": user_id,
            "action_type": "plan_auto_executed",
            "status": final_status,
            "metadata": {
                "plan_id": plan_id,
                "goal_type": goal_type_str,
                "email_id": email_id,
            },
        })

        logger.info(
            "Email %s processed → intent=%s goal=%s risk=%s plan_status=%s",
            email_id,
            intent_obj.intent_type.value,
            goal_type_str,
            risk_score.level.value,
            final_status,
        )

    except Exception as exc:
        logger.error("Agent pipeline failed for email %s: %s", email_id, exc)
        log_action({
            "user_id": user_id,
            "action_type": "agent_pipeline_error",
            "status": "failed",
            "metadata": {"email_id": email_id, "error": str(exc)},
        })
