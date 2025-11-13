import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import httpx

from .utils_time import ensure_iso8601

logger = logging.getLogger("bluesky_parser")

@dataclass
class BlueskyFollowerClient:
    base_url: str = "https://public.api.bsky.app"
    timeout_seconds: int = 15
    max_page_size: int = 100

    def _build_client(self) -> httpx.Client:
        return httpx.Client(
            base_url=self.base_url,
            timeout=self.timeout_seconds,
            headers={
                "User-Agent": "Bitbash-BlueskyFollowersScraper/1.0",
                "Accept": "application/json",
            },
        )

    @staticmethod
    def _is_did(identifier: str) -> bool:
        return identifier.startswith("did:")  # Simple heuristic

    @staticmethod
    def _build_profile_link(did: Optional[str], handle: Optional[str]) -> Optional[str]:
        if handle:
            return f"https://bsky.app/profile/{handle}"
        if did:
            return f"https://bsky.app/profile/{did}"
        return None

    @staticmethod
    def _normalize_follower(raw: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert a raw Bluesky follower record into a clean, analytics-ready structure.
        """
        did = raw.get("did")
        handle = raw.get("handle")
        display_name = raw.get("displayName")
        avatar = raw.get("avatar")
        created_at = ensure_iso8601(raw.get("createdAt"))
        description = raw.get("description") or raw.get("bio")
        labels = raw.get("labels") or []
        associated = raw.get("associated") or {}

        follower: Dict[str, Any] = {
            "did": did,
            "handle": handle,
            "displayName": display_name,
            "avatar": avatar,
            "createdAt": created_at,
            "description": description,
            "labels": labels,
            "associated": associated,
            "link_to_profile": BlueskyFollowerClient._build_profile_link(did, handle),
        }

        # Preserve other fields from the raw payload for completeness
        for key, value in raw.items():
            if key not in follower:
                follower[key] = value

        return follower

    def fetch_followers(self, actor: str, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Fetch followers for a given actor (handle or DID) using the public Bluesky API.

        This method:
            - Paginates through the followers list using the 'cursor' parameter.
            - Normalizes each follower into a consistent structure.
            - Stops when 'limit' followers have been collected or there is no more data.
        """
        if limit <= 0:
            raise ValueError("limit must be a positive integer")

        logger.debug("Starting follower fetch for actor '%s' with limit=%d", actor, limit)
        followers: List[Dict[str, Any]] = []
        remaining = limit
        cursor: Optional[str] = None

        with self._build_client() as client:
            while remaining > 0:
                page_size = min(self.max_page_size, remaining)
                params: Dict[str, Any] = {"actor": actor, "limit": page_size}
                if cursor:
                    params["cursor"] = cursor

                try:
                    response = client.get("/xrpc/app.bsky.graph.getFollowers", params=params)
                    response.raise_for_status()
                except httpx.HTTPError as exc:
                    logger.error("HTTP error while fetching followers for '%s': %s", actor, exc)
                    break

                try:
                    payload = response.json()
                except ValueError as exc:
                    logger.error("Failed to decode JSON response for '%s': %s", actor, exc)
                    break

                page_followers = payload.get("followers", [])
                if not isinstance(page_followers, list):
                    logger.error("Unexpected payload format: 'followers' is not a list")
                    break

                if not page_followers:
                    logger.info("No more followers returned for '%s'.", actor)
                    break

                for raw in page_followers:
                    normal = self._normalize_follower(raw)
                    followers.append(normal)
                    remaining -= 1
                    if remaining <= 0:
                        break

                cursor = payload.get("cursor")
                if not cursor:
                    logger.info("Reached end of follower list for '%s'.", actor)
                    break

                logger.debug(
                    "Fetched %d followers so far for '%s', cursor=%s",
                    len(followers),
                    actor,
                    cursor,
                )

        return followers