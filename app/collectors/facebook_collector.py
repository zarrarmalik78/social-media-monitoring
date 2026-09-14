"""Dedicated Facebook / Meta Collector querying Facebook search directly using session cookies."""

import re
import json
import logging
import urllib.parse
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from bs4 import BeautifulSoup
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


class FacebookCollector(BaseCollector):
    """Collector for Facebook querying Facebook's native post search directly using session cookies."""

    SEARCH_URL = "https://www.facebook.com/search/posts/"

    def __init__(self, db_path: str = "data/accounts.db", raise_when_no_account: bool = False):
        self.db_path = db_path
        self.raise_when_no_account = raise_when_no_account
        self.session_manager = SessionManager(db_path=db_path)

    async def check_status(self) -> Dict[str, Any]:
        """Check active Facebook session status."""
        sessions = self.session_manager.list_sessions(platform="facebook")
        active_sessions = [s for s in sessions if s.get("active")]
        is_ready = len(active_sessions) > 0

        return {
            "platform": "facebook",
            "ready": is_ready,
            "total_accounts": len(sessions),
            "active_accounts": len(active_sessions),
            "accounts": sessions,
        }

    async def add_account_cookies(self, account_name: str, cookies: str) -> bool:
        """Add or update a Facebook cookie session.
        
        Requires at least 'c_user' and 'xs' cookies from browser DevTools.
        """
        clean_cookies = cookies.strip()
        if "c_user" not in clean_cookies or "xs" not in clean_cookies:
            raise ValueError(
                "Facebook cookies must contain at least 'c_user' and 'xs'.\n"
                "Please copy them from facebook.com DevTools (F12 -> Application -> Cookies -> https://www.facebook.com)."
            )
        return self.session_manager.add_session("facebook", account_name, clean_cookies)

    def _build_headers(self, session: Dict[str, Any]) -> Dict[str, str]:
        """Construct authentic browser headers with session cookies."""
        return {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Cookie": session["cookies"],
            "Sec-Ch-Ua": '"Chromium";v="130", "Google Chrome";v="130", "Not?A_Brand";v="99"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
            "Referer": "https://www.facebook.com/",
        }

    def _parse_html_posts(self, html: str, limit: int) -> List[NormalizedPost]:
        """Parse Facebook search results from both JSON scripts and HTML containers."""
        posts: List[NormalizedPost] = []
        seen_texts = set()

        # Method 1: Extract from Comet Relay / GraphQL JSON embedded in scripts
        scripts = re.findall(r'<script type="application/json"[^>]*>(.*?)</script>', html, re.DOTALL)
        for s in scripts:
            if '"message":' in s:
                try:
                    data = json.loads(s)
                    def walk(d):
                        if isinstance(d, dict):
                            msg = d.get("message")
                            if isinstance(msg, dict) and "text" in msg:
                                text = msg.get("text", "")
                                snippet = text[:60].strip()
                                if text and len(text) > 15 and snippet not in seen_texts:
                                    seen_texts.add(snippet)
                                    
                                    # Extract author
                                    author_name = "Facebook User"
                                    author_username = "facebook_user"
                                    actors = d.get("actors")
                                    if actors and isinstance(actors, list) and len(actors) > 0:
                                        author_name = actors[0].get("name", "Facebook User")
                                        author_url = actors[0].get("url", "")
                                        m = re.search(r'facebook\.com/([^/?]+)', author_url)
                                        if m:
                                            author_username = m.group(1)

                                    # Extract url & id
                                    post_url = d.get("url") or d.get("shareable", {}).get("url") or f"https://www.facebook.com/{author_username}"
                                    post_id = d.get("post_id") or d.get("id") or f"fb_{abs(hash(snippet))}"
                                    
                                    # Extract metrics
                                    likes, comments, shares = 0, 0, 0
                                    feedback = d.get("feedback") or d.get("comet_sections", {}).get("feedback", {}).get("story", {}).get("feedback_context", {}).get("feedback_target_with_context", {})
                                    if isinstance(feedback, dict):
                                        reaction_count = feedback.get("reaction_count", {}).get("count") or feedback.get("comet_ufi_summary", {}).get("reaction_count")
                                        if reaction_count:
                                            likes = int(reaction_count)
                                        comm_count = feedback.get("comments_count", {}).get("total_count") or feedback.get("total_comment_count")
                                        if comm_count:
                                            comments = int(comm_count)
                                        share_count = feedback.get("share_count", {}).get("count")
                                        if share_count:
                                            shares = int(share_count)

                                    posts.append(NormalizedPost(
                                        id=str(post_id),
                                        platform="facebook",
                                        item_type="post",
                                        text=text.strip(),
                                        author_username=author_username,
                                        author_name=author_name,
                                        created_at=datetime.now(timezone.utc),
                                        url=post_url,
                                        likes=likes,
                                        replies=comments,
                                        reposts=shares,
                                        shares=shares,
                                        comments_count=comments,
                                        views=None,
                                        raw_data={"snippet": text[:200]},
                                    ))

                            for v in d.values():
                                walk(v)
                        elif isinstance(d, list):
                            for item in d:
                                walk(item)

                    walk(data)
                except Exception:
                    pass

        # Method 2: Fallback to DOM elements if JSON scripts yield nothing
        if not posts:
            soup = BeautifulSoup(html, "html.parser")
            articles = soup.find_all("article") or soup.find_all("div", role="article")
            if not articles:
                articles = soup.find_all("div", class_=re.compile(r'(story_body_container|feed_story|_5pcr)'))

            for art in articles:
                try:
                    text_el = art.find("div", class_=re.compile(r'(_5rgt|_5pat|userContent|story_body)')) or art
                    text = text_el.get_text(separator=" ", strip=True)
                    if not text or len(text) < 15:
                        continue

                    author_name = "Facebook User"
                    author_username = "facebook_user"
                    author_el = art.find("header") or art.find("h3") or art.find("strong")
                    if author_el:
                        author_name = author_el.get_text(strip=True)
                        author_link = author_el.find("a", href=True)
                        if author_link:
                            href = author_link["href"]
                            match = re.search(r'facebook\.com/([a-zA-Z0-9.]+)', href)
                            if match:
                                author_username = match.group(1)

                    post_id = f"fb_{abs(hash(text[:50]))}"
                    post_url = f"https://www.facebook.com/{author_username}"
                    link_el = art.find("a", href=re.compile(r'/(story\.php|posts/|permalink\.php)'))
                    if link_el:
                        post_url = link_el["href"]
                        if not post_url.startswith("http"):
                            post_url = f"https://www.facebook.com{post_url}"
                        id_match = re.search(r'(fbid=|posts/|permalink/)([0-9]+)', post_url)
                        if id_match:
                            post_id = id_match.group(2)

                    likes, comments, shares = 0, 0, 0
                    art_text = art.get_text(separator=" ", strip=True)
                    m_like = re.search(r'(\d+)\s*(?:likes?|reactions?|people like this)', art_text, re.I)
                    if m_like:
                        likes = int(m_like.group(1))
                    m_comm = re.search(r'(\d+)\s*comments?', art_text, re.I)
                    if m_comm:
                        comments = int(m_comm.group(1))
                    m_share = re.search(r'(\d+)\s*shares?', art_text, re.I)
                    if m_share:
                        shares = int(m_share.group(1))

                    posts.append(NormalizedPost(
                        id=post_id,
                        platform="facebook",
                        item_type="post",
                        text=text,
                        author_username=author_username,
                        author_name=author_name,
                        created_at=datetime.now(timezone.utc),
                        url=post_url,
                        likes=likes,
                        replies=comments,
                        reposts=shares,
                        shares=shares,
                        comments_count=comments,
                        views=None,
                        raw_data={"snippet": text[:200]},
                    ))
                except Exception as e:
                    logger.debug(f"Error parsing Facebook article element: {e}")

        return posts[:limit]

    async def search(
        self,
        query: str,
        limit: int = 20,
        **kwargs: Any
    ) -> List[NormalizedPost]:
        """Search Facebook directly for posts matching the query.
        
        Args:
            query: The search term (e.g. "COMSATS", "NUST").
            limit: Maximum number of posts to retrieve.
        """
        clean_query = query.strip()
        if not clean_query:
            return []

        # 1. Check session readiness
        session = self.session_manager.get_active_session("facebook")
        if not session:
            msg = (
                "No active Facebook session found in pool.\n"
                "To search Facebook, please add an active session cookie:\n"
                "  1. Log into facebook.com in your browser.\n"
                "  2. Open DevTools (F12) -> Application -> Cookies -> https://www.facebook.com\n"
                "  3. Copy 'c_user' and 'xs' values.\n"
                "  4. Add via CLI: python run_cli.py add-cookie --platform facebook <name> \"c_user=...; xs=...\"\n"
                "     or via the Web UI Accounts tab."
            )
            if self.raise_when_no_account:
                raise NoAccountError(msg)
            else:
                logger.warning(msg)
                return []

        # 2. Query Facebook search directly
        headers = self._build_headers(session)
        params = {"q": clean_query}

        try:
            async with httpx.AsyncClient(headers=headers, timeout=20.0, follow_redirects=True) as client:
                resp = await client.get(self.SEARCH_URL, params=params)

                if resp.status_code == 429:
                    raise RateLimitError("Facebook rate limit reached. Please wait before retrying.")
                elif resp.status_code in (401, 403) or "login" in str(resp.url):
                    self.session_manager.mark_error("facebook", session["account_name"], "Session expired or checkpoint triggered", deactivate=True)
                    raise AuthError("Facebook session expired. Please refresh your 'c_user' and 'xs' cookies.")
                elif resp.status_code != 200:
                    logger.warning(f"Facebook search returned HTTP {resp.status_code}")
                    return []

                return self._parse_html_posts(resp.text, limit=limit)

        except (NoAccountError, AuthError, RateLimitError):
            raise
        except httpx.RequestError as e:
            raise NetworkError(f"Network error while reaching Facebook: {e}") from e
        except Exception as e:
            raise CollectorError(f"Error searching Facebook for '{clean_query}': {e}") from e
