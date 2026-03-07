"""GoHighLevel API client — Private Integration (v2 API) support."""
import asyncio
import httpx
import logging
import uuid
from typing import Any, Dict, List, Optional

from config.settings import settings

logger = logging.getLogger(__name__)

# Private Integration keys (pit-) use the v2 API
V2_BASE_URL = "https://services.leadconnectorhq.com"

# Retry configuration
MAX_RETRIES = 3
RETRY_BASE_DELAY = 1.0  # seconds
RETRY_MAX_DELAY = 30.0  # seconds
RETRYABLE_STATUS_CODES = {429, 500, 502, 503}


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
        # Shared persistent HTTP client — reuses TCP connections across all
        # GHL API calls instead of opening a new connection every time.
        self._client = httpx.AsyncClient(
            timeout=30.0,
            limits=httpx.Limits(
                max_connections=20,
                max_keepalive_connections=10,
                keepalive_expiry=30,
            ),
        )

    async def close(self):
        """Close the shared HTTP client (call on app shutdown)."""
        await self._client.aclose()
        logger.info("GHL HTTP client closed")

    async def _request_with_retry(
        self,
        method: str,
        url: str,
        label: str = "GHL API",
        **kwargs,
    ) -> httpx.Response:
        """Make an HTTP request with exponential backoff retry on transient errors.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE).
            url: Request URL.
            label: Human-readable label for log messages.
            **kwargs: Passed through to httpx (headers, params, json, files, etc.).

        Returns:
            httpx.Response on success.

        Raises:
            Last exception if all retries exhausted.
        """
        last_error = None
        # Allow per-call timeout override (e.g. file uploads use 90s)
        timeout_override = kwargs.pop("timeout", None)

        for attempt in range(MAX_RETRIES):
            try:
                request_kwargs = {**kwargs}
                if timeout_override is not None:
                    request_kwargs["timeout"] = timeout_override

                response = await getattr(self._client, method.lower())(url, **request_kwargs)
                # Check if we got a retryable status code
                if response.status_code in RETRYABLE_STATUS_CODES:
                    if attempt < MAX_RETRIES - 1:
                        delay = min(RETRY_BASE_DELAY * (2 ** attempt), RETRY_MAX_DELAY)
                        logger.warning(
                            f"{label} returned {response.status_code} "
                            f"(attempt {attempt + 1}/{MAX_RETRIES}), "
                            f"retrying in {delay:.1f}s"
                        )
                        await asyncio.sleep(delay)
                        continue
                response.raise_for_status()
                return response

            except httpx.HTTPStatusError as e:
                last_error = e
                if e.response.status_code in RETRYABLE_STATUS_CODES and attempt < MAX_RETRIES - 1:
                    delay = min(RETRY_BASE_DELAY * (2 ** attempt), RETRY_MAX_DELAY)
                    logger.warning(
                        f"{label} failed with {e.response.status_code} "
                        f"(attempt {attempt + 1}/{MAX_RETRIES}), "
                        f"retrying in {delay:.1f}s"
                    )
                    await asyncio.sleep(delay)
                    continue
                raise

            except (httpx.ConnectError, httpx.ReadTimeout, httpx.WriteTimeout) as e:
                last_error = e
                if attempt < MAX_RETRIES - 1:
                    delay = min(RETRY_BASE_DELAY * (2 ** attempt), RETRY_MAX_DELAY)
                    logger.warning(
                        f"{label} connection error (attempt {attempt + 1}/{MAX_RETRIES}), "
                        f"retrying in {delay:.1f}s: {e}"
                    )
                    await asyncio.sleep(delay)
                    continue
                raise

        raise last_error

    async def search_contacts(self, query: str) -> List[Dict[str, Any]]:
        """Search GHL contacts by a query string."""
        url = f"{self.base_url}/contacts/"
        params = {
            "locationId": self.location_id,
            "query": query,
            "limit": 20,
        }

        try:
            response = await self._request_with_retry(
                "GET", url, label="GHL search",
                headers=self.headers, params=params,
            )
            logger.debug(f"GHL search response: {response.status_code} {response.text[:500]}")
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
            response = await self._request_with_retry(
                "GET", url, label=f"GHL field search ({field})",
                headers=self.headers, params=params,
            )
            logger.debug(f"GHL field search response: {response.status_code} {response.text[:500]}")
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
            logger.debug(f"GHL create payload: {payload}")
            response = await self._request_with_retry(
                "POST", url, label="GHL create contact",
                headers=self.headers, json=payload,
            )
            logger.debug(f"GHL create response: {response.status_code} {response.text[:500]}")
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
            response = await self._request_with_retry(
                "PUT", url, label=f"GHL update contact {contact_id}",
                headers=self.headers, json=payload,
            )
            logger.debug(f"GHL update response: {response.status_code} {response.text[:500]}")
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
            response = await self._request_with_retry(
                "GET", url, label=f"GHL get contact {contact_id}",
                headers=self.headers,
            )
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
        """Upload a file to a FILE_UPLOAD custom field on a contact,
        preserving any files already stored in that field.

        The /forms/upload-custom-files endpoint REPLACES the field value
        on every call, so we must:
          1. Fetch the contact to read existing files in the field.
          2. Re-download each existing file's bytes.
          3. POST all existing files + the new file in a single request.

        Args:
            contact_id: The GHL contact ID.
            custom_field_id: The GHL custom field ID (FILE_UPLOAD type).
            file_bytes: Raw file bytes for the NEW file.
            filename: Filename for the new file.
            content_type: MIME type of the new file.

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

        # -- Gather existing files so they aren't overwritten --
        existing_files: list[tuple[str, bytes, str, str]] = []  # (filename, bytes, mime, uuid)
        try:
            contact = await self.get_contact(contact_id)
            if contact:
                cfs = contact.get("customFields", contact.get("customField", []))
                for cf in cfs:
                    if cf.get("id") == custom_field_id:
                        field_val = cf.get("value")
                        if isinstance(field_val, dict):
                            existing_files = await self._download_existing_files(
                                field_val
                            )
                        break
        except Exception as e:
            logger.warning(f"Could not read existing files, will upload new only: {e}")

        # -- Build multi-file form --
        # Each form field: {customFieldId}_{uuid} = (filename, bytes, mime)
        files_payload: list[tuple[str, tuple[str, bytes, str]]] = []

        # Re-include existing files under their original UUIDs
        for ex_name, ex_bytes, ex_mime, ex_uuid in existing_files:
            field_name = f"{custom_field_id}_{ex_uuid}"
            files_payload.append((field_name, (ex_name, ex_bytes, ex_mime)))

        # Add the new file
        new_uuid = str(uuid.uuid4())
        new_field_name = f"{custom_field_id}_{new_uuid}"
        files_payload.append((new_field_name, (filename, file_bytes, content_type)))

        try:
            response = await self._request_with_retry(
                "POST", url, label="GHL file upload",
                headers=upload_headers, params=params, files=files_payload,
                timeout=90.0,
            )
            logger.debug(
                f"GHL file upload response: {response.status_code} {response.text[:500]}"
            )
            result = response.json()
            total = len(files_payload)
            logger.info(
                f"Uploaded {total} file(s) (1 new + {total - 1} existing) to "
                f"custom field {custom_field_id} on contact {contact_id}"
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

    async def _download_existing_files(
        self, field_value: dict
    ) -> list[tuple[str, bytes, str, str]]:
        """Download existing files from a FILE_UPLOAD custom field value.

        Args:
            field_value: Dict of {uuid: {meta: {...}, url: ..., documentId: ...}}

        Returns:
            List of (filename, file_bytes, mime_type, original_uuid) tuples.
        """
        results = []
        for file_uuid, file_info in field_value.items():
            if not isinstance(file_info, dict):
                continue
            meta = file_info.get("meta", {})
            download_url = file_info.get("url")
            if not download_url:
                continue

            fname = meta.get("originalname", "existing_file.jpg")
            mime = meta.get("mimetype", "image/jpeg")

            try:
                resp = await self._client.get(
                    download_url,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    follow_redirects=True,
                    timeout=60.0,
                )
                resp.raise_for_status()
                results.append((fname, resp.content, mime, file_uuid))
                logger.debug(f"Re-downloaded existing file: {fname} ({len(resp.content)} bytes)")
            except Exception as e:
                logger.warning(f"Could not re-download {fname}: {e}")

        return results

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
