"""Claude Vision API integration for extracting structured lead data from images."""
import json
import logging
from typing import Any, Dict, Optional

from anthropic import Anthropic
from config.settings import settings

logger = logging.getLogger(__name__)

EXTRACTION_PROMPT = """You are an expert data extraction system for MCA (Merchant Cash Advance) lead processing.

Analyze this image and extract ALL available business and owner information. The image may be:
- An MCA application form
- A business document or flyer
- A bank statement header
- A screenshot of business information
- A business card
- Any other document containing business/owner details

Extract the following fields. Return ONLY valid JSON with no extra text. Use null for any field you cannot find.

{
  "document_type": "MCA_APPLICATION | BANK_STATEMENT | BUSINESS_CARD | BUSINESS_DOCUMENT | SCREENSHOT | OTHER",
  "confidence": 0.0 to 1.0,
  "business_info": {
    "legal_name": "string or null",
    "dba": "string or null",
    "ein": "string or null (format: XX-XXXXXXX)",
    "address": "string or null",
    "city": "string or null",
    "state": "string or null (2-letter code)",
    "zip_code": "string or null",
    "phone": "string or null",
    "email": "string or null",
    "website": "string or null",
    "industry": "string or null",
    "entity_type": "LLC | CORP | SOLE_PROP | PARTNERSHIP | null",
    "start_date": "string or null (YYYY-MM-DD or MM/DD/YYYY)",
    "time_in_business_months": "integer or null"
  },
  "owner_info": {
    "first_name": "string or null",
    "last_name": "string or null",
    "full_name": "string or null",
    "phone": "string or null",
    "email": "string or null",
    "ssn_last_four": "string or null (last 4 digits only)",
    "dob": "string or null",
    "ownership_percentage": "number or null",
    "home_address": "string or null",
    "title": "string or null (Owner, CEO, etc.)"
  },
  "financial_info": {
    "monthly_revenue": "number or null",
    "annual_revenue": "number or null",
    "requested_amount": "number or null",
    "use_of_funds": "string or null",
    "credit_score": "number or null",
    "existing_positions": "number or null",
    "current_balance": "number or null",
    "avg_daily_balance": "number or null"
  },
  "mca_history": {
    "has_existing_mca": "boolean or null",
    "current_funder": "string or null",
    "daily_payment": "number or null",
    "remaining_balance": "number or null",
    "position": "number or null (1st, 2nd, 3rd)"
  },
  "additional_notes": "string - any other relevant info from the document"
}

IMPORTANT RULES:
- Extract EXACTLY what you see. Do not guess or fabricate data.
- For phone numbers, include the raw number as seen.
- For EIN, extract in XX-XXXXXXX format if visible.
- If the image is blurry or unreadable, set confidence below 0.3.
- If no business data is visible at all, set confidence to 0.0.
- Return ONLY the JSON object, nothing else."""


class ClaudeExtractor:
    def __init__(self):
        self.client = Anthropic(api_key=settings.claude_api_key)
        self.model = settings.claude_model
        self.max_tokens = settings.claude_max_tokens
        self.timeout = settings.claude_timeout

    async def extract(self, image_base64: str, media_type: str = "image/jpeg") -> Dict[str, Any]:
        """Extract structured data from an image using Claude Vision API.

        Args:
            image_base64: Base64-encoded image data.
            media_type: MIME type of the image (image/jpeg, image/png, etc.).

        Returns:
            Dict with extracted fields and confidence score.
        """
        try:
            logger.info("Sending image to Claude Vision for extraction")

            response = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": media_type,
                                    "data": image_base64,
                                },
                            },
                            {
                                "type": "text",
                                "text": EXTRACTION_PROMPT,
                            },
                        ],
                    }
                ],
            )

            raw_text = response.content[0].text
            extracted = self._parse_response(raw_text)

            confidence = extracted.get("confidence", 0.0)
            document_type = extracted.get("document_type", "OTHER")

            logger.info(
                f"Extraction complete — type={document_type}, confidence={confidence:.2f}"
            )

            if confidence < settings.min_confidence_threshold:
                logger.warning(
                    f"Low confidence extraction ({confidence:.2f} < {settings.min_confidence_threshold})"
                )

            return extracted

        except Exception as e:
            logger.error(f"Claude extraction failed: {e}", exc_info=True)
            return self._empty_extraction(error=str(e))

    def _parse_response(self, raw_text: str) -> Dict[str, Any]:
        """Parse Claude's response text into structured JSON.

        Handles common formatting issues like markdown code blocks,
        trailing commas, etc.
        """
        text = raw_text.strip()

        # Strip markdown code fences if present
        if text.startswith("```"):
            lines = text.split("\n")
            # Remove first line (```json or ```) and last line (```)
            lines = [l for l in lines if not l.strip().startswith("```")]
            text = "\n".join(lines).strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try fixing trailing commas
        import re
        cleaned = re.sub(r",\s*([}\]])", r"\1", text)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

        # Try extracting JSON object from surrounding text
        brace_start = text.find("{")
        brace_end = text.rfind("}")
        if brace_start != -1 and brace_end != -1:
            candidate = text[brace_start : brace_end + 1]
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                pass

        logger.error(f"Failed to parse Claude response as JSON: {raw_text[:200]}...")
        return self._empty_extraction(error="JSON parse failure")

    def _empty_extraction(self, error: Optional[str] = None) -> Dict[str, Any]:
        """Return a valid but empty extraction result."""
        result = {
            "document_type": "OTHER",
            "confidence": 0.0,
            "business_info": {
                "legal_name": None, "dba": None, "ein": None,
                "address": None, "city": None, "state": None,
                "zip_code": None, "phone": None, "email": None,
                "website": None, "industry": None, "entity_type": None,
                "start_date": None, "time_in_business_months": None,
            },
            "owner_info": {
                "first_name": None, "last_name": None, "full_name": None,
                "phone": None, "email": None, "ssn_last_four": None,
                "dob": None, "ownership_percentage": None,
                "home_address": None, "title": None,
            },
            "financial_info": {
                "monthly_revenue": None, "annual_revenue": None,
                "requested_amount": None, "use_of_funds": None,
                "credit_score": None, "existing_positions": None,
                "current_balance": None, "avg_daily_balance": None,
            },
            "mca_history": {
                "has_existing_mca": None, "current_funder": None,
                "daily_payment": None, "remaining_balance": None,
                "position": None,
            },
            "additional_notes": None,
        }
        if error:
            result["extraction_error"] = error
        return result
