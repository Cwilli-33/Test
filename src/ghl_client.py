"""GoHighLevel API client — Private Integration (v2 API) support."""
import httpx
import logging
import uuid
from typing import Any, Dict, List, Optional

from config.settings import settings

logger = logging.getLogger(__name__)

# Private Integration keys (pit-) use the v2 API
V2_BASE_URL = "https://services.leadconnectorhq.com"


class GHLClient:
    def __init__(self):
        self.api_key = settings.ghl_api_key
        self.location_id = settings.ghl_location_id
        self.base_url = V2_BASE_URL
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Version": "2021-07-28",
        }

    async def search_contacts(self, query: str) -> List[Dict[str, Any]]:
        """Search GHL contacts by a query string."""
        url = f"{self.base_url}/contacts/"
        params = {
            "locationId": self.location_id,
            "query": query,
            "limit": 20,
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, headers=self.headers, params=params)
                logger.debug(f"GHL search response: {response.status_code} {response.text[:500]}")
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

        The v2 API uses 'query' param for general search. For specific fields
        we just use the query param with the value.
        """
        url = f"{self.base_url}/contacts/"
        params = {
            "locationId": self.location_id,
            "query": value,
            "limit": 20,
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, headers=self.headers, params=params)
                logger.debug(f"GHL field search response: {response.status_code} {response.text[:500]}")
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
        """Create a new contact in GHL via v2 API.

        Args:
            contact_data: Dict with contact fields. Expected keys:
                - firstName, lastName, email, phone, companyName, address1,
                  city, state, postalCode, website, tags, customFields, source

        Returns:
            Created contact dict from GHL, or None on failure.
        """
        url = f"{self.base_url}/contacts/"

        payload = {
            "locationId": self.location_id,
            **contact_data,
        }

        # v2 API uses "customFields" (not "customField") as an array of {id, field_value}
        if "customField" in payload:
            cf = payload.pop("customField")
            if isinstance(cf, dict):
                payload["customFields"] = self._format_custom_fields(cf)
            elif isinstance(cf, list):
                payload["customFields"] = cf

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                logger.debug(f"GHL create payload: {payload}")
                response = await client.post(url, headers=self.headers, json=payload)
                logger.debug(f"GHL create response: {response.status_code} {response.text[:500]}")
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
        """Update an existing contact in GHL via v2 API."""
        url = f"{self.base_url}/contacts/{contact_id}"

        payload = {**contact_data}

        if "customField" in payload:
            cf = payload.pop("customField")
            if isinstance(cf, dict):
                payload["customFields"] = self._format_custom_fields(cf)
            elif isinstance(cf, list):
                payload["customFields"] = cf

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.put(url, headers=self.headers, json=payload)
                logger.debug(f"GHL update response: {response.status_code} {response.text[:500]}")
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
        """Fetch a single contact by ID."""
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

    async def upload_file_to_custom_field(
        self,
        contact_id: str,
        custom_field_id: str,
        file_bytes: bytes,
        filename: str = "lead_document.jpg",
        content_type: str = "image/jpeg",
    ) -> Optional[Dict[str, Any]]:
        """Upload a file to a FILE_UPLOAD custom field on a contact.

        Uses POST /forms/upload-custom-files (multipart/form-data).
        Max 50 MB per file.  Multi-file fields accumulate files; each
        call adds one more.

        Args:
            contact_id: The GHL contact ID.
            custom_field_id: The GHL custom field ID (FILE_UPLOAD type).
            file_bytes: Raw file bytes.
            filename: Filename for the upload.
            content_type: MIME type of the file.

        Returns:
            Updated contact dict, or None on failure.
        """
        url = f"{self.base_url}/forms/upload-custom-files"

        upload_headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Version": "2021-07-28",
            "Accept": "application/json",
        }

        params = {
            "contactId": contact_id,
            "locationId": self.location_id,
        }

        # Field name must be {customFieldId}_{randomUUID}
        file_id = str(uuid.uuid4())
        field_name = f"{custom_field_id}_{file_id}"

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                files = {field_name: (filename, file_bytes, content_type)}

                response = await client.post(
                    url, headers=upload_headers, params=params, files=files
                )
                logger.debug(
                    f"GHL file upload response: {response.status_code} {response.text[:500]}"
                )
                response.raise_for_status()
                result = response.json()
                logger.info(
                    f"Uploaded file '{filename}' to custom field {custom_field_id} "
                    f"on contact {contact_id}"
                )
                return result.get("contact", result)
        except httpx.HTTPStatusError as e:
            logger.error(
                f"GHL file upload failed ({e.response.status_code}): {e.response.text}"
            )
            return None
        except Exception as e:
            logger.error(f"GHL file upload error: {e}", exc_info=True)
            return None

    def _format_custom_fields(self, custom_fields: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Convert a dict of custom fields to GHL v2 expected array format.

        v2 API expects: [{"id": "field_key", "field_value": "value"}, ...]
        We accept:      {"field_key": "value", ...}
        """
        return [
            {"id": k, "field_value": v}
            for k, v in custom_fields.items()
            if v is not None
        ]
