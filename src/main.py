"""Main FastAPI application — Telegram → Claude Vision → GHL pipeline."""
import json
import logging
import sys
from contextlib import asynccontextmanager

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
    level=settings.log_level,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Telegram → GHL Pipeline...")
    init_db()
    logger.info("Database initialized")
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
# Telegram webhook
# ---------------------------------------------------------------------------

@app.post("/webhook/telegram")
async def handle_telegram_webhook(request: Request, db: Session = Depends(get_db)):
    """Process incoming Telegram messages containing images.

    Pipeline:
        1. Extract image metadata from Telegram message
        2. Fingerprint and check for duplicates
        3. Download image and encode to base64
        4. Send to Claude Vision for structured extraction
        5. Search GHL for existing matching contact
        6. Create or update contact in GHL
        7. Record extraction in local DB for audit trail
    """
    try:
        data = await request.json()
        logger.info(f"Received Telegram webhook")

        # ── Extract the message ──────────────────────────────────────────
        message = data.get("message") or data.get("channel_post")
        if not message:
            logger.debug("Webhook contained no message — ignoring")
            return {"status": "ignored", "reason": "no_message"}

        # ── Check for an image ───────────────────────────────────────────
        image_info = image_processor.extract_image_from_message(message)
        if not image_info:
            logger.debug("Message has no photo — ignoring")
            return {"status": "ignored", "reason": "no_photo"}

        file_id = image_info["file_id"]
        file_size = image_info["file_size"]

        # ── Duplicate check ──────────────────────────────────────────────
        fingerprint = image_processor.create_fingerprint(file_id, file_size)
        if image_processor.is_duplicate(fingerprint, db):
            return {
                "status": "skipped",
                "reason": "duplicate_image",
                "fingerprint": fingerprint,
            }

        logger.info(f"Processing new image: fingerprint={fingerprint}")

        # ── Download and encode ──────────────────────────────────────────
        image_bytes = await image_processor.download_image(file_id)
        image_base64 = image_processor.image_to_base64(image_bytes)

        # Determine media type from Telegram (they always serve JPEG for photos)
        media_type = "image/jpeg"

        # ── Extract data with Claude Vision ──────────────────────────────
        extracted = await claude_extractor.extract(image_base64, media_type)

        confidence = extracted.get("confidence", 0.0)
        document_type = extracted.get("document_type", "OTHER")

        if confidence < settings.min_confidence_threshold:
            logger.warning(
                f"Extraction below confidence threshold "
                f"({confidence:.2f} < {settings.min_confidence_threshold}) — skipping"
            )
            image_processor.mark_as_processed(
                fingerprint, image_info,
                contact_id=None, action="SKIPPED_LOW_CONFIDENCE",
                confidence=confidence, document_type=document_type, db=db,
            )
            return {
                "status": "skipped",
                "reason": "low_confidence",
                "confidence": confidence,
            }

        # ── Match against existing GHL contacts ──────────────────────────
        matched_contact, match_method, match_confidence = await lead_matcher.find_match(extracted)

        contact_id: str
        action: str

        if matched_contact:
            # ── Update existing contact ──────────────────────────────────
            contact_id = matched_contact.get("id", "")
            update_payload = data_merger.merge(
                matched_contact, extracted, match_method, match_confidence
            )
            result = await ghl_client.update_contact(contact_id, update_payload)
            action = "UPDATE"

            if result:
                logger.info(
                    f"Updated GHL contact {contact_id} "
                    f"(match={match_method}, confidence={match_confidence})"
                )
            else:
                logger.error(f"Failed to update GHL contact {contact_id}")

        else:
            # ── Create new contact ───────────────────────────────────────
            new_payload = data_merger.build_new_contact(extracted)
            result = await ghl_client.create_contact(new_payload)
            action = "CREATE"

            if result:
                contact_id = result.get("id", "unknown")
                logger.info(f"Created new GHL contact {contact_id}")
            else:
                contact_id = "failed"
                logger.error("Failed to create GHL contact")

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

        # Mark image as processed
        image_processor.mark_as_processed(
            fingerprint, image_info,
            contact_id=contact_id, action=action,
            confidence=confidence, document_type=document_type, db=db,
        )

        db.commit()

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
        logger.error(f"Webhook processing error: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"status": "error", "error": str(e)},
        )


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
