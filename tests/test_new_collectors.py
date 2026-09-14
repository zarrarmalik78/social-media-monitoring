"""Unit tests for dedicated YouTube, Instagram, and LinkedIn collectors."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.collectors.youtube_collector import YouTubeCollector
from app.collectors.instagram_collector import InstagramCollector
from app.collectors.linkedin_collector import LinkedInCollector
from app.utils.session_manager import SessionManager


@pytest.mark.asyncio
async def test_youtube_collector_scrape():
    """Test dedicated YouTubeCollector ytInitialData extraction."""
    collector = YouTubeCollector()
    mock_html = """
    <html>
        <script>
            var ytInitialData = {
                "contents": {
                    "twoColumnSearchResultsRenderer": {
                        "primaryContents": {
                            "sectionListRenderer": {
                                "contents": [
                                    {
                                        "itemSectionRenderer": {
                                            "contents": [
                                                {
                                                    "videoRenderer": {
                                                        "videoId": "abc123xyz",
                                                        "title": {"runs": [{"text": "COMSATS University Islamabad Campus Tour 2026"}]},
                                                        "ownerText": {"runs": [{"text": "COMSATS Media Club"}]},
                                                        "detailedMetadataSnippets": [{"snippetText": {"runs": [{"text": "A full walkthrough of the campus, labs, and student facilities."}]}}],
                                                        "viewCountText": {"simpleText": "14,520 views"},
                                                        "publishedTimeText": {"simpleText": "2 days ago"}
                                                    }
                                                }
                                            ]
                                        }
                                    }
                                ]
                            }
                        }
                    }
                }
            };
        </script>
    </html>
    """
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = mock_html

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp
        posts = await collector.search("COMSATS", limit=5)

        assert len(posts) == 1
        post = posts[0]
        assert post.platform == "youtube"
        assert "COMSATS University Islamabad Campus Tour" in post.text
        assert post.author_name == "COMSATS Media Club"
        assert post.views == 14520
        assert "youtube.com/watch?v=abc123xyz" in post.url


@pytest.mark.asyncio
async def test_instagram_collector_with_session(tmp_path):
    """Test dedicated InstagramCollector searching with session cookie."""
    test_db = str(tmp_path / "accounts.db")
    sm = SessionManager(db_path=test_db)
    sm.add_session("instagram", "ig_test", "sessionid=test_session_12345")

    collector = InstagramCollector(db_path=test_db)

    mock_tag_payload = {
        "data": {
            "recent": {
                "sections": [
                    {
                        "layout_content": {
                            "medias": [
                                {
                                    "media": {
                                        "id": "123456789",
                                        "code": "Cfest2026",
                                        "caption": {"text": "COMSATS Campus Fest 2026! Live musical concert and food stalls."},
                                        "user": {
                                            "username": "comsats_official",
                                            "full_name": "COMSATS University"
                                        },
                                        "like_count": 520,
                                        "comment_count": 38,
                                        "taken_at": 1725540000
                                    }
                                }
                            ]
                        }
                    }
                ]
            }
        }
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_tag_payload

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp
        posts = await collector.search("COMSATS", limit=5)

        assert len(posts) == 1
        post = posts[0]
        assert post.platform == "instagram"
        assert "Fest" in post.text
        assert post.likes == 520
        assert post.replies == 38
        assert "instagram.com/p/Cfest2026/" in post.url


@pytest.mark.asyncio
async def test_linkedin_collector_with_session(tmp_path):
    """Test dedicated LinkedInCollector searching with Voyager session."""
    test_db = str(tmp_path / "accounts.db")
    sm = SessionManager(db_path=test_db)
    sm.add_session("linkedin", "li_test", "li_at=test_li_at_token; JSESSIONID=\"ajax:12345\"")

    collector = LinkedInCollector(db_path=test_db)

    mock_voyager_payload = {
        "elements": [
            {
                "entityUrn": "urn:li:activity:999888777",
                "commentary": {"text": {"text": "Dr. Ali Khan on LinkedIn: Excited to announce our new research grant at COMSATS!"}},
                "actor": {
                    "name": {"text": "Dr. Ali Khan"},
                    "urn": "urn:li:member:dr_ali_khan"
                },
                "socialDetail": {
                    "totalSocialActivityCounts": {
                        "numLikes": 88,
                        "numComments": 14,
                        "numShares": 6
                    }
                },
                "postedAt": 1725540000000
            }
        ]
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_voyager_payload

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp
        posts = await collector.search("COMSATS", limit=5)

        assert len(posts) == 1
        post = posts[0]
        assert post.platform == "linkedin"
        assert "research grant" in post.text
        assert post.author_name == "Dr. Ali Khan"
        assert post.likes == 88
        assert post.replies == 14
        assert post.shares == 6
        assert "linkedin.com/feed/update/urn:li:activity:999888777" in post.url
