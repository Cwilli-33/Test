"""Main FastAPI application — Telegram → Claude Vision → GHL pipeline."""
import json
import logging
import sys
import traceback
from collections import deque
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, Request, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from config.settings import settings
from src.database import get_db, init_db
from src.image_processor import ImageProcessor
from src.claude_extractor import ClaudeExtractor
from src.ghl_client import GHLClient
from src.lead_matcher import LeadMatcher
from src.data_merger import DataMerger
from src.models import LeadExtraction

logging.basicConfig(
    level="DEBUG",
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# Store last 20 webhook results for debugging via /admin/debug
_debug_log = deque(maxlen=20)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Telegram → GHL Pipeline...")
    init_db()
    logger.info("Database initialized")
    logger.info(f"Bot token set: {bool(settings.telegram_bot_token)}")
    logger.info(f"Claude key set: {bool(settings.claude_api_key)}")
    logger.info(f"GHL key set: {bool(settings.ghl_api_key)}")
    logger.info(f"GHL location: {settings.ghl_location_id}")
    yield
    logger.info("Shutting down...")


app = FastAPI(
    title="Telegram → GHL Lead Pipeline",
    description="Automated MCA lead processing from Telegram images",
    version="1.0.0",
    lifespan=lifespan,
)

# Shared service instances
image_processor = ImageProcessor()
claude_extractor = ClaudeExtractor()
ghl_client = GHLClient()
lead_matcher = LeadMatcher(ghl_client)
data_merger = DataMerger()


# ---------------------------------------------------------------------------
# Health endpoints
# ---------------------------------------------------------------------------

@app.get("/")
async def root():
    return {
        "status": "healthy",
        "service": "telegram-ghl-pipeline",
        "version": "1.0.0",
    }


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "database": "connected",
        "message": "Ready to process images",
    }


# ---------------------------------------------------------------------------
# Debug endpoint — view recent webhook activity
# ---------------------------------------------------------------------------

@app.get("/admin/debug")
async def debug_log():
    """View the last 20 webhook processing results."""
    return {"count": len(_debug_log), "events": list(_debug_log)}


# ---------------------------------------------------------------------------
# Telegram webhook
# ---------------------------------------------------------------------------

@app.post("/webhook/telegram")
async def handle_telegram_webhook(request: Request, db: Session = Depends(get_db)):
    """Process incoming Telegram messages containing images."""
    event = {"timestamp": datetime.utcnow().isoformat(), "steps": []}

    def log_step(step: str, detail: str = ""):
        entry = {"step": step, "detail": detail}
        event["steps"].append(entry)
        logger.info(f"[PIPELINE] {step}: {detail}")

    try:
        data = await request.json()
        log_step("RECEIVED", f"keys={list(data.keys())}")

        # ── Extract the message ──────────────────────────────────────────
        message = data.get("message") or data.get("channel_post")
        if not message:
            log_step("IGNORED", f"no message key. payload keys: {list(data.keys())}")
            event["result"] = "ignored_no_message"
            _debug_log.append(event)
            return {"status": "ignored", "reason": "no_message"}

        chat_info = message.get("chat", {})
        log_step("MESSAGE", (
            f"chat_id={chat_info.get('id')}, "
            f"type={chat_info.get('type')}, "
            f"has_photo={bool(message.get('photo'))}, "
            f"has_document={bool(message.get('document'))}, "
            f"has_text={bool(message.get('text'))}"
        ))

        # ── Check for an image ───────────────────────────────────────────
        image_info = image_processor.extract_image_from_message(message)
        if not image_info:
            log_step("IGNORED", "no photo or image document in message")
            event["result"] = "ignored_no_photo"
            _debug_log.append(event)
            return {"status": "ignored", "reason": "no_photo"}

        file_id = image_info["file_id"]
        file_size = image_info["file_size"]
        log_step("IMAGE_FOUND", f"file_id={file_id[:20]}..., size={file_size}")

        # ── Duplicate check ──────────────────────────────────────────────
        fingerprint = image_processor.create_fingerprint(file_id, file_size)
        if image_processor.is_duplicate(fingerprint, db):
            log_step("SKIPPED", f"duplicate fingerprint={fingerprint}")
            event["result"] = "skipped_duplicate"
            _debug_log.append(event)
            return {"status": "skipped", "reason": "duplicate_image", "fingerprint": fingerprint}

        log_step("FINGERPRINT", fingerprint)

        # ── Download and encode ──────────────────────────────────────────
        image_bytes = await image_processor.download_image(file_id)
        image_base64 = image_processor.image_to_base64(image_bytes)
        media_type = image_info.get("media_type", "image/jpeg")
        log_step("DOWNLOADED", f"{len(image_bytes)} bytes, type={media_type}")

        # ── Extract data with Claude Vision ──────────────────────────────
        extracted = await claude_extractor.extract(image_base64, media_type)

        confidence = extracted.get("confidence", 0.0)
        document_type = extracted.get("document_type", "OTHER")
        extraction_error = extracted.get("extraction_error")

        stmt_nums = extracted.get("statement_numbers")
        log_step("EXTRACTED", (
            f"confidence={confidence}, type={document_type}, "
            f"error={extraction_error}, "
            f"biz_name={extracted.get('business_info', {}).get('legal_name')}, "
            f"statement_numbers={stmt_nums}"
        ))

        if confidence < settings.min_confidence_threshold:
            log_step("SKIPPED", f"low confidence {confidence} < {settings.min_confidence_threshold}")
            image_processor.mark_as_processed(
                fingerprint, image_info,
                contact_id=None, action="SKIPPED_LOW_CONFIDENCE",
                confidence=confidence, document_type=document_type, db=db,
            )
            event["result"] = "skipped_low_confidence"
            _debug_log.append(event)
            return {"status": "skipped", "reason": "low_confidence", "confidence": confidence}

        # ── Match against existing GHL contacts ──────────────────────────
        chat_id_str = str(image_info["chat_id"])
        matched_contact, match_method, match_confidence = await lead_matcher.find_match(
            extracted, chat_id=chat_id_str, db=db
        )
        log_step("MATCHED", f"method={match_method}, confidence={match_confidence}, found={bool(matched_contact)}")

        contact_id: str
        action: str

        if matched_contact:
            # ── Update existing contact ──────────────────────────────────
            contact_id = matched_contact.get("id", "")
            update_payload = data_merger.merge(
                matched_contact, extracted, match_method, match_confidence
            )
            log_step("MERGING", f"updating contact {contact_id}")
            result = await ghl_client.update_contact(contact_id, update_payload)
            action = "UPDATE"

            if result:
                log_step("GHL_UPDATED", f"contact_id={contact_id}")
            else:
                log_step("GHL_UPDATE_FAILED", f"contact_id={contact_id}")

        else:
            # ── Create new contact ───────────────────────────────────────
            new_payload = data_merger.build_new_contact(extracted)
            log_step("CREATING", f"payload keys: {list(new_payload.keys())}")
            result = await ghl_client.create_contact(new_payload)
            action = "CREATE"

            if result:
                contact_id = result.get("id", "unknown")
                log_step("GHL_CREATED", f"contact_id={contact_id}")
            else:
                contact_id = "failed"
                log_step("GHL_CREATE_FAILED", "no result returned")

        # ── Record in local database ─────────────────────────────────────
        biz = extracted.get("business_info", {}) or {}
        owner = extracted.get("owner_info", {}) or {}

        extraction_record = LeadExtraction(
            fingerprint=fingerprint,
            contact_id=contact_id,
            action=action,
            ein=biz.get("ein"),
            business_name=biz.get("legal_name") or biz.get("dba"),
            owner_phone=owner.get("phone") or biz.get("phone"),
            owner_email=owner.get("email") or biz.get("email"),
            match_method=match_method,
            match_confidence=match_confidence,
            extraction_confidence=confidence,
            document_type=document_type,
            raw_extracted_data=json.dumps(extracted),
        )
        db.add(extraction_record)

        image_processor.mark_as_processed(
            fingerprint, image_info,
            contact_id=contact_id, action=action,
            confidence=confidence, document_type=document_type, db=db,
        )

        db.commit()
        log_step("DONE", f"action={action}, contact_id={contact_id}")

        event["result"] = f"{action}_{contact_id}"
        _debug_log.append(event)

        return {
            "status": "processed",
            "action": action,
            "contact_id": contact_id,
            "confidence": confidence,
            "document_type": document_type,
            "match_method": match_method,
            "match_confidence": match_confidence,
        }

    except Exception as e:
        error_tb = traceback.format_exc()
        logger.error(f"Webhook processing error: {e}\n{error_tb}")
        log_step("ERROR", f"{type(e).__name__}: {str(e)}")
        event["result"] = f"error: {str(e)}"
        event["traceback"] = error_tb
        _debug_log.append(event)
        # Always return 200 to Telegram so it doesn't retry endlessly
        return {"status": "error", "error": str(e)}


# ---------------------------------------------------------------------------
# Manual cleanup endpoint
# ---------------------------------------------------------------------------

@app.post("/admin/cleanup-fingerprints")
async def cleanup_fingerprints(db: Session = Depends(get_db)):
    """Remove old image fingerprints based on configured TTL."""
    image_processor.cleanup_old_fingerprints(db)
    return {"status": "ok", "message": "Old fingerprints cleaned up"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.main:app", host="0.0.0.0", port=8000, reload=True)
