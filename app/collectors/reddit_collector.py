"""Reddit Collector implementation supporting both Submissions and Comment monitoring."""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import httpx

from app.models.post import NormalizedPost
from app.collectors.base import BaseCollector, CollectorError, NetworkError

logger = logging.getLogger(__name__)


class RedditCollector(BaseCollector):
    """Collector for Reddit posts, submissions, and individual comment threads matching search keywords."""

    def __init__(self, user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"):
        self.user_agent = user_agent
        self.headers = {
            "User-Agent": self.user_agent,
            "Accept-Language": "en-US,en;q=0.9",
        }

    async def check_status(self) -> Dict[str, Any]:
        """Check Reddit / PullPush connectivity."""
        try:
            async with httpx.AsyncClient(headers=self.headers, timeout=8.0, follow_redirects=True) as client:
                resp = await client.get("https://api.pullpush.io/reddit/search/submission/?q=test&size=1")
                is_ready = resp.status_code == 200
                if not is_ready:
                    # Check native Reddit search fallback
                    resp_native = await client.get("https://www.reddit.com/search.json?q=test&limit=1")
                    is_ready = resp_native.status_code in (200, 302, 429)
                return {
                    "platform": "reddit",
                    "ready": is_ready,
                    "status_code": resp.status_code,
                    "message": "Reddit public API is reachable." if is_ready else f"Reddit returned status {resp.status_code}",
                }
        except Exception as e:
            logger.warning(f"Reddit status check warning: {e}")
            return {
                "platform": "reddit",
                "ready": True,  # Non-blocking fallback
                "message": "Reddit collector loaded (fallback mode)",
            }

    async def _fetch_submissions(self, client: httpx.AsyncClient, query: str, limit: int, subreddit: Optional[str] = None) -> List[NormalizedPost]:
        """Fetch top-level Reddit submissions."""
        params: Dict[str, Any] = {
            "q": query,
            "size": min(limit, 50),
            "order": "desc",
            "sort_type": "created_utc",
        }
        if subreddit:
            params["subreddit"] = subreddit

        try:
            resp = await client.get("https://api.pullpush.io/reddit/search/submission/", params=params)
            if resp.status_code != 200:
                return []

            items = resp.json().get("data", [])
            posts = []
            for data in items:
                post_id = str(data.get("id", ""))
                if not post_id:
                    continue

                title = data.get("title", "")
                selftext = data.get("selftext", "")
                if selftext and selftext != "[removed]" and selftext != "[deleted]":
                    full_text = f"{title}\n\n{selftext}"
                else:
                    full_text = title

                author = data.get("author", "[deleted]")
                sub_name = data.get("subreddit", "")
                display_sub = f"r/{sub_name}" if sub_name else "Reddit"
                
                created_utc = data.get("created_utc", 0)
                try:
                    created_at = datetime.fromtimestamp(created_utc, tz=timezone.utc)
                except Exception:
                    created_at = datetime.now(timezone.utc)

                permalink = data.get("permalink", "")
                url = f"https://reddit.com{permalink}" if permalink else data.get("url", f"https://reddit.com/r/{sub_name}/comments/{post_id}")
                
                score = int(data.get("score", 0) or 0)
                num_comments = int(data.get("num_comments", 0) or 0)

                posts.append(NormalizedPost(
                    id=f"reddit_{post_id}",
                    platform="reddit",
                    item_type="post",
                    parent_id=None,
                    text=full_text,
                    author_username=f"u/{author}" if author not in ("[deleted]", "[removed]") else "[deleted]",
                    author_name=display_sub,
                    created_at=created_at,
                    url=url,
                    likes=score,
                    replies=num_comments,
                    reposts=0,
                    shares=0,
                    comments_count=num_comments,
                    views=None,
                    raw_data=data,
                ))
            return posts
        except Exception as e:
            logger.warning(f"Failed to fetch Reddit submissions: {e}")
            return []

    async def _fetch_comments(self, client: httpx.AsyncClient, query: str, limit: int, subreddit: Optional[str] = None) -> List[NormalizedPost]:
        """Fetch individual Reddit comments containing target keywords."""
        params: Dict[str, Any] = {
            "q": query,
            "size": min(limit, 50),
            "order": "desc",
            "sort_type": "created_utc",
        }
        if subreddit:
            params["subreddit"] = subreddit

        try:
            resp = await client.get("https://api.pullpush.io/reddit/search/comment/", params=params)
            if resp.status_code != 200:
                return []

            items = resp.json().get("data", [])
            comments = []
            for data in items:
                comment_id = str(data.get("id", ""))
                body = data.get("body", "")
                if not comment_id or not body or body in ("[deleted]", "[removed]"):
                    continue

                author = data.get("author", "[deleted]")
                sub_name = data.get("subreddit", "")
                display_sub = f"r/{sub_name} (Comment)" if sub_name else "Reddit Comment"
                parent_id = str(data.get("parent_id", ""))

                created_utc = data.get("created_utc", 0)
                try:
                    created_at = datetime.fromtimestamp(created_utc, tz=timezone.utc)
                except Exception:
                    created_at = datetime.now(timezone.utc)

                permalink = data.get("permalink", "")
                url = f"https://reddit.com{permalink}" if permalink else f"https://reddit.com/r/{sub_name}/comments/{parent_id}"
                score = int(data.get("score", 0) or 0)

                comments.append(NormalizedPost(
                    id=f"reddit_c_{comment_id}",
                    platform="reddit",
                    item_type="comment",
                    parent_id=parent_id,
                    text=body,
                    author_username=f"u/{author}" if author not in ("[deleted]", "[removed]") else "[deleted]",
                    author_name=display_sub,
                    created_at=created_at,
                    url=url,
                    likes=score,
                    replies=0,
                    reposts=0,
                    shares=0,
                    comments_count=0,
                    views=None,
                    raw_data=data,
                ))
            return comments
        except Exception as e:
            logger.warning(f"Failed to fetch Reddit comments: {e}")
            return []

    async def search(
        self,
        query: str,
        limit: int = 20,
        subreddit: Optional[str] = None,
        sort: str = "desc",
        **kwargs: Any
    ) -> List[NormalizedPost]:
        """Search Reddit for posts AND comments matching query."""
        clean_query = query.strip()
        if not clean_query:
            return []

        # Check if query contains subreddit directive (e.g. "r/pakistan query")
        if not subreddit and clean_query.lower().startswith("r/"):
            parts = clean_query.split(maxsplit=1)
            subreddit = parts[0][2:].strip()
            clean_query = parts[1] if len(parts) > 1 else ""

        try:
            async with httpx.AsyncClient(headers=self.headers, timeout=12.0, follow_redirects=True) as client:
                # Ingest both submissions AND comments in parallel
                per_limit = max(5, limit // 2)
                sub_task = self._fetch_submissions(client, clean_query, limit=per_limit, subreddit=subreddit)
                com_task = self._fetch_comments(client, clean_query, limit=per_limit, subreddit=subreddit)

                sub_posts, com_posts = await asyncio.gather(sub_task, com_task)
                combined = sub_posts + com_posts
                if combined:
                    combined.sort(key=lambda p: p.created_at, reverse=True)
                    return combined[:limit]

        except Exception as e:
            logger.warning(f"PullPush search failed for '{clean_query}': {e}. Trying fallback...")

        # Fallback: Reddit RSS search
        try:
            rss_url = f"https://www.reddit.com/search.rss?q={clean_query}&sort=new"
            async with httpx.AsyncClient(headers=self.headers, timeout=10.0, follow_redirects=True) as client:
                resp = await client.get(rss_url)
                if resp.status_code == 200 and resp.text:
                    import xml.etree.ElementTree as ET
                    root = ET.fromstring(resp.text)
                    ns = {"atom": "http://www.w3.org/2005/Atom"}
                    entries = root.findall("atom:entry", ns)
                    posts = []
                    for e in entries:
                        title_el = e.find("atom:title", ns)
                        link_el = e.find("atom:link", ns)
                        author_el = e.find("atom:author/atom:name", ns)
                        updated_el = e.find("atom:updated", ns)
                        id_el = e.find("atom:id", ns)

                        p_id = id_el.text if id_el is not None else str(len(posts))
                        title = title_el.text if title_el is not None else "Reddit Post"
                        link = link_el.attrib.get("href", "") if link_el is not None else ""
                        author = author_el.text if author_el is not None else "u/reddit_user"

                        dt = datetime.now(timezone.utc)
                        if updated_el is not None and updated_el.text:
                            try:
                                dt = datetime.fromisoformat(updated_el.text)
                            except Exception:
                                pass

                        posts.append(NormalizedPost(
                            id=f"reddit_{p_id[-10:]}",
                            platform="reddit",
                            item_type="post",
                            text=title,
                            author_username=author if author.startswith("u/") else f"u/{author}",
                            author_name="Reddit",
                            created_at=dt,
                            url=link,
                            likes=0,
                            replies=0,
                            reposts=0,
                            shares=0,
                            comments_count=0,
                            views=None,
                            raw_data={"title": title, "link": link},
                        ))
                        if len(posts) >= limit:
                            break
                    return posts
        except Exception as fallback_err:
            logger.error(f"Reddit fallback also failed: {fallback_err}")

        return []
