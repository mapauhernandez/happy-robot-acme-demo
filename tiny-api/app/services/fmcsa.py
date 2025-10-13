from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, Optional

import httpx


class CarrierLookupError(Exception):
    """Base exception for FMCSA lookup failures."""


class CarrierNotFoundError(CarrierLookupError):
    """Raised when a carrier cannot be located for a docket number."""


class FmcsaServiceError(CarrierLookupError):
    """Raised when the FMCSA service cannot be reached or returns bad data."""


@dataclass
class CarrierRecord:
    mc: str
    dot_number: Optional[str]
    carrier_name: Optional[str]
    authority_status: Optional[str]
    eligible: bool


def _extract_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
    else:
        text = str(value).strip()
    return text or None


def _expand_status_code(code: Optional[str]) -> Optional[str]:
    extracted = _extract_str(code)
    if not extracted:
        return None
    normalized = extracted.lower()
    mapping = {
        "a": "Active",
        "i": "Inactive",
        "n": "Inactive",
        "o": "Out of Service",
        "s": "Suspended",
        "v": "Inactive (voluntary)",
        "p": "Pending",
        "r": "Revoked",
    }
    return mapping.get(normalized, extracted)


def _interpret_allowed_flag(value: Optional[str]) -> Optional[str]:
    extracted = _extract_str(value)
    if not extracted:
        return None
    normalized = extracted.lower()
    truthy = {"y", "yes", "true", "1"}
    falsy = {"n", "no", "false", "0"}
    if normalized in truthy:
        return "Allowed to operate"
    if normalized in falsy:
        return "Not allowed to operate"
    return f"Allowed to operate: {extracted}"


def _status_text_indicates_active(status: Optional[str]) -> bool:
    if not status:
        return False
    normalized = status.lower()
    if "inactive" in normalized or "revoked" in normalized:
        return False
    if "not" in normalized and "authorized" in normalized:
        return False
    return "active" in normalized or "authorized" in normalized or "allowed" in normalized


def _normalize_authority_status(carrier: Dict[str, Any]) -> Optional[str]:
    fragments = []

    descriptive_fields = [
        carrier.get("operatingStatus"),
        carrier.get("authorityStatus"),
        carrier.get("authorityDescription"),
        carrier.get("operatingStatusDesc"),
    ]
    for field in descriptive_fields:
        extracted = _extract_str(field)
        if extracted:
            fragments.append(extracted)
            break

    code_fields = [
        ("Status", carrier.get("statusCode")),
        ("Common", carrier.get("commonAuthorityStatus")),
        ("Contract", carrier.get("contractAuthorityStatus")),
        ("Broker", carrier.get("brokerAuthorityStatus")),
    ]
    for label, value in code_fields:
        expanded = _expand_status_code(value)
        if expanded:
            fragments.append(f"{label}: {expanded}")

    allowed_fragment = _interpret_allowed_flag(carrier.get("allowedToOperate"))
    if allowed_fragment:
        fragments.append(allowed_fragment)

    unique_fragments: list[str] = []
    for fragment in fragments:
        if fragment and fragment not in unique_fragments:
            unique_fragments.append(fragment)

    return "; ".join(unique_fragments) or None


def _determine_eligibility(carrier: Dict[str, Any], status_text: Optional[str]) -> bool:
    if _status_text_indicates_active(status_text):
        return True

    allowed_flag = _extract_str(carrier.get("allowedToOperate"))
    if allowed_flag and allowed_flag.lower() in {"y", "yes", "true", "1"}:
        return True

    status_codes = [
        carrier.get("statusCode"),
        carrier.get("commonAuthorityStatus"),
        carrier.get("contractAuthorityStatus"),
        carrier.get("brokerAuthorityStatus"),
    ]
    for code in status_codes:
        extracted = _extract_str(code)
        if not extracted:
            continue
        normalized = extracted.lower()
        if normalized.startswith("a") or normalized == "yes":
            return True
        if normalized.startswith("i") or normalized.startswith("r") or normalized.startswith("s"):
            return False

    return False


def _looks_like_carrier_block(candidate: Dict[str, Any]) -> bool:
    keys = {str(key).lower() for key in candidate.keys()}
    carrier_keys = {
        "usdotnumber",
        "usdornumber",
        "dotnumber",
        "legalname",
        "carriername",
        "dba",
        "operatingstatus",
        "authoritystatus",
        "authoritydescription",
        "operatingstatusdesc",
    }
    return bool(keys & carrier_keys)


def _find_carrier_block(payload: Any) -> Optional[Dict[str, Any]]:
    if isinstance(payload, dict):
        if "carrier" in payload and isinstance(payload["carrier"], dict):
            carrier = payload["carrier"]
            if carrier:
                return carrier
        if _looks_like_carrier_block(payload):
            return payload
        for value in payload.values():
            result = _find_carrier_block(value)
            if result:
                return result
    elif isinstance(payload, list):
        for item in payload:
            result = _find_carrier_block(item)
            if result:
                return result
    return None


def _parse_carrier_payload(payload: Dict[str, Any], mc: str) -> CarrierRecord:
    print("[FMCSA] Parsing carrier payload...")
    if isinstance(payload, dict):
        print(f"[FMCSA] Top-level payload keys: {list(payload.keys())}")
    carrier_block = _find_carrier_block(payload.get("content") or payload)

    if not isinstance(carrier_block, dict) or not carrier_block:
        raise CarrierNotFoundError(f"No carrier details available for MC {mc}.")

    print("[FMCSA] Carrier block located:")
    try:
        print(json.dumps(carrier_block, indent=2))
    except TypeError:
        print(carrier_block)

    dot_number = _extract_str(
        carrier_block.get("usdotNumber")
        or carrier_block.get("usDotNumber")
        or carrier_block.get("dotNumber")
        or carrier_block.get("US_DOT")
    )
    print(f"[FMCSA] Extracted DOT number: {dot_number}")
    carrier_name = _extract_str(
        carrier_block.get("legalName")
        or carrier_block.get("carrierName")
        or carrier_block.get("dbaName")
    )
    print(f"[FMCSA] Extracted carrier name: {carrier_name}")
    authority_status = _normalize_authority_status(carrier_block)
    print(f"[FMCSA] Extracted authority status: {authority_status}")

    eligible = _determine_eligibility(carrier_block, authority_status)
    print(f"[FMCSA] Eligible: {eligible}")

    return CarrierRecord(
        mc=mc,
        dot_number=dot_number,
        carrier_name=carrier_name,
        authority_status=authority_status,
        eligible=eligible,
    )


async def fetch_carrier_by_mc(mc: str, web_key: str) -> CarrierRecord:
    """Fetch carrier details from the FMCSA service by MC (docket) number."""

    if not web_key:
        raise FmcsaServiceError("FMCSA web key is not configured.")

    url = f"https://mobile.fmcsa.dot.gov/qc/services/carriers/docket-number/{mc}?webKey={web_key}"

    async with httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=5.0)) as client:
        try:
            response = await client.get(url)
        except httpx.HTTPError as exc:  # pragma: no cover - network failures
            raise FmcsaServiceError("Failed to reach FMCSA service.") from exc

    sanitized_url = url.replace(web_key, "***")
    print(f"[FMCSA] Request URL: {sanitized_url}")
    print(f"[FMCSA] Response status: {response.status_code}")

    if response.status_code == 404:
        raise CarrierNotFoundError(f"No carrier found for MC {mc}.")

    if response.status_code >= 500:
        raise FmcsaServiceError("FMCSA service returned an error.")

    try:
        data: Dict[str, Any] = response.json()
    except json.JSONDecodeError as exc:
        raise FmcsaServiceError("FMCSA response was not valid JSON.") from exc

    print("[FMCSA] Raw response JSON:")
    try:
        print(json.dumps(data, indent=2))
    except TypeError:
        print(data)

    if not response.is_success:
        raise FmcsaServiceError("FMCSA service returned an unexpected response.")

    return _parse_carrier_payload(data, mc)
