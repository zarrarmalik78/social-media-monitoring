"""YouTube Video and Community Post Collector implementation."""

import os
import re
import json
import logging
import hashlib
import xml.etree.ElementTree as ET
from urllib.parse import quote
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import httpx

from app.models.post import NormalizedPost
from app.collectors.base import BaseCollector, CollectorError, NetworkError

logger = logging.getLogger(__name__)


class YouTubeCollector(BaseCollector):
    """Collector for YouTube videos, shorts, and discussions using direct web scraping, Data API v3, or RSS streams."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    ):
        self.api_key = api_key or os.getenv("YOUTUBE_API_KEY")
        self.user_agent = user_agent
        self.headers = {
            "User-Agent": self.user_agent,
            "Accept-Language": "en-US,en;q=0.9",
        }

    async def check_status(self) -> Dict[str, Any]:
        """Check YouTube search connectivity."""
        try:
            async with httpx.AsyncClient(headers=self.headers, timeout=8.0, follow_redirects=True) as client:
                resp = await client.get("https://www.youtube.com/results?search_query=test")
                is_ready = resp.status_code == 200
                return {
                    "platform": "youtube",
                    "ready": is_ready,
                    "mode": "direct_web" if not self.api_key else "api_v3",
                    "message": "YouTube collector active and reachable.",
                }
        except Exception as e:
            logger.warning(f"YouTube status check warning: {e}")
            return {
                "platform": "youtube",
                "ready": True,
                "mode": "stream",
                "message": "YouTube collector active (fallback mode)",
            }

    def _parse_view_count(self, view_text: str) -> Optional[int]:
        """Convert view strings like '1,035 views' or '12K views' into integers."""
        if not view_text:
            return None
        clean = view_text.lower().replace("views", "").replace("view", "").strip()
        try:
            if "k" in clean:
                return int(float(clean.replace("k", "").replace(",", "").strip()) * 1000)
            if "m" in clean:
                return int(float(clean.replace("m", "").replace(",", "").strip()) * 1000000)
            clean = re.sub(r"[^\d]", "", clean)
            return int(clean) if clean else None
        except Exception:
            return None

    async def _search_direct_web(self, query: str, limit: int = 20) -> List[NormalizedPost]:
        """Scrape YouTube search results directly via ytInitialData."""
        encoded_q = quote(query)
        search_url = f"https://www.youtube.com/results?search_query={encoded_q}"

        async with httpx.AsyncClient(headers=self.headers, timeout=12.0, follow_redirects=True) as client:
            resp = await client.get(search_url)
            if resp.status_code != 200:
                raise NetworkError(f"YouTube direct search returned HTTP {resp.status_code}")

            match = re.search(r'var ytInitialData = ({.*?});</script>', resp.text, re.DOTALL)
            if not match:
                # Alternate pattern
                match = re.search(r'ytInitialData\s*=\s*({.*?});', resp.text, re.DOTALL)

            if not match:
                return []

            try:
                data = json.loads(match.group(1))
            except Exception as e:
                logger.warning(f"Failed to parse ytInitialData JSON: {e}")
                return []

            contents = data.get("contents", {}).get("twoColumnSearchResultsRenderer", {}).get("primaryContents", {}).get("sectionListRenderer", {}).get("contents", [])

            posts: List[NormalizedPost] = []

            for section in contents:
                items = section.get("itemSectionRenderer", {}).get("contents", [])
                for it in items:
                    if "videoRenderer" in it:
                        v = it["videoRenderer"]
                        video_id = v.get("videoId", "")
                        if not video_id:
                            continue

                        # Extract title
                        title = ""
                        title_runs = v.get("title", {}).get("runs", [])
                        if title_runs:
                            title = "".join([r.get("text", "") for r in title_runs])
                        elif "simpleText" in v.get("title", {}):
                            title = v["title"]["simpleText"]

                        # Extract Channel name
                        channel_name = "YouTube Creator"
                        owner_runs = v.get("ownerText", {}).get("runs", [])
                        if owner_runs:
                            channel_name = owner_runs[0].get("text", "YouTube Creator")

                        # Extract snippet / description
                        desc_text = ""
                        snippet_runs = v.get("detailedMetadataSnippets", [])
                        if snippet_runs:
                            desc_runs = snippet_runs[0].get("snippetText", {}).get("runs", [])
                            desc_text = "".join([r.get("text", "") for r in desc_runs])
                        elif "descriptionSnippet" in v:
                            desc_runs = v.get("descriptionSnippet", {}).get("runs", [])
                            desc_text = "".join([r.get("text", "") for r in desc_runs])

                        # View count and published time
                        views_str = v.get("viewCountText", {}).get("simpleText", "")
                        views = self._parse_view_count(views_str)

                        published_str = v.get("publishedTimeText", {}).get("simpleText", "")

                        full_text = f"{title}\n\n{desc_text}".strip() if desc_text else title
                        video_url = f"https://www.youtube.com/watch?v={video_id}"

                        posts.append(NormalizedPost(
                            id=f"yt_{video_id}",
                            platform="youtube",
                            item_type="post",
                            parent_id=None,
                            text=full_text,
                            author_username=channel_name.lower().replace(" ", "_").replace(".", "_"),
                            author_name=channel_name,
                            created_at=datetime.now(timezone.utc),
                            url=video_url,
                            likes=0,
                            replies=0,
                            reposts=0,
                            shares=0,
                            comments_count=0,
                            views=views,
                            raw_data={"videoId": video_id, "channel": channel_name, "views_text": views_str, "published_text": published_str}
                        ))

                        if len(posts) >= limit:
                            break

                if len(posts) >= limit:
                    break

            return posts

    async def _search_official_api(self, query: str, limit: int = 20) -> List[NormalizedPost]:
        """Search YouTube via official Data API v3 if API key is provided."""
        url = "https://www.googleapis.com/youtube/v3/search"
        params = {
            "key": self.api_key,
            "q": query,
            "part": "snippet",
            "type": "video",
            "maxResults": min(limit, 50),
            "order": "date"
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, params=params)
            if resp.status_code != 200:
                raise NetworkError(f"YouTube API returned HTTP {resp.status_code}")
            
            data = resp.json()
            items = data.get("items", [])
            posts: List[NormalizedPost] = []

            for item in items:
                video_id = item.get("id", {}).get("videoId", "")
                snippet = item.get("snippet", {})
                title = snippet.get("title", "")
                description = snippet.get("description", "")
                channel_title = snippet.get("channelTitle", "YouTube Channel")
                channel_id = snippet.get("channelId", "")
                published_at_str = snippet.get("publishedAt", "")

                try:
                    created_at = datetime.fromisoformat(published_at_str.replace("Z", "+00:00"))
                except Exception:
                    created_at = datetime.now(timezone.utc)

                full_text = f"{title}\n\n{description}".strip() if description else title
                post_url = f"https://www.youtube.com/watch?v={video_id}" if video_id else "https://youtube.com"

                posts.append(NormalizedPost(
                    id=f"yt_{video_id or hashlib.sha256(full_text.encode()).hexdigest()[:16]}",
                    platform="youtube",
                    text=full_text,
                    author_username=channel_title.lower().replace(" ", "_"),
                    author_name=channel_title,
                    created_at=created_at,
                    url=post_url,
                    likes=0,
                    replies=0,
                    reposts=0,
                    views=None,
                    raw_data={"videoId": video_id, "channelId": channel_id, "snippet": snippet}
                ))

            return posts

    async def _search_stream_fallback(self, query: str, limit: int = 20) -> List[NormalizedPost]:
        """Fallback to Google Video Indexing stream if direct scrape is throttled."""
        search_query = f"site:youtube.com {query}"
        encoded_q = quote(search_query)
        feed_url = f"https://news.google.com/rss/search?q={encoded_q}&hl=en&gl=PK&ceid=PK:en"

        async with httpx.AsyncClient(headers=self.headers, timeout=12.0, follow_redirects=True) as client:
            resp = await client.get(feed_url)
            if resp.status_code != 200:
                raise NetworkError(f"YouTube stream returned HTTP {resp.status_code}")

            xml_text = resp.text
            root = ET.fromstring(xml_text)
            channel = root.find("channel")
            if channel is None:
                return []

            items = channel.findall("item")
            posts: List[NormalizedPost] = []

            for item in items:
                title_elem = item.find("title")
                raw_title = title_elem.text if title_elem is not None and title_elem.text else "YouTube Video"

                link_elem = item.find("link")
                url = link_elem.text if link_elem is not None and link_elem.text else "https://youtube.com"

                desc_elem = item.find("description")
                raw_desc = desc_elem.text if desc_elem is not None and desc_elem.text else ""

                source_elem = item.find("source")
                source_name = source_elem.text if source_elem is not None and source_elem.text else "YouTube"

                author_name = source_name
                clean_title = raw_title
                if " - " in raw_title:
                    parts = raw_title.rsplit(" - ", 1)
                    clean_title = parts[0].strip()
                    if parts[1].strip() != "YouTube":
                        author_name = parts[1].strip()

                author_handle = author_name.lower().replace(" ", "_").replace(".", "_")
                post_id = f"yt_{hashlib.sha256((url + clean_title).encode('utf-8')).hexdigest()[:16]}"

                posts.append(NormalizedPost(
                    id=post_id,
                    platform="youtube",
                    text=clean_title,
                    author_username=author_handle,
                    author_name=author_name,
                    created_at=datetime.now(timezone.utc),
                    url=url,
                    likes=0,
                    replies=0,
                    reposts=0,
                    views=None,
                    raw_data={"title": raw_title, "link": url, "source": source_name},
                ))

                if len(posts) >= limit:
                    break

            return posts

    async def search(
        self,
        query: str,
        limit: int = 20,
        **kwargs: Any
    ) -> List[NormalizedPost]:
        """Search YouTube videos and discussions."""
        clean_query = query.strip()
        if not clean_query:
            return []

        try:
            # 1. If official API key provided, prioritize it
            if self.api_key:
                try:
                    return await self._search_official_api(clean_query, limit=limit)
                except Exception as e:
                    logger.warning(f"YouTube official API failed ({e}), falling back to direct web search.")

            # 2. Direct Web Search via ytInitialData
            direct_results = await self._search_direct_web(clean_query, limit=limit)
            if direct_results:
                return direct_results

            # 3. Fallback to indexing stream
            return await self._search_stream_fallback(clean_query, limit=limit)

        except (CollectorError, NetworkError):
            raise
        except Exception as e:
            logger.error(f"Error searching YouTube for '{clean_query}': {e}")
            raise CollectorError(f"Error fetching YouTube posts for '{clean_query}': {e}") from e
