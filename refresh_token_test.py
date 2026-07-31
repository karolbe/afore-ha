#!/usr/bin/env python3
"""Standalone check of the Afore OAuth refresh flow - no Home Assistant needed.

The portal endpoint and client auth are known (confirmed 2026-07-30):
  endpoint : /oauth2-s/oauth/token
  client   : client_id=test in the form body (no secret, no Basic auth)

    python3 refresh_token_test.py --refresh-token "<your refresh JWT>"

On success it prints the new access token, its expiry, and any rotated refresh
token. This same call is what a daily cron would run to keep tokens fresh.
"""
import argparse
import base64
import datetime
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://hom.aforenergy.com"
DEFAULT_URL = "/oauth2-s/oauth/token"
DEFAULT_CLIENT_ID = "test"


def decode_exp(jwt: str) -> str:
    try:
        p = jwt.split(".")[1]
        p += "=" * (-len(p) % 4)
        payload = json.loads(base64.urlsafe_b64decode(p))
        return datetime.datetime.utcfromtimestamp(payload["exp"]).strftime("%Y-%m-%d %H:%M UTC")
    except Exception:
        return "?"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh-token", required=True)
    ap.add_argument("--url", default=DEFAULT_URL)
    ap.add_argument("--client-id", default=DEFAULT_CLIENT_ID)
    args = ap.parse_args()

    body = urllib.parse.urlencode({
        "grant_type": "refresh_token",
        "refresh_token": args.refresh_token,
        "client_id": args.client_id,
    }).encode()

    req = urllib.request.Request(
        BASE + args.url,
        data=body,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0",
            "Origin": BASE,
            "Referer": BASE + "/login",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            payload = json.loads(r.read())
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read().decode()[:400]}", file=sys.stderr)
        sys.exit(1)

    access = payload.get("access_token", "")
    refresh = payload.get("refresh_token")
    print("SUCCESS")
    print("  access_token expiry :", decode_exp(access))
    print("  refresh in response :", "yes -> exp " + decode_exp(refresh) if refresh else "no (reuse existing)")
    print("  expires_in          :", payload.get("expires_in"))
    print("  raw keys            :", list(payload.keys()))


if __name__ == "__main__":
    main()
