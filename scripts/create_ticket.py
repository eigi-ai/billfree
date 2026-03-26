#!/usr/bin/env python3
"""
BillFree Ticket Creator — Create a support ticket via the BF-TKT API.

Endpoint: POST https://script.google.com/macros/s/AKfycbwJcHg5ToptJlv2OV4r3eCdOnmtzh0HC-ahvBmriI5OsnNo1eB5_PxuZGrli83Fz0s6Mw/exec
Auth: apiKey field in request body (from BF_API_KEY env var)

Uses only Python stdlib — no external dependencies.

Usage:
    python3 create_ticket.py --concern "POS not working"
    python3 create_ticket.py --concern "POS not working" --phone "9876543210"
    python3 create_ticket.py --concern "POS not working" --phone "9876543210" --name "John" --mid "123456" --business "ABC Store" --pos "Terminal-01"
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
import urllib.error

API_URL = (
    "https://script.google.com/macros/s/"
    "AKfycbwJcHg5ToptJlv2OV4r3eCdOnmtzh0HC-ahvBmriI5OsnNo1eB5_PxuZGrli83Fz0s6Mw/exec"
)


# -- Friendly error messages keyed by API error code --
_ERROR_MESSAGES = {
    "E001": "It looks like this ticket was already submitted recently, or we've hit the rate limit. Please wait about a minute and try again.",
    "E002": "The BillFree API key is invalid. Please check the configuration and update the key.",
    "E004": "Some of the information provided isn't quite right — {detail}. Could you double-check and try again?",
    "E006": "The BillFree server is a bit busy right now. Hang tight — I'll retry in a few seconds.",
    "E999": "Something went wrong on BillFree's end. Please contact BillFree support if this persists.",
}


def _friendly_error(code: str, detail: str, request_id: str) -> str:
    """Return a natural-language error message for the user."""
    template = _ERROR_MESSAGES.get(code, "")
    if template:
        msg = template.format(detail=detail) if "{detail}" in template else template
    else:
        msg = (
            f'I wasn\'t able to create the ticket. The server said: "{detail}"'
            if detail
            else "I wasn't able to create the ticket due to an unexpected error. Please try again."
        )
    if request_id:
        msg += f"\n\n(Reference ID: {request_id} — share this with BillFree support if needed.)"
    return msg


def get_api_key() -> str:
    key = os.environ.get("BF_API_KEY", "").strip()
    if not key:
        print(
            "The BillFree API key (BF_API_KEY) is not configured. "
            "Please set it up before creating tickets."
        )
        sys.exit(1)
    return key


def create_ticket(
    concern: str,
    phone: str | None,
    name: str | None,
    mid: str | None,
    business: str | None,
    pos: str | None,
) -> int:
    api_key = get_api_key()

    body: dict = {
        "action": "createTicket",
        "apiKey": api_key,
        "concern": concern,
    }
    if phone:
        body["phone"] = phone
    if name:
        body["requestedBy"] = name
    if mid:
        body["mid"] = mid
    if business:
        body["business"] = business
    if pos:
        body["pos"] = pos

    data = json.dumps(body).encode("utf-8")

    req = urllib.request.Request(
        API_URL,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        # GAS redirects once — urllib follows redirects by default for GET,
        # but for POST we need a custom handler to follow the redirect.
        opener = urllib.request.build_opener(_RedirectHandler)
        resp = opener.open(req, timeout=30)
        result = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        try:
            err = json.loads(error_body)
            print(
                _friendly_error(
                    err.get("code", ""), err.get("error", ""), err.get("requestId", "")
                )
            )
        except json.JSONDecodeError:
            print(
                "I wasn't able to create the ticket because the BillFree server returned an unexpected response. Please try again in a moment."
            )
        return 1
    except urllib.error.URLError:
        print(
            "I couldn't reach the BillFree server right now. This is likely a temporary network issue — please try again shortly."
        )
        return 1

    if result.get("success"):
        ticket_data = result.get("data", {})
        ticket_id = ticket_data.get("ticketId", "unknown")
        agent = ticket_data.get("assignedAgent", "unknown")
        status = ticket_data.get("status", "unknown")
        request_id = ticket_data.get("requestId", "")

        print(
            f"Your ticket **{ticket_id}** has been created successfully. "
            f"Our agent **{agent}** has been assigned and will contact you shortly."
        )
        if request_id:
            print(f"\n(Reference ID: {request_id})")
        return 0
    else:
        code = result.get("code", "")
        msg = result.get("error", "")
        request_id = result.get("requestId", "")
        print(_friendly_error(code, msg, request_id))
        return 1


class _RedirectHandler(urllib.request.HTTPRedirectHandler):
    """Follow redirects for POST requests (GAS returns a 302)."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # On redirect, switch to GET (standard browser behavior for 302).
        new_req = urllib.request.Request(
            newurl,
            headers={"Content-Type": "application/json"},
            method="GET",
        )
        return new_req


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="create_ticket",
        description="Create a BillFree support ticket via the BF-TKT API.",
    )
    parser.add_argument(
        "--concern", required=True, help="Issue description (max 500 chars)"
    )
    parser.add_argument("--phone", default=None, help="Customer phone number")
    parser.add_argument("--name", default=None, help="Customer name")
    parser.add_argument("--mid", default=None, help="Merchant ID (numeric)")
    parser.add_argument(
        "--business", default=None, help="Business name (max 200 chars)"
    )
    parser.add_argument("--pos", default=None, help="POS terminal ID (max 50 chars)")

    args = parser.parse_args()
    return create_ticket(
        args.concern, args.phone, args.name, args.mid, args.business, args.pos
    )


if __name__ == "__main__":
    raise SystemExit(main())
