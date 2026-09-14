"""News & RSS Feeds Collector implementation using public news search feeds."""

import logging
import hashlib
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import quote
import httpx
import re

from app.models.post import NormalizedPost
from app.collectors.base import BaseCollector, CollectorError, NetworkError

logger = logging.getLogger(__name__)


class NewsCollector(BaseCollector):
    """Collector for public News and RSS feeds for institutional topic tracking."""

    def __init__(self, user_agent: str = "SocialMediaMonitoringBot/1.0 (academic news aggregator)"):
        self.user_agent = user_agent
        self.headers = {
            "User-Agent": self.user_agent,
            "Accept": "application/rss+xml, application/xml, text/xml",
        }

    async def check_status(self) -> Dict[str, Any]:
        """Check News feed accessibility."""
        try:
            async with httpx.AsyncClient(headers=self.headers, timeout=10.0, follow_redirects=True) as client:
                resp = await client.get("https://news.google.com/rss?hl=en")
                is_ready = resp.status_code == 200
                return {
                    "platform": "news",
                    "ready": is_ready,
                    "status_code": resp.status_code,
                    "message": "Google News RSS feed is reachable." if is_ready else f"News feed status {resp.status_code}",
                }
        except Exception as e:
            logger.warning(f"NewsCollector status error: {e}")
            return {
                "platform": "news",
                "ready": False,
                "error": str(e),
            }

    def _strip_html(self, raw_html: str) -> str:
        """Clean HTML tags and entities from RSS descriptions."""
        if not raw_html:
            return ""
        clean = re.sub(r'<[^>]+>', ' ', raw_html)
        clean = re.sub(r'\s+', ' ', clean).strip()
        return clean

    async def search(
        self,
        query: str,
        limit: int = 20,
        hl: str = "en",
        gl: str = "PK",
        **kwargs: Any
    ) -> List[NormalizedPost]:
        """Search Google News RSS feeds for articles matching the query."""
        clean_query = query.strip()
        if not clean_query:
            return []

        encoded_q = quote(clean_query)
        feed_url = f"https://news.google.com/rss/search?q={encoded_q}&hl={hl}&gl={gl}&ceid={gl}:{hl}"

        try:
            async with httpx.AsyncClient(headers=self.headers, timeout=15.0, follow_redirects=True) as client:
                resp = await client.get(feed_url)
                if resp.status_code != 200:
                    raise NetworkError(f"News RSS feed returned HTTP {resp.status_code}")

                xml_text = resp.text
                root = ET.fromstring(xml_text)
                
                channel = root.find("channel")
                if channel is None:
                    return []

                items = channel.findall("item")
                posts: List[NormalizedPost] = []

                for item in items:
                    title_elem = item.find("title")
                    title = title_elem.text if title_elem is not None and title_elem.text else "Untitled Article"
                    
                    link_elem = item.find("link")
                    url = link_elem.text if link_elem is not None and link_elem.text else ""

                    desc_elem = item.find("description")
                    raw_desc = desc_elem.text if desc_elem is not None and desc_elem.text else ""
                    clean_desc = self._strip_html(raw_desc)

                    source_elem = item.find("source")
                    source_name = source_elem.text if source_elem is not None and source_elem.text else "News"

                    pubdate_elem = item.find("pubDate")
                    created_at = datetime.now(timezone.utc)
                    if pubdate_elem is not None and pubdate_elem.text:
                        try:
                            created_at = parsedate_to_datetime(pubdate_elem.text)
                            if created_at.tzinfo is None:
                                created_at = created_at.replace(tzinfo=timezone.utc)
                        except Exception:
                            pass

                    # Unique ID based on article URL hash
                    url_hash = hashlib.sha256((url or title).encode("utf-8")).hexdigest()[:16]
                    post_id = f"news_{url_hash}"

                    # Clean title: Google News appends " - Source" at the end of title
                    clean_title = title
                    if " - " in clean_title:
                        clean_title = clean_title.rsplit(" - ", 1)[0].strip()

                    full_text = f"{clean_title}\n\n{clean_desc}" if clean_desc and clean_desc != clean_title else clean_title

                    posts.append(NormalizedPost(
                        id=post_id,
                        platform="news",
                        text=full_text,
                        author_username=source_name.lower().replace(" ", "_"),
                        author_name=source_name,
                        created_at=created_at,
                        url=url,
                        likes=0,
                        replies=0,
                        reposts=0,
                        views=None,
                        raw_data={"title": title, "link": url, "source": source_name, "pubDate": str(created_at)},
                    ))

                    if len(posts) >= limit:
                        break

                return posts

        except (CollectorError, NetworkError):
            raise
        except Exception as e:
            logger.error(f"Error searching news feeds for '{clean_query}': {e}")
            raise CollectorError(f"Error fetching news feeds for '{clean_query}': {e}") from e
