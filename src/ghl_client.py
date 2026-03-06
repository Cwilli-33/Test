"""GoHighLevel API client for contact search, creation, and updates."""
import httpx
import logging
from typing import Any, Dict, List, Optional

from config.settings import settings

logger = logging.getLogger(__name__)


class GHLClient:
    def __init__(self):
        self.api_key = settings.ghl_api_key
        self.location_id = settings.ghl_location_id
        self.base_url = settings.ghl_api_base_url.rstrip("/")
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def search_contacts(self, query: str) -> List[Dict[str, Any]]:
        """Search GHL contacts by a query string (phone, email, name, etc.).

        Args:
            query: Search term to look up contacts.

        Returns:
            List of matching contact dicts from GHL.
        """
        url = f"{self.base_url}/contacts/"
        params = {
            "locationId": self.location_id,
            "query": query,
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, headers=self.headers, params=params)
                response.raise_for_status()
                data = response.json()
                contacts = data.get("contacts", [])
                logger.info(f"GHL search '{query}' returned {len(contacts)} contacts")
                return contacts
        except httpx.HTTPStatusError as e:
            logger.error(f"GHL search failed ({e.response.status_code}): {e.response.text}")
            return []
        except Exception as e:
            logger.error(f"GHL search error: {e}", exc_info=True)
            return []

    async def search_by_field(self, field: str, value: str) -> List[Dict[str, Any]]:
        """Search contacts by a specific field (email, phone).

        GHL's v1 API search endpoint accepts query params for specific fields.
        """
        url = f"{self.base_url}/contacts/"
        params = {
            "locationId": self.location_id,
            field: value,
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, headers=self.headers, params=params)
                response.raise_for_status()
                data = response.json()
                contacts = data.get("contacts", [])
                logger.info(f"GHL search {field}='{value}' returned {len(contacts)} contacts")
                return contacts
        except httpx.HTTPStatusError as e:
            logger.error(f"GHL field search failed ({e.response.status_code}): {e.response.text}")
            return []
        except Exception as e:
            logger.error(f"GHL field search error: {e}", exc_info=True)
            return []

    async def create_contact(self, contact_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Create a new contact in GHL.

        Args:
            contact_data: Dict with contact fields. Expected keys:
                - firstName, lastName, email, phone, companyName, address1,
                  city, state, postalCode, website, tags, customField, source

        Returns:
            Created contact dict from GHL, or None on failure.
        """
        url = f"{self.base_url}/contacts/"

        payload = {
            "locationId": self.location_id,
            **contact_data,
        }

        # Format custom fields as GHL expects
        if "customField" in payload and isinstance(payload["customField"], dict):
            payload["customField"] = self._format_custom_fields(payload["customField"])

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, headers=self.headers, json=payload)
                response.raise_for_status()
                result = response.json()
                contact = result.get("contact", result)
                contact_id = contact.get("id", "unknown")
                logger.info(f"Created GHL contact: {contact_id}")
                return contact
        except httpx.HTTPStatusError as e:
            logger.error(
                f"GHL create failed ({e.response.status_code}): {e.response.text}"
            )
            return None
        except Exception as e:
            logger.error(f"GHL create error: {e}", exc_info=True)
            return None

    async def update_contact(
        self, contact_id: str, contact_data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Update an existing contact in GHL.

        Args:
            contact_id: GHL contact ID.
            contact_data: Dict of fields to update.

        Returns:
            Updated contact dict, or None on failure.
        """
        url = f"{self.base_url}/contacts/{contact_id}"

        payload = {**contact_data}

        if "customField" in payload and isinstance(payload["customField"], dict):
            payload["customField"] = self._format_custom_fields(payload["customField"])

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.put(url, headers=self.headers, json=payload)
                response.raise_for_status()
                result = response.json()
                contact = result.get("contact", result)
                logger.info(f"Updated GHL contact: {contact_id}")
                return contact
        except httpx.HTTPStatusError as e:
            logger.error(
                f"GHL update failed ({e.response.status_code}): {e.response.text}"
            )
            return None
        except Exception as e:
            logger.error(f"GHL update error: {e}", exc_info=True)
            return None

    async def get_contact(self, contact_id: str) -> Optional[Dict[str, Any]]:
        """Fetch a single contact by ID.

        Args:
            contact_id: GHL contact ID.

        Returns:
            Contact dict, or None on failure.
        """
        url = f"{self.base_url}/contacts/{contact_id}"

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, headers=self.headers)
                response.raise_for_status()
                result = response.json()
                return result.get("contact", result)
        except httpx.HTTPStatusError as e:
            logger.error(f"GHL get contact failed ({e.response.status_code}): {e.response.text}")
            return None
        except Exception as e:
            logger.error(f"GHL get contact error: {e}", exc_info=True)
            return None

    def _format_custom_fields(self, custom_fields: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Convert a dict of custom fields to GHL's expected array format.

        GHL expects: [{"id": "field_key", "value": "field_value"}, ...]
        We accept:   {"field_key": "field_value", ...}
        """
        return [{"id": k, "value": v} for k, v in custom_fields.items() if v is not None]
