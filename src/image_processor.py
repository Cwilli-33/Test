"""Image processing: fingerprinting, download, and duplicate detection."""
import httpx
import base64
import hashlib
from typing import Optional, Dict, Any, Tuple
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from src.models import ProcessedImage
from config.settings import settings
import logging

logger = logging.getLogger(__name__)

IMAGE_MIME_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp", "image/bmp"}


class ImageProcessor:
    def __init__(self):
        self.bot_token = settings.telegram_bot_token
        self.fingerprint_ttl = timedelta(hours=settings.image_fingerprint_ttl_hours)

    def extract_image_from_message(self, message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Extract image info from a Telegram message.

        Handles three cases:
          1. photo array  — standard compressed photo
          2. document with image mime_type — photo sent as file
          3. sticker — skip
        """
        chat_id = message.get("chat", {}).get("id", 0)
        message_id = message.get("message_id", 0)
        timestamp = message.get("date", 0)

        # Case 1: Photo (most common)
        photo = message.get("photo")
        if photo and isinstance(photo, list) and len(photo) > 0:
            best_photo = max(photo, key=lambda p: p.get("file_size", 0))
            logger.info(f"Found photo in message {message_id}")
            return {
                "file_id": best_photo["file_id"],
                "file_size": best_photo.get("file_size", 0),
                "message_id": message_id,
                "chat_id": chat_id,
                "timestamp": timestamp,
                "media_type": "image/jpeg",  # Telegram photos are always JPEG
            }

        # Case 2: Document that is an image
        doc = message.get("document")
        if doc and isinstance(doc, dict):
            mime = doc.get("mime_type", "")
            if mime in IMAGE_MIME_TYPES:
                logger.info(f"Found image document ({mime}) in message {message_id}")
                return {
                    "file_id": doc["file_id"],
                    "file_size": doc.get("file_size", 0),
                    "message_id": message_id,
                    "chat_id": chat_id,
                    "timestamp": timestamp,
                    "media_type": mime,
                }

        return None

    def create_fingerprint(self, file_id: str, file_size: int) -> str:
        fingerprint_string = f"{file_id}_{file_size}"
        return hashlib.sha256(fingerprint_string.encode()).hexdigest()[:32]

    def is_duplicate(self, fingerprint: str, db: Session) -> bool:
        processed = db.query(ProcessedImage).filter(
            ProcessedImage.fingerprint == fingerprint
        ).first()
        if processed:
            logger.info(f"Duplicate image detected: {fingerprint}")
            return True
        return False

    async def download_image(self, file_id: str) -> bytes:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://api.telegram.org/bot{self.bot_token}/getFile",
                params={"file_id": file_id},
                timeout=30.0,
            )
            response.raise_for_status()
            file_data = response.json()
            if not file_data.get("ok"):
                raise Exception(f"Failed to get file path: {file_data}")
            file_path = file_data["result"]["file_path"]
            file_url = f"https://api.telegram.org/file/bot{self.bot_token}/{file_path}"
            response = await client.get(file_url, timeout=60.0)
            response.raise_for_status()
            logger.info(f"Downloaded image: {len(response.content)} bytes")
            return response.content

    def image_to_base64(self, image_bytes: bytes) -> str:
        return base64.b64encode(image_bytes).decode("utf-8")

    def mark_as_processed(
        self,
        fingerprint: str,
        image_info: Dict[str, Any],
        contact_id: Optional[str],
        action: str,
        confidence: float,
        document_type: Optional[str],
        db: Session,
    ):
        # Update the existing placeholder record (claimed during race-condition
        # prevention) rather than inserting a new one.
        existing = db.query(ProcessedImage).filter(
            ProcessedImage.fingerprint == fingerprint
        ).first()

        if existing:
            existing.contact_id = contact_id
            existing.action = action
            existing.confidence = confidence
            existing.document_type = document_type
            existing.processed_at = datetime.utcnow()
        else:
            # Fallback: insert fresh record if placeholder wasn't created
            processed = ProcessedImage(
                fingerprint=fingerprint,
                file_id=image_info["file_id"],
                message_id=image_info["message_id"],
                chat_id=str(image_info["chat_id"]),
                contact_id=contact_id,
                action=action,
                confidence=confidence,
                document_type=document_type,
                processed_at=datetime.utcnow(),
            )
            db.add(processed)
        logger.info(f"Marked image {fingerprint} as processed ({action})")

    def cleanup_old_fingerprints(self, db: Session):
        cutoff_time = datetime.utcnow() - self.fingerprint_ttl
        deleted_count = (
            db.query(ProcessedImage)
            .filter(ProcessedImage.processed_at < cutoff_time)
            .delete()
        )
        db.commit()
        if deleted_count > 0:
            logger.info(f"Cleaned up {deleted_count} old image fingerprints")
