"""Smart data merging — combines extracted data with existing GHL contact data.

Maps extracted fields to exact GHL custom field IDs for the location.
"""
import json
import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# GHL Custom Field ID mapping (from location xUrzKPGPYMeo1BSR9a0P)
# ---------------------------------------------------------------------------
# These IDs come from the GHL API: GET /locations/{id}/customFields
# The key is a readable name; the value is the GHL field ID.

GHL_CUSTOM_FIELDS = {
    # Business identifiers
    "ein":                      "24QthvUKjKiEWBJr5kGN",
    "dba":                      "e34gazjAyNSaDXIWZOmq",
    "business_start_date":      "TtdjtsXprss3caSuPyXP",
    "state_of_incorporation":   "XFs2Swg2iv7eUcj18MI5",
    "industry":                 "3ZAqSshPhgXPUlLjRUNd",
    "business_phone":           "Mk6gFArjGHC91aosp0ql",
    "funding_requested":        "Qi236dvs25FS7laGaWq9",

    # Owner 2
    "owner_2_name":             "6COH4V1v30QoSgruiZpO",
    "owner_2_phone":            "LddyH78lQfPPfdvVFIGk",

    # Financials
    "monthly_revenue":          "4nwh9GkL87CPx3rvYXte",
    "avg_daily_balance":        "Cwd0VoL1uJq5cyM9pfAB",
    "true_revenue_avg_3mo":     "jsqyKetf6dr66ku3vQXb",

    # Credit
    "fico_owner1":              "8xhJtYRSWIy1fxBmrO0n",
    "fico_owner2":              "SSSP2fzyfGVUMsghsaL0",
    "satisfactory_accounts":    "kJPaOajlJy1cqSSIZBcz",
    "total_tradelines":         "NJbDArsoKKJuCLSb8Eoj",
    "now_delinquent":           "3NHx3LTaUEnxFUdPo0wo",
    "num_chargeoffs":           "oABAg6qGnNSortIGFGwy",
    "leverage_pct":             "oJZ9IERN5LL8BWMjTSiq",

    # MCA positions
    "num_positions":            "fKaTtIOb9JTypnAMUhx4",
    "num_existing_positions":   "FRvcdvhGlUqp9q9ewfXD",

    # Credit
    "statement_number":         "AXQyV1j0A8ByYGLvVFon",

    # Owner 1 home address
    "owner1_address":           "DUonmL5QgCisIDqFlPLy",
    "owner1_city":              "Pn4y4ppf4R5PLjJwRzcQ",
    "owner1_state":             "qAhft8fEIXB4A9fdmJLp",
    "owner1_zip":               "harMFyX4xvXghV4ksksB",

    # Metadata
    "ai_confidence":            "JAkXR6AT0kMzSm25b7Dt",
    "ai_flags":                 "xoReYLVOg7u0sb4flE0S",
    "batch_date":               "f7D788L5PQXxQHBZ1uRj",
    "iso_name":                 "A907hIwQGuzA0K6HLSeI",
    "source_platform":          "rHO4Rb6Fi8J9Rb6Oxz0I",
}


class DataMerger:
    """Merges newly extracted lead data with an existing GHL contact.

    Rules:
        - Never overwrite existing data with empty/null values.
        - For numeric fields (revenue, credit score), prefer the higher or newer value.
        - For tags, append new tags without duplicating existing ones.
        - Custom fields are mapped by exact GHL field IDs.
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
            match_method: How the match was made (EIN, PHONE, EMAIL, NAME, etc.).
            match_confidence: 0-100 confidence in the match.

        Returns:
            Dict payload suitable for GHLClient.update_contact().
        """
        biz = extracted.get("business_info", {}) or {}
        owner = extracted.get("owner_info", {}) or {}
        owner2 = extracted.get("owner2_info", {}) or {}
        fin = extracted.get("financial_info", {}) or {}
        credit = extracted.get("credit_info", {}) or {}
        mca = extracted.get("mca_info", {}) or {}
        iso = extracted.get("iso_info", {}) or {}

        update: Dict[str, Any] = {}

        # --- Standard fields ---
        update.update(self._merge_standard_fields(existing_contact, biz, owner))

        # --- Tags ---
        update["tags"] = self._merge_tags(
            existing_contact.get("tags", []),
            extracted,
            match_method,
        )

        # --- Custom fields (using GHL field IDs) ---
        custom = self._build_custom_fields(
            existing_contact, biz, owner, owner2, fin, credit, mca, iso, extracted
        )
        if custom:
            update["customFields"] = self._format_custom_fields(custom)

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
        owner2 = extracted.get("owner2_info", {}) or {}
        fin = extracted.get("financial_info", {}) or {}
        credit = extracted.get("credit_info", {}) or {}
        mca = extracted.get("mca_info", {}) or {}
        iso = extracted.get("iso_info", {}) or {}

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
        custom = self._build_custom_fields(
            {}, biz, owner, owner2, fin, credit, mca, iso, extracted
        )
        if custom:
            contact["customFields"] = self._format_custom_fields(custom)

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
        owner2: Dict[str, Any],
        fin: Dict[str, Any],
        credit: Dict[str, Any],
        mca: Dict[str, Any],
        iso: Dict[str, Any],
        extracted: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Build a dict of {ghl_field_id: value} for custom fields.

        Uses the GHL_CUSTOM_FIELDS mapping to produce exact field IDs.
        """
        custom: Dict[str, Any] = {}
        existing_custom = self._existing_custom_map(existing)

        # --- Business identifiers ---
        self._set_custom(custom, "ein", biz.get("ein"))
        self._set_custom(custom, "dba", biz.get("dba"))
        self._set_custom(custom, "business_start_date", biz.get("start_date"))
        self._set_custom(custom, "state_of_incorporation", biz.get("state_of_incorporation"))
        self._set_custom(custom, "industry", biz.get("industry"))
        self._set_custom(custom, "business_phone", biz.get("phone"))
        self._set_custom_numeric(custom, existing_custom, "funding_requested", fin.get("funding_requested"))

        # --- Owner 2 ---
        self._set_custom(custom, "owner_2_name", owner2.get("full_name"))
        self._set_custom(custom, "owner_2_phone", owner2.get("phone"))

        # --- Financials (prefer higher revenue, newer values) ---
        self._set_custom_numeric_prefer_higher(
            custom, existing_custom, "monthly_revenue", fin.get("monthly_revenue")
        )
        self._set_custom_numeric(custom, existing_custom, "avg_daily_balance", fin.get("avg_daily_balance"))
        self._set_custom_numeric_prefer_higher(
            custom, existing_custom, "true_revenue_avg_3mo", fin.get("true_revenue_avg_3mo")
        )

        # --- Credit info ---
        self._set_custom_numeric(custom, existing_custom, "fico_owner1", credit.get("fico_owner1"))
        self._set_custom_numeric(
            custom, existing_custom, "fico_owner2",
            credit.get("fico_owner2") or owner2.get("fico")
        )
        self._set_custom_numeric(custom, existing_custom, "satisfactory_accounts", credit.get("satisfactory_accounts"))
        self._set_custom_numeric(custom, existing_custom, "total_tradelines", credit.get("total_tradelines"))
        self._set_custom_numeric(custom, existing_custom, "now_delinquent", credit.get("now_delinquent"))
        self._set_custom_numeric(custom, existing_custom, "num_chargeoffs", credit.get("num_chargeoffs"))
        self._set_custom_numeric(custom, existing_custom, "leverage_pct", credit.get("leverage_pct"))

        # Statement numbers — accumulate across documents, don't overwrite
        new_stmts = extracted.get("statement_numbers")
        if new_stmts:
            existing_stmts = existing_custom.get(GHL_CUSTOM_FIELDS.get("statement_number", ""), "")
            merged = self._merge_statement_numbers(existing_stmts, new_stmts)
            if merged:
                ghl_id = GHL_CUSTOM_FIELDS.get("statement_number")
                if ghl_id:
                    custom[ghl_id] = merged

        # --- MCA positions ---
        self._set_custom_numeric(custom, existing_custom, "num_positions", mca.get("num_positions"))
        self._set_custom_numeric(custom, existing_custom, "num_existing_positions", mca.get("num_existing_positions"))

        # --- Owner 1 home address ---
        self._set_custom(custom, "owner1_address", owner.get("home_address"))
        self._set_custom(custom, "owner1_city", owner.get("home_city"))
        self._set_custom(custom, "owner1_state", owner.get("home_state"))
        self._set_custom(custom, "owner1_zip", owner.get("home_zip"))

        # --- ISO / Source ---
        self._set_custom(custom, "iso_name", iso.get("iso_name"))
        self._set_custom(custom, "source_platform", iso.get("source_platform") or "Telegram")

        # --- Metadata ---
        confidence = extracted.get("confidence")
        if confidence is not None:
            custom[GHL_CUSTOM_FIELDS["ai_confidence"]] = str(round(float(confidence), 2))

        # Build AI flags
        flags = self._build_ai_flags(extracted)
        if flags:
            custom[GHL_CUSTOM_FIELDS["ai_flags"]] = ", ".join(flags)

        # Batch date (today's date as YYYYMMDD for sorting)
        custom[GHL_CUSTOM_FIELDS["batch_date"]] = datetime.utcnow().strftime("%Y%m%d")

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

        mca = extracted.get("mca_info", {}) or {}
        has_positions = mca.get("has_existing_positions")
        # Guard against string "false" being truthy
        if isinstance(has_positions, str):
            has_positions = has_positions.lower() not in ("false", "no", "none", "0", "")
        if has_positions or mca.get("num_positions"):
            new_tags.append("existing-mca")

        fin = extracted.get("financial_info", {}) or {}
        rev = self._to_float(fin.get("monthly_revenue"))
        if rev and rev >= 50000:
            new_tags.append("high-revenue")

        credit = extracted.get("credit_info", {}) or {}
        fico = self._to_float(credit.get("fico_owner1"))
        if fico:
            if fico >= 700:
                new_tags.append("fico-700+")
            elif fico < 550:
                new_tags.append("fico-sub550")

        # Deduplicate (case-insensitive) while preserving order
        seen = {t.lower() for t in tags}
        for t in new_tags:
            if t.lower() not in seen:
                tags.append(t)
                seen.add(t.lower())

        return tags

    def _build_ai_flags(self, extracted: Dict[str, Any]) -> List[str]:
        """Generate AI-derived flags/warnings about the lead."""
        flags = []
        credit = extracted.get("credit_info", {}) or {}
        fin = extracted.get("financial_info", {}) or {}
        mca = extracted.get("mca_info", {}) or {}

        fico = self._to_float(credit.get("fico_owner1"))
        if fico and fico < 550:
            flags.append("LOW_FICO")

        delinquent = self._to_float(credit.get("now_delinquent"))
        if delinquent and delinquent > 3:
            flags.append("HIGH_DELINQUENCY")

        chargeoffs = self._to_float(credit.get("num_chargeoffs"))
        if chargeoffs and chargeoffs > 0:
            flags.append("HAS_CHARGEOFFS")

        leverage = self._to_float(credit.get("leverage_pct"))
        if leverage and leverage > 80:
            flags.append("HIGH_LEVERAGE")

        positions = self._to_float(mca.get("num_positions"))
        if positions and positions >= 3:
            flags.append("3+_POSITIONS")

        rev = self._to_float(fin.get("monthly_revenue"))
        if rev and rev < 15000:
            flags.append("LOW_REVENUE")

        confidence = self._to_float(extracted.get("confidence"))
        if confidence and confidence < 0.7:
            flags.append("LOW_AI_CONFIDENCE")

        return flags

    # -------------------------------------------------------------------------
    # Custom field helpers
    # -------------------------------------------------------------------------

    def _set_custom(self, custom: Dict, field_name: str, value: Any) -> None:
        """Set a custom field by name (maps to GHL ID) if value is non-empty."""
        if not value:
            return
        ghl_id = GHL_CUSTOM_FIELDS.get(field_name)
        if ghl_id:
            custom[ghl_id] = str(value)

    def _set_custom_numeric(
        self, custom: Dict, existing_custom: Dict, field_name: str, value: Any
    ) -> None:
        """Set a numeric custom field, always preferring a new non-null value."""
        new_val = self._to_float(value)
        if new_val is None:
            return
        ghl_id = GHL_CUSTOM_FIELDS.get(field_name)
        if ghl_id:
            custom[ghl_id] = str(new_val)

    def _set_custom_numeric_prefer_higher(
        self, custom: Dict, existing_custom: Dict, field_name: str, value: Any
    ) -> None:
        """Set a numeric custom field, preferring the higher of existing vs new."""
        new_val = self._to_float(value)
        if new_val is None:
            return
        ghl_id = GHL_CUSTOM_FIELDS.get(field_name)
        if not ghl_id:
            return
        existing_val = self._to_float(existing_custom.get(ghl_id))
        if existing_val and existing_val > new_val:
            return  # Keep existing higher value
        custom[ghl_id] = str(new_val)

    @staticmethod
    def _format_custom_fields(custom: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Convert {ghl_id: value} dict to GHL v2 API array format.

        v2 API expects: [{"id": "field_id", "field_value": "value"}, ...]
        """
        return [
            {"id": k, "field_value": v}
            for k, v in custom.items()
            if v is not None
        ]

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
        """Convert GHL custom field array to a simple {id: value} dict for lookups."""
        result: Dict[str, str] = {}
        # v2 API returns customFields as array
        custom_fields = contact.get("customFields", contact.get("customField", []))
        if isinstance(custom_fields, list):
            for cf in custom_fields:
                fid = cf.get("id", "")
                fval = cf.get("field_value", cf.get("value", ""))
                if fid and fval:
                    result[fid] = str(fval)
        return result

    @staticmethod
    def _to_float(val: Any) -> Optional[float]:
        if val is None:
            return None
        try:
            # Handle strings like "$50,000" or "75%"
            if isinstance(val, str):
                cleaned = val.replace("$", "").replace(",", "").replace("%", "").strip()
                return float(cleaned) if cleaned else None
            return float(val)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _merge_statement_numbers(existing: str, new: str) -> str:
        """Merge existing and new statement numbers, deduplicating.

        Both values are comma-separated strings like
        'XXXXXX5800, XXXXXXXXXXXX9112'. Returns a single deduplicated
        comma-separated string preserving order (new first, then any
        existing ones not already present).
        """
        seen = set()
        result = []

        for raw in [new, existing]:
            if not raw:
                continue
            for item in raw.split(","):
                item = item.strip()
                if item and item not in seen:
                    seen.add(item)
                    result.append(item)

        return ", ".join(result)

    @staticmethod
    def _clean_phone(raw: str) -> str:
        """Quick phone cleanup — strip to digits and prepend +1 if needed."""
        digits = re.sub(r"\D", "", raw)
        if len(digits) == 10:
            return f"+1{digits}"
        if len(digits) == 11 and digits.startswith("1"):
            return f"+{digits}"
        return raw
