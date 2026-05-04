# coding: utf-8
"""
oci_storage.py
Reusable OCI Object Storage helper for the Code Reviewer system.

Provides upload, list (paginated + date-filtered), and download of review reports.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from io import BytesIO
from typing import List, Dict, Optional

import oci

from logger import get_logger

log = get_logger(__name__)


def _get_storage_config() -> tuple[str, str]:
    """
    Return (compartment_id, bucket_name) from the runtime config.
    Imported lazily to always reflect the latest runtime overrides.
    """
    from config import OCI_STORAGE_COMPARTMENT_ID, OCI_BUCKET_NAME
    return OCI_STORAGE_COMPARTMENT_ID, OCI_BUCKET_NAME


class OCIStorageClient:
    """Thin wrapper around OCI ObjectStorageClient for review report management."""

    def __init__(self) -> None:
        from config import get_oci_auth
        log.info("Initialising OCI Object Storage client …")
        try:
            auth = get_oci_auth(service="storage")
        except Exception as exc:
            log.critical(
                "Failed to load OCI auth config.\n"
                "  WHAT WENT WRONG : %s\n"
                "  WHAT TO DO      : Ensure your settings are correctly configured.",
                exc
            )
            raise

        kwargs = {"config": auth.get("config", {})}
        if "signer" in auth:
            kwargs["signer"] = auth["signer"]

        self._client = oci.object_storage.ObjectStorageClient(**kwargs)
        self._namespace: Optional[str] = None
        log.info("OCI Object Storage client ready.")

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def namespace(self) -> str:
        if self._namespace is None:
            self._namespace = self._client.get_namespace().data
        return self._namespace

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def upload(self, file_path: str, object_name: str) -> bool:
        """
        Upload a local file to the configured OCI bucket.

        Args:
            file_path:   Absolute path of the local file to upload.
            object_name: Object key (path) in the OCI bucket.

        Returns:
            True on success, False on failure.
        """
        compartment_id, bucket_name = _get_storage_config()
        log.info("Uploading '%s' → OCI bucket '%s' as '%s' …", file_path, bucket_name, object_name)
        try:
            with open(file_path, "rb") as fh:
                data = fh.read()
            self._client.put_object(
                self.namespace,
                bucket_name,
                object_name,
                BytesIO(data),
                content_type="text/html; charset=utf-8",
            )
            log.info("Upload successful → %s/%s", bucket_name, object_name)
            return True
        except FileNotFoundError:
            log.error(
                "Upload failed — local file not found: %s\n"
                "  WHAT TO DO : Verify the report was generated before uploading.",
                file_path,
            )
            return False
        except oci.exceptions.ServiceError as exc:
            log.error(
                "OCI upload error.\n"
                "  HTTP STATUS : %s | CODE : %s | MESSAGE : %s",
                exc.status, exc.code, exc.message,
            )
            return False
        except Exception as exc:
            log.error("Unexpected upload error: %s", exc)
            return False

    def list_objects(
        self,
        page: int = 1,
        page_size: int = 20,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        prefix: str = "",
    ) -> Dict:
        """
        List objects in the bucket, sorted by last-modified descending.

        Args:
            page:       1-based page number.
            page_size:  Number of items per page.
            from_date:  Filter: only include objects modified on or after this datetime (UTC).
            to_date:    Filter: only include objects modified on or before this datetime (UTC).
            prefix:     OCI object name prefix filter.

        Returns:
            Dict with keys: ``items``, ``total``, ``page``, ``page_size``, ``total_pages``.
        """
        _, bucket_name = _get_storage_config()
        log.info(
            "Listing OCI bucket '%s' | prefix='%s' | page=%d | page_size=%d",
            bucket_name, prefix, page, page_size,
        )
        try:
            all_items: List[Dict] = []
            next_start_with: Optional[str] = None

            # Fetch ALL objects with just a name prefix (OCI does not support date-range natively)
            while True:
                kwargs = {
                    # "prefix": prefix if prefix else None,
                    "fields": "name,size,timeCreated",
                    "limit": 1000,
                }
                if next_start_with:
                    kwargs["start"] = next_start_with

                # Remove None prefix to avoid OCI SDK issues
                kwargs = {k: v for k, v in kwargs.items() if v is not None}

                log.info(kwargs)

                resp = self._client.list_objects(self.namespace, bucket_name, **kwargs)
                objects = resp.data.objects or []
                log.info(resp.data)

                for obj in objects:
                    created: Optional[datetime] = None
                    if obj.time_created:
                        # OCI returns tz-aware datetime; normalise to UTC
                        created = obj.time_created.astimezone(timezone.utc).replace(tzinfo=None)

                    # Apply date filters
                    if from_date and created and created < from_date:
                        continue
                    if to_date and created and created > to_date:
                        continue

                    all_items.append({
                        "name":          obj.name,
                        "size_bytes":    obj.size,
                        "time_created":  created.strftime("%Y-%m-%d %H:%M:%S") if created else "",
                    })

                # Pagination token from OCI
                next_start_with = resp.data.next_start_with
                if not next_start_with:
                    break

            # Sort by time_created descending (newest first)
            all_items.sort(key=lambda x: x["time_created"], reverse=True)

            total = len(all_items)
            total_pages = max(1, -(-total // page_size))  # ceil division
            start = (page - 1) * page_size
            page_items = all_items[start: start + page_size]

            log.info("Listed %d object(s) from OCI (page %d/%d).", total, page, total_pages)
            return {
                "items":       page_items,
                "total":       total,
                "page":        page,
                "page_size":   page_size,
                "total_pages": total_pages,
            }

        except oci.exceptions.ServiceError as exc:
            log.error(
                "OCI list error.\n  HTTP STATUS : %s | CODE : %s | MESSAGE : %s",
                exc.status, exc.code, exc.message,
            )
            raise
        except Exception as exc:
            log.error("Unexpected error listing OCI objects: %s", exc)
            raise

    def get_object_content(self, object_name: str) -> bytes:
        """
        Download and return the raw bytes of an object from OCI.

        Args:
            object_name: The OCI object key.

        Returns:
            Raw bytes of the object content.

        Raises:
            oci.exceptions.ServiceError: On OCI API errors.
        """
        _, bucket_name = _get_storage_config()
        log.info("Fetching object '%s' from bucket '%s' …", object_name, bucket_name)
        try:
            resp = self._client.get_object(self.namespace, bucket_name, object_name)
            content = resp.data.content
            log.info("Fetched '%s' (%d bytes).", object_name, len(content))
            return content
        except oci.exceptions.ServiceError as exc:
            log.error(
                "OCI get_object error for '%s'.\n  HTTP STATUS : %s | CODE : %s | MESSAGE : %s",
                object_name, exc.status, exc.code, exc.message,
            )
            raise
        except Exception as exc:
            log.error("Unexpected error fetching '%s': %s", object_name, exc)
            raise
