"""Dedicated Instagram Collector querying Instagram's native Web API directly using session cookies."""

import re
import json
import logging
import urllib.parse
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import httpx

from app.models.post import NormalizedPost
from app.collectors.base import (
    BaseCollector,
    CollectorError,
    NoAccountError,
    AuthError,
    RateLimitError,
    NetworkError,
)
from app.utils.session_manager import SessionManager

logger = logging.getLogger(__name__)


class InstagramCollector(BaseCollector):
    """Collector for Instagram querying Instagram's native Web API directly using session cookies."""

    IG_APP_ID = "936619743392459"
    TAG_URL = "https://www.instagram.com/api/v1/tags/web_info/"
    SEARCH_URL = "https://www.instagram.com/api/v1/fbsearch/topsearch_flat/"

    def __init__(self, db_path: str = "data/accounts.db", raise_when_no_account: bool = False):
        self.db_path = db_path
        self.raise_when_no_account = raise_when_no_account
        self.session_manager = SessionManager(db_path=db_path)

    async def check_status(self) -> Dict[str, Any]:
        """Check active Instagram session status."""
        sessions = self.session_manager.list_sessions(platform="instagram")
        active_sessions = [s for s in sessions if s.get("active")]
        is_ready = len(active_sessions) > 0

        return {
            "platform": "instagram",
            "ready": is_ready,
            "total_accounts": len(sessions),
            "active_accounts": len(active_sessions),
            "accounts": sessions,
        }

    async def add_account_cookies(self, account_name: str, cookies: str) -> bool:
        """Add or update an Instagram cookie session.
        
        Requires at least 'sessionid' from browser DevTools (Application -> Cookies).
        """
        clean_cookies = cookies.strip()
        if "sessionid" not in clean_cookies:
            raise ValueError(
                "Instagram cookies must contain at least 'sessionid'.\n"
                "Please copy it from instagram.com DevTools (F12 -> Application -> Cookies -> https://www.instagram.com)."
            )
        return self.session_manager.add_session("instagram", account_name, clean_cookies)

    def _build_headers(self, session: Dict[str, Any]) -> Dict[str, str]:
        """Construct authentic Instagram web app headers."""
        cookie_str = session["cookies"]
        cookie_dict = SessionManager.parse_cookie_dict(cookie_str)
        csrf_token = cookie_dict.get("csrftoken", "")

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
            "X-IG-App-ID": self.IG_APP_ID,
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Cookie": cookie_str,
            "Referer": "https://www.instagram.com/",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
        }
        if csrf_token:
            headers["X-CSRFToken"] = csrf_token
        return headers

    def _extract_media_objects(self, obj: Any) -> List[Dict[str, Any]]:
        """Recursively extract all media items from Instagram response payload tree."""
        media_items = []
        if isinstance(obj, dict):
            if "media" in obj and isinstance(obj["media"], dict):
                media_items.append(obj["media"])
            for v in obj.values():
                media_items.extend(self._extract_media_objects(v))
        elif isinstance(obj, list):
            for item in obj:
                media_items.extend(self._extract_media_objects(item))
        return media_items

    def _parse_media_items(self, items: List[Dict[str, Any]], limit: int) -> List[NormalizedPost]:
        """Parse Instagram media items into NormalizedPost objects."""
        posts: List[NormalizedPost] = []

        for item in items:
            try:
                # Resolve media or node wrapper
                media = item.get("media") or item.get("node") or item

                code = media.get("code") or media.get("shortcode")
                media_id = str(media.get("id") or code or f"ig_{abs(hash(str(media)))}")
                
                # Caption
                caption = ""
                caption_obj = media.get("caption")
                if isinstance(caption_obj, dict):
                    caption = caption_obj.get("text", "")
                elif isinstance(caption_obj, str):
                    caption = caption_obj
                elif "edge_media_to_caption" in media:
                    edges = media.get("edge_media_to_caption", {}).get("edges", [])
                    if edges:
                        caption = edges[0].get("node", {}).get("text", "")

                if not caption:
                    continue

                # User
                user = media.get("user") or media.get("owner", {})
                username = user.get("username", "instagram_user")
                full_name = user.get("full_name", username)

                # Engagement metrics
                likes = int(media.get("like_count", 0) or media.get("edge_media_preview_like", {}).get("count", 0) or 0)
                comments = int(media.get("comment_count", 0) or media.get("edge_media_to_comment", {}).get("count", 0) or 0)
                views = media.get("view_count") or media.get("play_count")
                if views is not None:
                    try:
                        views = int(views)
                    except Exception:
                        views = None

                # Timestamp
                created_at = datetime.now(timezone.utc)
                ts = media.get("taken_at") or media.get("taken_at_timestamp")
                if ts:
                    try:
                        created_at = datetime.fromtimestamp(ts, timezone.utc)
                    except Exception:
                        pass

                post_url = f"https://www.instagram.com/p/{code}/" if code else f"https://www.instagram.com/{username}/"

                posts.append(NormalizedPost(
                    id=media_id,
                    platform="instagram",
                    item_type="post",
                    text=caption.strip(),
                    author_username=username,
                    author_name=full_name,
                    created_at=created_at,
                    url=post_url,
                    likes=likes,
                    replies=comments,
                    reposts=0,
                    shares=0,
                    comments_count=comments,
                    views=views,
                    raw_data={"id": media_id, "code": code},
                ))

                if len(posts) >= limit:
                    return posts

            except Exception as e:
                logger.debug(f"Error parsing Instagram item: {e}")

        return posts

    async def search(
        self,
        query: str,
        limit: int = 20,
        **kwargs: Any
    ) -> List[NormalizedPost]:
        """Search Instagram directly for public posts matching query.
        
        Args:
            query: The search term (e.g. "COMSATS", "NUST").
            limit: Maximum number of posts to retrieve.
        """
        clean_query = query.strip()
        if not clean_query:
            return []

        # 1. Check session readiness
        session = self.session_manager.get_active_session("instagram")
        if not session:
            msg = (
                "No active Instagram session found in pool.\n"
                "To search Instagram, please add an active session cookie:\n"
                "  1. Log into instagram.com in your browser.\n"
                "  2. Open DevTools (F12) -> Application -> Cookies -> https://www.instagram.com\n"
                "  3. Copy 'sessionid' value.\n"
                "  4. Add via CLI: python run_cli.py add-cookie --platform instagram <name> \"sessionid=...\"\n"
                "     or via the Web UI Accounts tab."
            )
            if self.raise_when_no_account:
                raise NoAccountError(msg)
            else:
                logger.warning(msg)
                return []

        # 2. Query Instagram directly (Primary: Tag endpoint, Secondary: topsearch)
        headers = self._build_headers(session)
        clean_tag = re.sub(r'[^a-zA-Z0-9_]', '', clean_query.lower())

        try:
            async with httpx.AsyncClient(headers=headers, timeout=15.0, follow_redirects=True) as client:
                # Try tag endpoint first if clean tag exists
                if clean_tag:
                    tag_url = f"{self.TAG_URL}?tag_name={clean_tag}"
                    resp = await client.get(tag_url)

                    if resp.status_code == 429:
                        raise RateLimitError("Instagram rate limit reached. Please wait before retrying.")
                    elif resp.status_code in (401, 403) or "login" in str(resp.url):
                        self.session_manager.mark_error("instagram", session["account_name"], "Session expired (HTTP 401/403)", deactivate=True)
                        raise AuthError("Instagram session expired. Please refresh your 'sessionid' cookie.")

                    if resp.status_code == 200:
                        data = resp.json()
                        items = self._extract_media_objects(data)
                        if items:
                            return self._parse_media_items(items, limit=limit)

                # Fallback to topsearch
                search_url = f"{self.SEARCH_URL}?query={urllib.parse.quote(clean_query)}&context=blended"
                resp = await client.get(search_url)
                if resp.status_code == 200:
                    data = resp.json()
                    users = data.get("users", [])
                    # If users found, return profile cards
                    posts = []
                    for u in users[:limit]:
                        user_obj = u.get("user", {})
                        uname = user_obj.get("username", "")
                        fname = user_obj.get("full_name", uname)
                        bio = user_obj.get("biography", "") or f"Instagram profile for {fname}"
                        posts.append(NormalizedPost(
                            id=f"ig_user_{user_obj.get('pk', uname)}",
                            platform="instagram",
                            item_type="post",
                            text=f"{fname} (@{uname}): {bio}",
                            author_username=uname,
                            author_name=fname,
                            created_at=datetime.now(timezone.utc),
                            url=f"https://www.instagram.com/{uname}/",
                            likes=int(user_obj.get("follower_count", 0) or 0),
                            replies=0,
                            reposts=0,
                            shares=0,
                            comments_count=0,
                            views=None,
                            raw_data=user_obj,
                        ))
                    return posts

                return []

        except (NoAccountError, AuthError, RateLimitError):
            raise
        except httpx.RequestError as e:
            raise NetworkError(f"Network error while reaching Instagram: {e}") from e
        except Exception as e:
            raise CollectorError(f"Error searching Instagram for '{clean_query}': {e}") from e
