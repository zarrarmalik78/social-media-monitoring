"""Dedicated LinkedIn Collector interacting directly with LinkedIn's Voyager API."""

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


class LinkedInCollector(BaseCollector):
    """Collector for LinkedIn querying LinkedIn's native Voyager API directly using session cookies."""

    VOYAGER_BASE_URL = "https://www.linkedin.com/voyager/api"

    def __init__(self, db_path: str = "data/accounts.db", raise_when_no_account: bool = False):
        self.db_path = db_path
        self.raise_when_no_account = raise_when_no_account
        self.session_manager = SessionManager(db_path=db_path)

    async def check_status(self) -> Dict[str, Any]:
        """Check active LinkedIn session status."""
        sessions = self.session_manager.list_sessions(platform="linkedin")
        active_sessions = [s for s in sessions if s.get("active")]
        is_ready = len(active_sessions) > 0

        return {
            "platform": "linkedin",
            "ready": is_ready,
            "total_accounts": len(sessions),
            "active_accounts": len(active_sessions),
            "accounts": sessions,
        }

    async def add_account_cookies(self, account_name: str, cookies: str) -> bool:
        """Add or update a LinkedIn cookie session.
        
        Requires at least 'li_at' cookie from browser DevTools (Application -> Cookies).
        """
        clean_cookies = cookies.strip()
        if "li_at" not in clean_cookies:
            raise ValueError(
                "LinkedIn cookies must contain at least 'li_at'.\n"
                "Please copy it from linkedin.com DevTools (F12 -> Application -> Cookies -> https://www.linkedin.com)."
            )
        return self.session_manager.add_session("linkedin", account_name, clean_cookies)

    def _build_headers(self, session: Dict[str, Any]) -> Dict[str, str]:
        """Construct authentic browser headers and extract CSRF token from JSESSIONID."""
        cookie_str = session["cookies"]
        cookie_dict = SessionManager.parse_cookie_dict(cookie_str)
        
        # Extract or generate JSESSIONID for csrf-token header
        jsessionid = cookie_dict.get("JSESSIONID", "").strip('"')
        if not jsessionid:
            jsessionid = "ajax:1000000000000000000"
            cookie_str = f"{cookie_str}; JSESSIONID=\"{jsessionid}\""

        return {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
            "Accept": "application/vnd.linkedin.normalized+json+2.1",
            "csrf-token": jsessionid,
            "x-restli-protocol-version": "2.0.0",
            "x-li-lang": "en_US",
            "x-li-page-instance": "urn:li:page:d_flagship3_search_srp_content",
            "Cookie": cookie_str,
            "Referer": "https://www.linkedin.com/search/results/content/",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
        }

    def _parse_voyager_posts(self, data: Dict[str, Any], limit: int) -> List[NormalizedPost]:
        """Parse LinkedIn Voyager JSON response into NormalizedPost list."""
        posts: List[NormalizedPost] = []
        
        elements = data.get("elements", [])
        included = data.get("included", [])

        # Build an entity lookup map from 'included' if present
        entity_map = {item.get("entityUrn"): item for item in included if item.get("entityUrn")}

        for el in elements:
            try:
                # Find post items within clusters or direct results
                items = el.get("items", [el]) if "items" in el else [el]
                for item in items:
                    entity_urn = item.get("entityUrn") or item.get("urn", "")
                    entity = entity_map.get(entity_urn, item)
                    
                    # Extract text content
                    commentary = (
                        entity.get("commentary", {}).get("text", {}).get("text")
                        or entity.get("summary", {}).get("text")
                        or entity.get("text", "")
                    )
                    
                    # Fallback to title if summary/text not directly present
                    if not commentary and "title" in entity:
                        title_obj = entity.get("title")
                        if isinstance(title_obj, dict):
                            commentary = title_obj.get("text", "")
                        elif isinstance(title_obj, str):
                            commentary = title_obj

                    if not commentary:
                        continue

                    # Extract author details
                    actor = entity.get("actor", {})
                    author_name = actor.get("name", {}).get("text") if isinstance(actor.get("name"), dict) else "LinkedIn Member"
                    if not author_name or author_name == "LinkedIn Member":
                        primary_sub = entity.get("primarySubtitle", {})
                        if isinstance(primary_sub, dict) and primary_sub.get("text"):
                            author_name = primary_sub.get("text")

                    author_username = actor.get("urn", "linkedin_user").split(":")[-1]
                    
                    # Extract engagement metrics
                    social_detail = entity.get("socialDetail", {})
                    social_counts = social_detail.get("totalSocialActivityCounts", {})
                    likes = int(social_counts.get("numLikes", 0) or 0)
                    comments = int(social_counts.get("numComments", 0) or 0)
                    shares = int(social_counts.get("numShares", 0) or 0)

                    # Extract timestamp
                    created_at = datetime.now(timezone.utc)
                    posted_at = entity.get("postedAt")
                    if posted_at:
                        try:
                            created_at = datetime.fromtimestamp(posted_at / 1000.0, timezone.utc)
                        except Exception:
                            pass

                    # Clean post ID and link
                    post_id = re.sub(r'[^a-zA-Z0-9_-]', '', entity_urn) or f"li_{abs(hash(commentary))}"
                    post_url = f"https://www.linkedin.com/feed/update/{entity_urn}" if "urn:li:activity" in entity_urn else f"https://www.linkedin.com/search/results/content/?keywords={urllib.parse.quote(commentary[:30])}"

                    posts.append(NormalizedPost(
                        id=post_id,
                        platform="linkedin",
                        item_type="post",
                        text=commentary.strip(),
                        author_username=author_username,
                        author_name=author_name,
                        created_at=created_at,
                        url=post_url,
                        likes=likes,
                        replies=comments,
                        reposts=shares,
                        shares=shares,
                        comments_count=comments,
                        views=None,
                        raw_data=entity,
                    ))

                    if len(posts) >= limit:
                        return posts

            except Exception as parse_err:
                logger.debug(f"Error parsing LinkedIn item: {parse_err}")

        # Fallback: scan included entity map directly if elements didn't yield items
        if not posts:
            for entity_urn, entity in entity_map.items():
                if entity.get("$type", "").endswith("EntityResultViewModel"):
                    title_text = entity.get("title", {}).get("text", "") if isinstance(entity.get("title"), dict) else ""
                    summary_text = entity.get("summary", {}).get("text", "") if isinstance(entity.get("summary"), dict) else ""
                    primary_sub = entity.get("primarySubtitle", {}).get("text", "") if isinstance(entity.get("primarySubtitle"), dict) else ""
                    
                    full_text = f"{title_text}\n{summary_text}".strip()
                    if not full_text:
                        continue

                    post_id = re.sub(r'[^a-zA-Z0-9_-]', '', entity_urn) or f"li_{abs(hash(full_text))}"
                    post_url = f"https://www.linkedin.com/search/results/all/?keywords={urllib.parse.quote(title_text or summary_text[:30])}"

                    posts.append(NormalizedPost(
                        id=post_id,
                        platform="linkedin",
                        item_type="post",
                        text=full_text,
                        author_username="linkedin_search",
                        author_name=primary_sub or title_text or "LinkedIn Entity",
                        created_at=datetime.now(timezone.utc),
                        url=post_url,
                        likes=0,
                        replies=0,
                        reposts=0,
                        shares=0,
                        comments_count=0,
                        views=None,
                        raw_data=entity,
                    ))

                    if len(posts) >= limit:
                        return posts

        return posts

    async def search(
        self,
        query: str,
        limit: int = 20,
        **kwargs: Any
    ) -> List[NormalizedPost]:
        """Search LinkedIn directly for public posts matching query.
        
        Args:
            query: The search term (e.g. "COMSATS", "NUST", "internship").
            limit: Maximum number of posts to retrieve.
        """
        clean_query = query.strip()
        if not clean_query:
            return []

        # 1. Retrieve active session
        session = self.session_manager.get_active_session("linkedin")
        if not session:
            msg = (
                "No active LinkedIn session found in pool.\n"
                "To search LinkedIn, please add an active session cookie:\n"
                "  1. Log into linkedin.com in your browser.\n"
                "  2. Open DevTools (F12) -> Application -> Cookies -> https://www.linkedin.com\n"
                "  3. Copy 'li_at' value.\n"
                "  4. Add via CLI: python run_cli.py add-cookie --platform linkedin <name> \"li_at=...\"\n"
                "     or via the Web UI Accounts tab."
            )
            if self.raise_when_no_account:
                raise NoAccountError(msg)
            else:
                logger.warning(msg)
                return []

        # 2. Query LinkedIn Voyager API
        headers = self._build_headers(session)
        encoded_query = urllib.parse.quote(clean_query)
        
        # Primary search endpoint for content/posts
        url = (
            f"{self.VOYAGER_BASE_URL}/search/dash/clusters?"
            f"decorationId=com.linkedin.voyager.dash.deco.search.SearchClusterCollection-174&"
            f"origin=GLOBAL_SEARCH_HEADER&q=all&"
            f"query=(keywords:{encoded_query},flagshipSearchIntent:SEARCH_SRP)"
        )

        try:
            async with httpx.AsyncClient(headers=headers, timeout=15.0, follow_redirects=True) as client:
                resp = await client.get(url)

                if resp.status_code == 429:
                    raise RateLimitError("LinkedIn rate limit reached. Please wait before retrying.")
                elif resp.status_code in (401, 403) or "/login" in str(resp.url):
                    self.session_manager.mark_error("linkedin", session["account_name"], "Session expired (HTTP 401/403)", deactivate=True)
                    raise AuthError("LinkedIn session expired. Please refresh your 'li_at' cookie.")
                elif resp.status_code != 200:
                    logger.warning(f"LinkedIn Voyager returned HTTP {resp.status_code}: {resp.text[:200]}")
                    return []

                data = resp.json()
                return self._parse_voyager_posts(data, limit=limit)

        except (NoAccountError, AuthError, RateLimitError):
            raise
        except httpx.RequestError as e:
            raise NetworkError(f"Network error while reaching LinkedIn: {e}") from e
        except Exception as e:
            raise CollectorError(f"Error searching LinkedIn for '{clean_query}': {e}") from e
