"""Unified Multi-Platform Collector Manager with 5 Resilience & Rate-Limit Strategies."""

import asyncio
import time
import logging
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, timezone

from app.models.post import NormalizedPost
from app.collectors.base import BaseCollector, CollectorError, NoAccountError
from app.collectors.x_collector import XCollector
from app.collectors.reddit_collector import RedditCollector
from app.collectors.news_collector import NewsCollector
from app.collectors.facebook_collector import FacebookCollector
from app.collectors.youtube_collector import YouTubeCollector
from app.collectors.instagram_collector import InstagramCollector
from app.collectors.linkedin_collector import LinkedInCollector
from app.utils.analyzer import analyzer
from app.utils.retry import retry_with_backoff

logger = logging.getLogger(__name__)


class CollectorManager:
    """Orchestrates searches across 7 dedicated platforms with Caching, Batching, Incremental Sync & Backoff."""

    def __init__(
        self,
        db_path: str = "data/accounts.db",
        cache_ttl_seconds: int = 180  # Strategy 1: 3-minute query cache window
    ):
        self.db_path = db_path
        self.cache_ttl = cache_ttl_seconds
        
        # Strategy 1: In-Memory Query Cache ((query, platform) -> (timestamp, posts))
        self._query_cache: Dict[Tuple[str, str], Tuple[float, List[NormalizedPost]]] = {}
        
        # Strategy 3: Incremental Sync Watermarks ((query, platform) -> latest_post_timestamp)
        self._watermarks: Dict[Tuple[str, str], datetime] = {}

        self.x_collector = XCollector(db_path=db_path)
        self.reddit_collector = RedditCollector()
        self.news_collector = NewsCollector()
        self.facebook_collector = FacebookCollector(db_path=db_path)
        self.youtube_collector = YouTubeCollector()
        self.instagram_collector = InstagramCollector(db_path=db_path)
        self.linkedin_collector = LinkedInCollector(db_path=db_path)

        self.collectors: Dict[str, BaseCollector] = {
            "x": self.x_collector,
            "facebook": self.facebook_collector,
            "reddit": self.reddit_collector,
            "youtube": self.youtube_collector,
            "instagram": self.instagram_collector,
            "linkedin": self.linkedin_collector,
            "news": self.news_collector,
        }

    async def check_status(self) -> Dict[str, Any]:
        """Check readiness status across all 7 registered platforms."""
        statuses = {}
        all_accounts = []
        total_accs = 0
        active_accs = 0

        for name, collector in self.collectors.items():
            try:
                st = await collector.check_status()
                statuses[name] = st
                
                # Aggregate accounts
                accs = st.get("accounts", [])
                for acc in accs:
                    acc_dict = dict(acc) if isinstance(acc, dict) else acc.__dict__
                    acc_dict["platform"] = name
                    all_accounts.append(acc_dict)
                
                total_accs += st.get("total_accounts", 0)
                active_accs += st.get("active_accounts", 0)
            except Exception as e:
                statuses[name] = {"platform": name, "ready": False, "error": str(e)}

        overall_ready = any(s.get("ready", False) for s in statuses.values())

        return {
            "ready": overall_ready,
            "platforms": statuses,
            "active_accounts": active_accs,
            "total_accounts": total_accs,
            "accounts": all_accounts,
            "db_path": self.db_path,
        }

    async def add_account_cookies(self, platform: str, account_name: str, cookies: str) -> bool:
        """Add or update cookies for any supported platform."""
        clean_platform = platform.lower().strip()
        if clean_platform not in self.collectors:
            raise ValueError(f"Unknown platform '{platform}'. Supported: {list(self.collectors.keys())}")
        
        collector = self.collectors[clean_platform]
        if hasattr(collector, "add_account_cookies"):
            return await collector.add_account_cookies(account_name, cookies)
        raise ValueError(f"Platform '{platform}' does not require session cookies.")

    async def _fetch_single_collector(
        self,
        name: str,
        query: str,
        limit: int,
        incremental: bool = False,
        **kwargs: Any
    ) -> List[NormalizedPost]:
        """Fetch posts from a single collector with Strategy 5 (Exponential Backoff)."""
        collector = self.collectors[name]

        # Strategy 2: Batch requests - Fetch larger page per call (e.g. up to 50) to minimize network roundtrips
        batch_limit = max(limit, 25)

        async def _do_search():
            return await collector.search(query=query, limit=batch_limit, **kwargs)

        # Strategy 5: Retry with exponential backoff on transient errors/rate limits
        posts = await retry_with_backoff(_do_search, max_retries=2, initial_delay=0.5)

        # Strategy 3: Incremental Sync - Watermark filtering
        watermark_key = (query.lower().strip(), name)
        last_seen = self._watermarks.get(watermark_key)

        if incremental and last_seen:
            posts = [p for p in posts if p.created_at > last_seen]

        # Update watermark with newest post time
        if posts:
            newest_time = max(p.created_at for p in posts)
            if last_seen is None or newest_time > last_seen:
                self._watermarks[watermark_key] = newest_time

        return posts

    async def search(
        self,
        query: str,
        limit: int = 20,
        platform: str = "all",
        force_refresh: bool = False,
        incremental: bool = False,
        **kwargs: Any
    ) -> List[NormalizedPost]:
        """Execute multi-platform search with Caching, Batching, Incremental Sync, and Fault Tolerance.
        
        Args:
            query: The search keywords or advanced search query.
            limit: Maximum number of posts to retrieve.
            platform: Target platform ('all', 'x', 'facebook', 'reddit', 'youtube', 'instagram', 'linkedin', 'news').
            force_refresh: If True, bypass Strategy 1 cache and query live scrapers.
            incremental: If True, only retrieve posts newer than the last collected watermark.
        """
        clean_query = query.strip()
        clean_platform = platform.lower().strip()
        cache_key = (clean_query.lower(), clean_platform)

        # Strategy 1: Check in-memory query cache (Avoid redundant requests)
        if not force_refresh and not incremental:
            cached = self._query_cache.get(cache_key)
            if cached:
                cached_time, cached_posts = cached
                if (time.time() - cached_time) < self.cache_ttl:
                    logger.info(f"[CACHE HIT] Returning {len(cached_posts)} cached posts for '{clean_query}' on '{clean_platform}'.")
                    return cached_posts[:limit]

        # Target platform selection
        if clean_platform != "all" and clean_platform in self.collectors:
            target_collectors = [clean_platform]
        elif clean_platform == "all":
            # Search all 7 platforms in parallel
            target_collectors = list(self.collectors.keys())
        else:
            raise CollectorError(f"Unknown platform requested: '{clean_platform}'")

        # Strategy 4: Resilient Fault-Tolerant Parallel Dispatch
        tasks = [
            self._fetch_single_collector(
                name=c_name,
                query=clean_query,
                limit=limit,
                incremental=incremental,
                **kwargs
            )
            for c_name in target_collectors
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        combined_posts: List[NormalizedPost] = []
        errors: List[str] = []

        for c_name, res in zip(target_collectors, results):
            if isinstance(res, Exception):
                logger.warning(f"Platform '{c_name}' encountered an error: {res}")
                errors.append(f"{c_name}: {res}")
            elif isinstance(res, list):
                combined_posts.extend(res)

        # If a single specific platform was requested and errored, raise error
        if len(target_collectors) == 1 and errors:
            raise CollectorError(errors[0])

        # Deduplicate posts by (platform, id)
        seen_keys = set()
        deduped_posts: List[NormalizedPost] = []
        for post in combined_posts:
            post_key = (post.platform, str(post.id))
            if post_key not in seen_keys:
                seen_keys.add(post_key)
                deduped_posts.append(post)

        # Sort by creation date descending
        deduped_posts.sort(key=lambda p: p.created_at, reverse=True)
        final_posts = deduped_posts[:limit] if clean_platform != "all" else deduped_posts

        # Run AI Sentiment & Topic analysis
        analyzer.enrich_posts(final_posts)

        # Cache results for Strategy 1
        if not incremental:
            self._query_cache[cache_key] = (time.time(), final_posts)

        return final_posts
