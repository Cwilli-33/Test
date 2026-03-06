"""Smart data merging — combines extracted data with existing GHL contact data."""
import json
import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class DataMerger:
    """Merges newly extracted lead data with an existing GHL contact.

    Rules:
        - Never overwrite existing data with empty/null values.
        - For numeric fields (revenue, credit score), prefer the higher or newer value.
        - For tags, append new tags without duplicating existing ones.
        - Custom fields are merged individually.
    """

    def merge(
        self,
        existing_contact: Dict[str, Any],
        extracted: Dict[str, Any],
        match_method: str,
        match_confidence: int,
    ) -> Dict[str, Any]:
        """Produce a GHL-compatible update payload by merging extracted data into
        an existing contact.

        Args:
            existing_contact: Current contact dict from GHL.
            extracted: Extraction result from ClaudeExtractor.
            match_method: How the match was made (EIN, PHONE, EMAIL, NAME).
            match_confidence: 0-100 confidence in the match.

        Returns:
            Dict payload suitable for GHLClient.update_contact().
        """
        biz = extracted.get("business_info", {}) or {}
        owner = extracted.get("owner_info", {}) or {}
        fin = extracted.get("financial_info", {}) or {}
        mca = extracted.get("mca_history", {}) or {}

        update: Dict[str, Any] = {}

        # --- Standard fields ---
        update.update(self._merge_standard_fields(existing_contact, biz, owner))

        # --- Tags ---
        update["tags"] = self._merge_tags(
            existing_contact.get("tags", []),
            extracted,
            match_method,
        )

        # --- Custom fields ---
        custom = self._build_custom_fields(existing_contact, biz, owner, fin, mca, extracted)
        if custom:
            update["customField"] = custom

        logger.info(
            f"Merged data for contact (match={match_method}, confidence={match_confidence}): "
            f"{len(update)} top-level fields, {len(custom)} custom fields"
        )

        return update

    def build_new_contact(self, extracted: Dict[str, Any]) -> Dict[str, Any]:
        """Build a GHL contact payload from scratch using only extracted data.

        Used when no existing contact was matched.
        """
        biz = extracted.get("business_info", {}) or {}
        owner = extracted.get("owner_info", {}) or {}
        fin = extracted.get("financial_info", {}) or {}
        mca = extracted.get("mca_history", {}) or {}

        contact: Dict[str, Any] = {}

        # Name
        first = owner.get("first_name") or ""
        last = owner.get("last_name") or ""
        if not first and not last and owner.get("full_name"):
            parts = owner["full_name"].strip().split(None, 1)
            first = parts[0] if parts else ""
            last = parts[1] if len(parts) > 1 else ""

        if first:
            contact["firstName"] = first
        if last:
            contact["lastName"] = last

        # Contact info — prefer owner phone/email, fall back to business
        phone = owner.get("phone") or biz.get("phone")
        email = owner.get("email") or biz.get("email")
        if phone:
            contact["phone"] = self._clean_phone(phone)
        if email:
            contact["email"] = email.strip().lower()

        # Business details
        company = biz.get("legal_name") or biz.get("dba")
        if company:
            contact["companyName"] = company
        if biz.get("website"):
            contact["website"] = biz["website"]
        if biz.get("address"):
            contact["address1"] = biz["address"]
        if biz.get("city"):
            contact["city"] = biz["city"]
        if biz.get("state"):
            contact["state"] = biz["state"]
        if biz.get("zip_code"):
            contact["postalCode"] = biz["zip_code"]

        # Tags
        contact["tags"] = self._merge_tags([], extracted, None)

        # Source
        contact["source"] = "Telegram MCA Pipeline"

        # Custom fields
        custom = self._build_custom_fields({}, biz, owner, fin, mca, extracted)
        if custom:
            contact["customField"] = custom

        return contact

    # -------------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------------

    def _merge_standard_fields(
        self,
        existing: Dict[str, Any],
        biz: Dict[str, Any],
        owner: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Merge top-level GHL standard fields, never overwriting with empty values."""
        update: Dict[str, Any] = {}

        # Owner name
        first = owner.get("first_name")
        last = owner.get("last_name")
        if not first and not last and owner.get("full_name"):
            parts = owner["full_name"].strip().split(None, 1)
            first = parts[0] if parts else None
            last = parts[1] if len(parts) > 1 else None

        self._set_if_better(update, existing, "firstName", first)
        self._set_if_better(update, existing, "lastName", last)

        # Contact info
        phone = owner.get("phone") or biz.get("phone")
        email = owner.get("email") or biz.get("email")
        if phone:
            phone = self._clean_phone(phone)
        if email:
            email = email.strip().lower()

        self._set_if_better(update, existing, "phone", phone)
        self._set_if_better(update, existing, "email", email)

        # Business
        company = biz.get("legal_name") or biz.get("dba")
        self._set_if_better(update, existing, "companyName", company)
        self._set_if_better(update, existing, "website", biz.get("website"))
        self._set_if_better(update, existing, "address1", biz.get("address"))
        self._set_if_better(update, existing, "city", biz.get("city"))
        self._set_if_better(update, existing, "state", biz.get("state"))
        self._set_if_better(update, existing, "postalCode", biz.get("zip_code"))

        return update

    def _build_custom_fields(
        self,
        existing: Dict[str, Any],
        biz: Dict[str, Any],
        owner: Dict[str, Any],
        fin: Dict[str, Any],
        mca: Dict[str, Any],
        extracted: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Build a dict of custom field values to set/update.

        GHLClient._format_custom_fields will convert this to the array format
        GHL expects before sending.
        """
        custom: Dict[str, Any] = {}

        # Business identifiers
        if biz.get("ein"):
            custom["ein"] = biz["ein"]
        if biz.get("dba"):
            custom["dba_name"] = biz["dba"]
        if biz.get("entity_type"):
            custom["entity_type"] = biz["entity_type"]
        if biz.get("industry"):
            custom["industry"] = biz["industry"]
        if biz.get("start_date"):
            custom["business_start_date"] = biz["start_date"]
        if biz.get("time_in_business_months"):
            custom["time_in_business_months"] = str(biz["time_in_business_months"])

        # Owner extras
        if owner.get("title"):
            custom["owner_title"] = owner["title"]
        if owner.get("ownership_percentage"):
            custom["ownership_pct"] = str(owner["ownership_percentage"])

        # Financials — prefer higher revenue, newer credit score
        existing_custom = self._existing_custom_map(existing)

        if fin.get("monthly_revenue"):
            existing_rev = self._to_float(existing_custom.get("monthly_revenue"))
            new_rev = self._to_float(fin["monthly_revenue"])
            if new_rev and (not existing_rev or new_rev > existing_rev):
                custom["monthly_revenue"] = str(fin["monthly_revenue"])

        if fin.get("annual_revenue"):
            custom["annual_revenue"] = str(fin["annual_revenue"])

        if fin.get("requested_amount"):
            custom["requested_amount"] = str(fin["requested_amount"])

        if fin.get("use_of_funds"):
            custom["use_of_funds"] = fin["use_of_funds"]

        if fin.get("credit_score"):
            # Always prefer the newest credit score
            custom["credit_score"] = str(fin["credit_score"])

        # MCA history
        if mca.get("has_existing_mca") is not None:
            custom["has_existing_mca"] = str(mca["has_existing_mca"]).lower()
        if mca.get("current_funder"):
            custom["current_mca_funder"] = mca["current_funder"]
        if mca.get("daily_payment"):
            custom["mca_daily_payment"] = str(mca["daily_payment"])
        if mca.get("remaining_balance"):
            custom["mca_remaining_balance"] = str(mca["remaining_balance"])
        if mca.get("position"):
            custom["mca_position"] = str(mca["position"])

        # Document metadata
        if extracted.get("document_type"):
            custom["last_document_type"] = extracted["document_type"]
        if extracted.get("confidence"):
            custom["extraction_confidence"] = str(round(extracted["confidence"], 2))

        return custom

    def _merge_tags(
        self,
        existing_tags: Any,
        extracted: Dict[str, Any],
        match_method: Optional[str],
    ) -> List[str]:
        """Build a deduplicated tag list combining existing and new tags."""
        tags: List[str] = []
        if isinstance(existing_tags, list):
            tags = [t for t in existing_tags if isinstance(t, str)]
        elif isinstance(existing_tags, str):
            tags = [t.strip() for t in existing_tags.split(",") if t.strip()]

        # Add pipeline tags
        new_tags = ["telegram-lead"]

        doc_type = extracted.get("document_type", "")
        if doc_type:
            new_tags.append(f"doc-{doc_type.lower()}")

        if match_method:
            new_tags.append(f"matched-{match_method.lower()}")

        mca = extracted.get("mca_history", {}) or {}
        if mca.get("has_existing_mca"):
            new_tags.append("existing-mca")

        fin = extracted.get("financial_info", {}) or {}
        rev = self._to_float(fin.get("monthly_revenue"))
        if rev and rev >= 50000:
            new_tags.append("high-revenue")

        # Deduplicate (case-insensitive) while preserving order
        seen = {t.lower() for t in tags}
        for t in new_tags:
            if t.lower() not in seen:
                tags.append(t)
                seen.add(t.lower())

        return tags

    # -------------------------------------------------------------------------
    # Utility methods
    # -------------------------------------------------------------------------

    @staticmethod
    def _set_if_better(
        update: Dict[str, Any],
        existing: Dict[str, Any],
        key: str,
        new_value: Optional[str],
    ):
        """Set key in update dict only if new_value is non-empty and existing is empty."""
        if not new_value:
            return
        existing_val = existing.get(key)
        if not existing_val:
            update[key] = new_value

    @staticmethod
    def _existing_custom_map(contact: Dict[str, Any]) -> Dict[str, str]:
        """Convert GHL custom field array to a simple dict for lookups."""
        result: Dict[str, str] = {}
        custom_fields = contact.get("customField", [])
        if isinstance(custom_fields, list):
            for cf in custom_fields:
                fid = cf.get("id", "")
                fval = cf.get("value", "")
                if fid and fval:
                    result[fid] = str(fval)
        return result

    @staticmethod
    def _to_float(val: Any) -> Optional[float]:
        if val is None:
            return None
        try:
            return float(val)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _clean_phone(raw: str) -> str:
        """Quick phone cleanup — strip to digits and prepend +1 if needed."""
        digits = re.sub(r"\D", "", raw)
        if len(digits) == 10:
            return f"+1{digits}"
        if len(digits) == 11 and digits.startswith("1"):
            return f"+{digits}"
        return raw
