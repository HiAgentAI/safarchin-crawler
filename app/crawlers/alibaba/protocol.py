"""
Two-phase search protocol for Alibaba.

Alibaba splits every availability search into two round trips:

1. ``POST`` the search criteria. The response is **not** a result set - it
   carries only a handle.
2. ``GET`` ``<criteria-url>/<handle>``. This returns the actual results.

Flights return an opaque ``requestId``; trains return a base64-encoded echo of
the criteria. Both are the same protocol with a different handle encoding, so
one helper owns the whole exchange.

Both endpoints answer with an ASP.NET-style envelope on failure, which must
surface as an error rather than as an empty result set.
"""

import asyncio
import logging
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)


class AlibabaSearchError(RuntimeError):
    """Raised when an Alibaba search cannot be completed."""


async def _as_dict(response: Any) -> Dict[str, Any]:
    """
    Extract a JSON body from an HTTP response or an already-decoded dict.

    ``.json()`` is normally synchronous, but the rest of this codebase already
    tolerates clients that expose it as a coroutine, so both are accepted.
    """
    data = response.json() if hasattr(response, "json") else response
    if asyncio.iscoroutine(data):
        data = await data
    return data if isinstance(data, dict) else {}


def provider_error_message(body: Dict[str, Any]) -> Optional[str]:
    """
    Return a human-readable error from an Alibaba envelope, or None if it is fine.

    Alibaba fronts more than one backend stack, so two failure shapes exist:
    an ASP.NET-style ``{"success": false, "error": {...}}`` and a Go-style
    ``{"status": "error", "message": "..."}``.
    """
    if not isinstance(body, dict):
        return None

    if body.get("unauthorizedRequest"):
        return "Alibaba rejected the request as unauthorized"

    error = body.get("error")
    if isinstance(error, dict):
        message = error.get("message") or error.get("serviceMessage")
        if message:
            details = error.get("details")
            return f"{message} (details: {details})" if details else str(message)

    if body.get("success") is False:
        return "Alibaba reported the search as unsuccessful"

    if body.get("status") == "error" and body.get("message"):
        return str(body["message"])

    return None


def extract_request_id(body: Dict[str, Any]) -> Optional[str]:
    """Flights return ``result.requestId``."""
    result = body.get("result")
    if isinstance(result, dict):
        handle = result.get("requestId")
        return str(handle) if handle else None
    return None


def extract_encoded_handle(body: Dict[str, Any]) -> Optional[str]:
    """Trains return ``result`` as a base64-encoded criteria echo."""
    result = body.get("result")
    if isinstance(result, str) and result:
        return result
    return None


async def two_phase_search(
    client,
    url: str,
    payload: Dict[str, Any],
    extract_handle: Callable[[Dict[str, Any]], Optional[str]] = extract_request_id,
) -> Dict[str, Any]:
    """
    Run an Alibaba two-phase search and return the phase-two body.

    Raises :class:`AlibabaSearchError` when the criteria request is rejected, no
    handle comes back, or the result set cannot be retrieved. It never returns an
    empty result set to signal failure.
    """
    try:
        criteria_response = await client.post(url, json_data=payload)
    except Exception as exc:
        raise AlibabaSearchError(f"Alibaba criteria request failed for {url}: {exc}") from exc

    criteria_body = await _as_dict(criteria_response)

    error = provider_error_message(criteria_body)
    if error:
        raise AlibabaSearchError(f"Alibaba rejected the search: {error}")

    handle = extract_handle(criteria_body)
    if not handle:
        # A successful response with no handle means we cannot retrieve results.
        # Treating this as "no results" would silently hide an unavailable service.
        raise AlibabaSearchError(
            f"Alibaba returned no search handle for {url}; results are not retrievable"
        )

    try:
        result_response = await client.get(f"{url}/{handle}")
    except Exception as exc:
        raise AlibabaSearchError(
            f"Alibaba result retrieval failed for handle {handle[:32]}: {exc}"
        ) from exc

    return await _as_dict(result_response)