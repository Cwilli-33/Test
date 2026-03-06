"""Lead matching — multi-criteria search to prevent duplicate contacts in GHL."""
import logging
import re
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Tuple

import phonenumbers

from src.ghl_client import GHLClient

logger = logging.getLogger(__name__)


class LeadMatcher:
    """Searches GHL for existing contacts that match extracted lead data.

    Match priority (highest → lowest):
        1. EIN — unique federal identifier, near-certain match
        2. Phone — strong identifier, normalized to E.164
        3. Email — strong identifier
        4. Business name + state — fuzzy match with geographic verification
    """

    # Minimum similarity ratio for business name fuzzy matching
    NAME_MATCH_THRESHOLD = 0.80

    def __init__(self, ghl_client: GHLClient):
        self.ghl = ghl_client

    async def find_match(
        self, extracted: Dict[str, Any]
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str], int]:
        """Find the best matching GHL contact for extracted lead data.

        Args:
            extracted: Dict from ClaudeExtractor with business_info, owner_info, etc.

        Returns:
            Tuple of (matched_contact, match_method, match_confidence).
            If no match found, returns (None, None, 0).
        """
        biz = extracted.get("business_info", {}) or {}
        owner = extracted.get("owner_info", {}) or {}

        # --- 1. Match by EIN (highest confidence) ---
        ein = self._normalize_ein(biz.get("ein"))
        if ein:
            contact = await self._search_ein(ein)
            if contact:
                logger.info(f"Matched by EIN: {ein}")
                return contact, "EIN", 95

        # --- 2. Match by phone (business phone, then owner phone) ---
        for raw_phone in [biz.get("phone"), owner.get("phone")]:
            phone = self._normalize_phone(raw_phone)
            if phone:
                contact = await self._search_phone(phone)
                if contact:
                    logger.info(f"Matched by phone: {phone}")
                    return contact, "PHONE", 90

        # --- 3. Match by email ---
        for raw_email in [biz.get("email"), owner.get("email")]:
            email = self._normalize_email(raw_email)
            if email:
                contact = await self._search_email(email)
                if contact:
                    logger.info(f"Matched by email: {email}")
                    return contact, "EMAIL", 85

        # --- 4. Match by business name + state ---
        biz_name = biz.get("legal_name") or biz.get("dba")
        state = biz.get("state")
        if biz_name:
            contact = await self._search_business_name(biz_name, state)
            if contact:
                logger.info(f"Matched by business name: {biz_name}")
                return contact, "NAME", 70

        logger.info("No existing contact matched")
        return None, None, 0

    # -------------------------------------------------------------------------
    # Search helpers
    # -------------------------------------------------------------------------

    async def _search_ein(self, ein: str) -> Optional[Dict[str, Any]]:
        """Search GHL contacts by EIN (via general query search)."""
        contacts = await self.ghl.search_contacts(ein)
        for c in contacts:
            # Check if the EIN appears in custom fields or company name
            if self._contact_has_value(c, ein):
                return c
        return None

    async def _search_phone(self, phone: str) -> Optional[Dict[str, Any]]:
        """Search GHL contacts by normalized phone number."""
        # Try field-specific search first
        contacts = await self.ghl.search_by_field("phone", phone)
        if contacts:
            return contacts[0]

        # Fallback to query search with just digits
        digits = re.sub(r"\D", "", phone)
        contacts = await self.ghl.search_contacts(digits)
        for c in contacts:
            contact_phone = self._normalize_phone(c.get("phone"))
            if contact_phone and contact_phone == phone:
                return c
        return None

    async def _search_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Search GHL contacts by email."""
        contacts = await self.ghl.search_by_field("email", email)
        if contacts:
            return contacts[0]

        contacts = await self.ghl.search_contacts(email)
        for c in contacts:
            contact_email = self._normalize_email(c.get("email"))
            if contact_email and contact_email == email:
                return c
        return None

    async def _search_business_name(
        self, name: str, state: Optional[str]
    ) -> Optional[Dict[str, Any]]:
        """Search GHL contacts by business name with fuzzy matching and optional state verification."""
        clean_name = self._clean_business_name(name)
        contacts = await self.ghl.search_contacts(clean_name)

        best_match = None
        best_score = 0.0

        for c in contacts:
            company = c.get("companyName", "") or ""
            clean_company = self._clean_business_name(company)
            if not clean_company:
                continue

            score = SequenceMatcher(None, clean_name.lower(), clean_company.lower()).ratio()

            # Boost score if state matches
            if state and c.get("state", "").upper() == state.upper():
                score = min(score + 0.10, 1.0)

            if score > best_score and score >= self.NAME_MATCH_THRESHOLD:
                best_score = score
                best_match = c

        return best_match

    # -------------------------------------------------------------------------
    # Normalization helpers
    # -------------------------------------------------------------------------

    @staticmethod
    def _normalize_phone(raw: Optional[str]) -> Optional[str]:
        """Normalize phone to E.164 format (+1XXXXXXXXXX)."""
        if not raw:
            return None
        try:
            parsed = phonenumbers.parse(raw, "US")
            if phonenumbers.is_valid_number(parsed):
                return phonenumbers.format_number(
                    parsed, phonenumbers.PhoneNumberFormat.E164
                )
        except phonenumbers.NumberParseException:
            pass

        # Fallback: strip to digits, prepend +1 if 10 digits
        digits = re.sub(r"\D", "", raw)
        if len(digits) == 10:
            return f"+1{digits}"
        if len(digits) == 11 and digits.startswith("1"):
            return f"+{digits}"
        return None

    @staticmethod
    def _normalize_ein(raw: Optional[str]) -> Optional[str]:
        """Normalize EIN to XX-XXXXXXX format."""
        if not raw:
            return None
        digits = re.sub(r"\D", "", raw)
        if len(digits) == 9:
            return f"{digits[:2]}-{digits[2:]}"
        return None

    @staticmethod
    def _normalize_email(raw: Optional[str]) -> Optional[str]:
        """Normalize email to lowercase, stripped."""
        if not raw:
            return None
        email = raw.strip().lower()
        if "@" in email and "." in email.split("@")[-1]:
            return email
        return None

    @staticmethod
    def _clean_business_name(name: str) -> str:
        """Remove common suffixes and noise from business names for comparison."""
        if not name:
            return ""
        cleaned = name.strip()
        # Remove common entity suffixes
        suffixes = [
            r"\bllc\b", r"\binc\.?\b", r"\bcorp\.?\b", r"\bcorporation\b",
            r"\bltd\.?\b", r"\bco\.?\b", r"\bcompany\b", r"\bdba\b",
            r"\bd/b/a\b", r"\bthe\b",
        ]
        for suffix in suffixes:
            cleaned = re.sub(suffix, "", cleaned, flags=re.IGNORECASE)
        # Remove extra whitespace and punctuation
        cleaned = re.sub(r"[^\w\s]", "", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned

    @staticmethod
    def _contact_has_value(contact: Dict[str, Any], value: str) -> bool:
        """Check whether a GHL contact contains a given value in any field."""
        value_lower = value.lower().replace("-", "")
        # Check top-level string fields
        for field in ["companyName", "email", "phone", "name", "tags"]:
            field_val = contact.get(field)
            if field_val and value_lower in str(field_val).lower().replace("-", ""):
                return True
        # Check custom fields
        custom_fields = contact.get("customField", [])
        if isinstance(custom_fields, list):
            for cf in custom_fields:
                cf_val = cf.get("value", "")
                if cf_val and value_lower in str(cf_val).lower().replace("-", ""):
                    return True
        return False
