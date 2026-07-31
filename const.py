"""Constants for the Afore integration."""
from __future__ import annotations

from datetime import timedelta
import logging
from typing import Final

from homeassistant.const import Platform

DOMAIN: Final = "afore3"
PLATFORMS = [Platform.SENSOR]

LOGGER = logging.getLogger(__package__)
SCAN_INTERVAL = timedelta(minutes=10)

# --- OAuth2 token refresh -------------------------------------------------
# The Afore portal issues a short-lived access token (now ~daily) plus a
# long-lived refresh token (~6 months). We store the refresh token and mint a
# new access token automatically, so the captcha login is only needed ~twice a
# year (when the refresh token itself expires).
CONF_REFRESH_TOKEN: Final = "refresh_token"

# Confirmed from a live capture (2026-07-30): the portal's OAuth2 token endpoint
# authenticates the client via a "client_id" form field only — no client secret,
# no Basic auth header. A refresh_token grant returns a fresh ~24h access token.
OAUTH_TOKEN_URL: Final = "/oauth2-s/oauth/token"
OAUTH_CLIENT_ID: Final = "test"

# Refresh the access token this long before it actually expires.
TOKEN_REFRESH_MARGIN = timedelta(minutes=15)

# Persistent-notification id shown when the refresh token is dead and a manual
# re-login is required (so token failures are loud, not silent gaps).
NOTIFY_REAUTH_ID: Final = "afore3_reauth_required"
