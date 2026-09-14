"""Unit tests for Multi-Platform Collectors (Reddit, News/RSS, CollectorManager)."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timezone

from app.models.post import NormalizedPost
from app.collectors.reddit_collector import RedditCollector
from app.collectors.news_collector import NewsCollector
from app.collectors.manager import CollectorManager


@pytest.mark.asyncio
async def test_reddit_collector_parsing():
    collector = RedditCollector()

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "data": [
            {
                "id": "abc123xyz",
                "title": "Discussion about IIUI Computer Science program",
                "selftext": "Is the MS CS program at IIUI good for AI research?",
                "author": "student_pk",
                "subreddit": "pakistan",
                "created_utc": 1756550400,
                "permalink": "/r/pakistan/comments/abc123xyz/discussion_about_iiui/",
                "score": 42,
                "num_comments": 15,
            }
        ]
    }


    with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=mock_response)):
        posts = await collector.search("IIUI", limit=10)

        assert len(posts) == 1
        post = posts[0]
        assert isinstance(post, NormalizedPost)
        assert post.platform == "reddit"
        assert post.id == "reddit_abc123xyz"
        assert post.author_username == "u/student_pk"
        assert post.author_name == "r/pakistan"
        assert "Discussion about IIUI" in post.text
        assert "Is the MS CS program" in post.text
        assert post.likes == 42
        assert post.replies == 15
        assert "reddit.com/r/pakistan/comments/abc123xyz" in post.url


@pytest.mark.asyncio
async def test_news_collector_parsing():
    collector = NewsCollector()

    sample_rss_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0">
        <channel>
            <title>Google News</title>
            <item>
                <title>COMSATS University Ranked Top in Pakistan - Dawn</title>
                <link>https://news.google.com/articles/CAIiEO123</link>
                <pubDate>Sun, 30 Aug 2026 10:00:00 GMT</pubDate>
                <description>&lt;a href="https://example.com"&gt;COMSATS leads Pakistan universities in latest world rankings.&lt;/a&gt;</description>
                <source url="https://www.dawn.com">Dawn</source>
            </item>
        </channel>
    </rss>"""

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = sample_rss_xml

    with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=mock_response)):
        posts = await collector.search("COMSATS", limit=5)

        assert len(posts) == 1
        post = posts[0]
        assert isinstance(post, NormalizedPost)
        assert post.platform == "news"
        assert post.id.startswith("news_")
        assert post.author_username == "dawn"
        assert post.author_name == "Dawn"
        assert "COMSATS University Ranked Top in Pakistan" in post.text
        assert "COMSATS leads Pakistan universities" in post.text
        assert post.url == "https://news.google.com/articles/CAIiEO123"


@pytest.mark.asyncio
async def test_collector_manager_all_platforms_aggregation():
    manager = CollectorManager()

    post_x = NormalizedPost(
        id="1001",
        platform="x",
        text="X post about NUST",
        author_username="nust_official",
        created_at=datetime(2026, 8, 30, 12, 0, 0, tzinfo=timezone.utc),
        url="https://x.com/nust_official/status/1001"
    )
    post_reddit = NormalizedPost(
        id="reddit_r1",
        platform="reddit",
        text="Reddit post about NUST",
        author_username="u/nustian",
        created_at=datetime(2026, 8, 30, 14, 0, 0, tzinfo=timezone.utc),
        url="https://reddit.com/r/NUST/comments/r1"
    )
    post_news = NormalizedPost(
        id="news_n1",
        platform="news",
        text="News article about NUST",
        author_username="tribune",
        created_at=datetime(2026, 8, 30, 10, 0, 0, tzinfo=timezone.utc),
        url="https://tribune.com.pk/story/n1"
    )
    post_fb = NormalizedPost(
        id="fb_f1",
        platform="facebook",
        text="Facebook announcement about NUST",
        author_username="nust_fb",
        created_at=datetime(2026, 8, 30, 8, 0, 0, tzinfo=timezone.utc),
        url="https://facebook.com/nust/posts/1"
    )

    post_yt = NormalizedPost(
        id="yt_y1",
        platform="youtube",
        text="YouTube video about NUST campus tour",
        author_username="nust_media",
        created_at=datetime(2026, 8, 30, 16, 0, 0, tzinfo=timezone.utc),
        url="https://youtube.com/watch?v=y1"
    )
    post_ig = NormalizedPost(
        id="ig_i1",
        platform="instagram",
        text="Instagram reel about NUST",
        author_username="nust_life",
        created_at=datetime(2026, 8, 30, 15, 0, 0, tzinfo=timezone.utc),
        url="https://instagram.com/p/i1"
    )
    post_li = NormalizedPost(
        id="li_l1",
        platform="linkedin",
        text="LinkedIn update about NUST alumni",
        author_username="nust_alumni",
        created_at=datetime(2026, 8, 30, 13, 0, 0, tzinfo=timezone.utc),
        url="https://linkedin.com/posts/l1"
    )

    manager.x_collector.search = AsyncMock(return_value=[post_x])
    manager.reddit_collector.search = AsyncMock(return_value=[post_reddit])
    manager.news_collector.search = AsyncMock(return_value=[post_news])
    manager.facebook_collector.search = AsyncMock(return_value=[post_fb])
    manager.youtube_collector.search = AsyncMock(return_value=[post_yt])
    manager.instagram_collector.search = AsyncMock(return_value=[post_ig])
    manager.linkedin_collector.search = AsyncMock(return_value=[post_li])

    results = await manager.search("NUST", limit=10, platform="all")

    assert len(results) == 7
    # Verify chronological sorting (newest first: yt 16:00, ig 15:00, reddit 14:00, li 13:00, x 12:00, news 10:00, fb 08:00)
    assert results[0].id == "yt_y1"
    assert results[1].id == "ig_i1"
    assert results[2].id == "reddit_r1"
    assert results[3].id == "li_l1"
    assert results[4].id == "1001"
    assert results[5].id == "news_n1"
    assert results[6].id == "fb_f1"


