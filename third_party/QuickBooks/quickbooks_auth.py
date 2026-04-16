"""
QuickBooks Online OAuth2 authentication helpers.

QuickBooks Online uses OAuth 2.0. This module handles token refresh
so the MCP server can maintain a valid access token across requests.

Setup:
  1. Create an app at https://developer.intuit.com
  2. Obtain client_id, client_secret, and an initial refresh_token
     via the OAuth 2.0 playground or your own auth flow.
  3. Provide these via environment variables (see .env.example).
"""

import os
import time
from dataclasses import dataclass, field

import httpx

INTUIT_TOKEN_URL = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"


@dataclass
class QuickBooksAuth:
    """Manages OAuth2 tokens for QuickBooks Online API."""

    client_id: str
    client_secret: str
    refresh_token: str
    access_token: str = ""
    token_expiry: float = 0.0
    redirect_uri: str = "https://developer.intuit.com/v2/OAuth2Playground/RedirectUrl"
    _http: httpx.AsyncClient = field(default_factory=httpx.AsyncClient, repr=False)

    @classmethod
    def from_env(cls) -> "QuickBooksAuth":
        """Create an auth instance from environment variables."""
        client_id = os.environ.get("QB_CLIENT_ID", "")
        client_secret = os.environ.get("QB_CLIENT_SECRET", "")
        refresh_token = os.environ.get("QB_REFRESH_TOKEN", "")
        access_token = os.environ.get("QB_ACCESS_TOKEN", "")

        if not client_id or not client_secret:
            raise ValueError(
                "QB_CLIENT_ID and QB_CLIENT_SECRET environment variables are required. "
                "Create an app at https://developer.intuit.com to obtain these."
            )
        if not refresh_token and not access_token:
            raise ValueError(
                "Either QB_REFRESH_TOKEN or QB_ACCESS_TOKEN must be set. "
                "Use the Intuit OAuth 2.0 Playground to obtain tokens."
            )

        return cls(
            client_id=client_id,
            client_secret=client_secret,
            refresh_token=refresh_token,
            access_token=access_token,
        )

    async def get_access_token(self) -> str:
        """Return a valid access token, refreshing if needed."""
        if self.access_token and time.time() < self.token_expiry - 60:
            return self.access_token
        if self.refresh_token:
            await self._refresh()
        return self.access_token

    async def _refresh(self) -> None:
        """Exchange the refresh token for a new access + refresh token pair."""
        resp = await self._http.post(
            INTUIT_TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": self.refresh_token,
            },
            auth=(self.client_id, self.client_secret),
            headers={"Accept": "application/json"},
        )
        resp.raise_for_status()
        data = resp.json()
        self.access_token = data["access_token"]
        self.refresh_token = data.get("refresh_token", self.refresh_token)
        self.token_expiry = time.time() + data.get("expires_in", 3600)

    async def close(self) -> None:
        await self._http.aclose()
