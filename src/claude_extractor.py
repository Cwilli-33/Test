"""Claude Vision API integration for extracting structured lead data from images."""
import json
import logging
import re
from typing import Any, Dict, Optional

from anthropic import Anthropic
from config.settings import settings

logger = logging.getLogger(__name__)

EXTRACTION_PROMPT = """You are an expert data extraction system for MCA (Merchant Cash Advance) lead processing.

Analyze this image and extract ALL available business and owner information.

CRITICAL — IDENTIFYING THE CORRECT BUSINESS:
This is an MCA lead document. The BUSINESS (the merchant/applicant seeking funding) is the company
APPLYING for the cash advance — NOT the lender, funder, ISO, or broker. Look for clues:
  - The business name is usually in a field labeled "Business Name", "Legal Name", "Company", "DBA",
    "Applicant", or "Merchant".
  - Lender/funder/ISO names often appear in headers, footers, logos, or fields labeled "Funder",
    "Lender", "ISO", "Broker", or "Funded by". Do NOT use these as the business name.
  - If the document is an application FORM, the business is whoever is FILLING OUT the form,
    not the company whose form it is.

The image may be:
- An MCA application form
- A bank statement or financial summary
- A credit report or score sheet
- A business document, tax form, or articles of incorporation
- A screenshot of CRM data or lead information
- A business card

Extract ALL of the following fields. Return ONLY valid JSON with no extra text.
Use null for any field you cannot find or that is not visible in the image.

{
  "document_type": "MCA_APPLICATION | BANK_STATEMENT | CREDIT_REPORT | TAX_DOCUMENT | BUSINESS_DOCUMENT | CRM_SCREENSHOT | OTHER",
  "confidence": 0.0 to 1.0,

  "business_info": {
    "legal_name": "The legal business name of the APPLICANT/MERCHANT (NOT the lender/funder)",
    "dba": "DBA / trade name if different from legal name",
    "ein": "Federal EIN, format XX-XXXXXXX. Include even if partially masked (e.g. ***-**-6789)",
    "address": "Business street address",
    "city": "Business city",
    "state": "Business state (2-letter code)",
    "zip_code": "Business ZIP code",
    "phone": "Business phone number (raw, as shown)",
    "email": "Business email",
    "website": "Business website URL",
    "industry": "Type of business / industry (e.g. Restaurant, Trucking, Construction)",
    "entity_type": "LLC | CORP | SOLE_PROP | PARTNERSHIP | S_CORP | C_CORP | null",
    "start_date": "Business start date or date of incorporation",
    "state_of_incorporation": "State where the business was incorporated (2-letter code)"
  },

  "owner_info": {
    "first_name": "Owner/principal first name",
    "last_name": "Owner/principal last name",
    "full_name": "Owner full name if first/last not clearly separated",
    "phone": "Owner personal phone (may differ from business phone)",
    "email": "Owner personal email",
    "ssn_last_four": "Last 4 digits of SSN only (never extract full SSN)",
    "dob": "Date of birth",
    "ownership_percentage": "Ownership percentage as a number (e.g. 100, 51, 50)",
    "title": "Title or role (Owner, CEO, President, Member, etc.)",
    "home_address": "Owner home street address",
    "home_city": "Owner home city",
    "home_state": "Owner home state (2-letter code)",
    "home_zip": "Owner home ZIP code"
  },

  "owner2_info": {
    "full_name": "Second owner/partner/guarantor full name, or null if only one owner",
    "phone": "Second owner phone",
    "ownership_percentage": "Second owner percentage",
    "fico": "Second owner FICO/credit score if shown"
  },

  "financial_info": {
    "monthly_revenue": "Average monthly revenue/deposits as a number",
    "annual_revenue": "Annual revenue as a number",
    "funding_requested": "Amount of funding requested as a number",
    "use_of_funds": "Stated purpose for the funds",
    "avg_daily_balance": "Average daily bank balance as a number",
    "true_revenue_avg_3mo": "True 3-month average revenue/deposits if shown"
  },

  "credit_info": {
    "fico_owner1": "Primary owner FICO / credit score as a number",
    "fico_owner2": "Second owner FICO / credit score as a number (null if N/A)",
    "satisfactory_accounts": "Number of satisfactory/current accounts",
    "total_tradelines": "Total number of tradelines",
    "now_delinquent": "Number of currently delinquent accounts",
    "num_chargeoffs": "Number of charge-offs",
    "leverage_pct": "Credit utilization / leverage percentage as a number",
    "statement_number": "The masked statement or account identifiers shown in a 'Statements' column or list. These look like XXXXXX5800, XXXXXXXXXXXX9112, XXXXXXXXXXXX1758 — masked numbers with X's followed by visible digits. Extract ALL unique statement numbers as a comma-separated string (e.g. 'XXXXXX5800, XXXXXXXXXXXX9112, XXXXXXXXXXXX1758'). Include the X's exactly as shown."
  },

  "mca_info": {
    "has_existing_positions": "true/false — does the merchant have existing MCA positions?",
    "num_positions": "Number of current MCA positions (e.g. 1, 2, 3)",
    "num_existing_positions": "Total number of existing funding positions",
    "current_funder": "Name of current MCA funder(s)",
    "daily_payment": "Current daily MCA payment amount",
    "remaining_balance": "Remaining balance on current MCA"
  },

  "iso_info": {
    "iso_name": "Name of the ISO/broker who submitted this lead (from header, footer, or watermark)",
    "source_platform": "Platform or source where this lead originated (if visible)"
  },

  "additional_notes": "Any other relevant information from the document not captured above"
}

IMPORTANT RULES:
- Extract EXACTLY what you see. Do not guess or fabricate data.
- The BUSINESS NAME is the company seeking funding, NOT the lender/funder/ISO.
- For phone numbers, include the raw number exactly as shown.
- For EIN, include even partial/masked values (e.g. "***-**-6789" or just "6789").
- For dollar amounts, extract as plain numbers without $ or commas (e.g. 50000 not $50,000).
- For percentages, extract as plain numbers (e.g. 75 not 75%).
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
                "start_date": None, "state_of_incorporation": None,
            },
            "owner_info": {
                "first_name": None, "last_name": None, "full_name": None,
                "phone": None, "email": None, "ssn_last_four": None,
                "dob": None, "ownership_percentage": None, "title": None,
                "home_address": None, "home_city": None,
                "home_state": None, "home_zip": None,
            },
            "owner2_info": {
                "full_name": None, "phone": None,
                "ownership_percentage": None, "fico": None,
            },
            "financial_info": {
                "monthly_revenue": None, "annual_revenue": None,
                "funding_requested": None, "use_of_funds": None,
                "avg_daily_balance": None, "true_revenue_avg_3mo": None,
            },
            "credit_info": {
                "fico_owner1": None, "fico_owner2": None,
                "satisfactory_accounts": None, "total_tradelines": None,
                "now_delinquent": None, "num_chargeoffs": None,
                "leverage_pct": None, "statement_number": None,
            },
            "mca_info": {
                "has_existing_positions": None, "num_positions": None,
                "num_existing_positions": None, "current_funder": None,
                "daily_payment": None, "remaining_balance": None,
            },
            "iso_info": {
                "iso_name": None, "source_platform": None,
            },
            "additional_notes": None,
        }
        if error:
            result["extraction_error"] = error
        return result
