"""Unit tests for dedicated platform collectors and SessionManager."""

import pytest
import os
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch, MagicMock

from app.models.post import NormalizedPost
from app.utils.session_manager import SessionManager
from app.collectors.linkedin_collector import LinkedInCollector
from app.collectors.facebook_collector import FacebookCollector
from app.collectors.instagram_collector import InstagramCollector
from app.collectors.base import NoAccountError


@pytest.fixture
def temp_accounts_db(tmp_path):
    """Temporary SQLite database for session manager testing."""
    return str(tmp_path / "test_accounts.db")


def test_session_manager(temp_accounts_db):
    """Test session manager CRUD operations and cookie parsing."""
    sm = SessionManager(db_path=temp_accounts_db)
    
    # 1. Add session
    res = sm.add_session("linkedin", "li_test", "li_at=test_token_123; JSESSIONID=\"ajax:98765\"")
    assert res is True

    # 2. Get active session
    sess = sm.get_active_session("linkedin")
    assert sess is not None
    assert sess["account_name"] == "li_test"
    assert "test_token_123" in sess["cookies"]
    assert sess["total_req"] == 1

    # 3. Parse cookies
    cookie_dict = sm.parse_cookie_dict(sess["cookies"])
    assert cookie_dict["li_at"] == "test_token_123"
    assert cookie_dict["JSESSIONID"] == '"ajax:98765"'

    # 4. List sessions
    sessions = sm.list_sessions(platform="linkedin")
    assert len(sessions) == 1

    # 5. Delete session
    del_res = sm.delete_session("linkedin", "li_test")
    assert del_res is True
    assert sm.get_active_session("linkedin") is None


@pytest.mark.asyncio
async def test_linkedin_collector_no_account(temp_accounts_db):
    """Verify LinkedInCollector raises NoAccountError when no account is configured."""
    collector = LinkedInCollector(db_path=temp_accounts_db, raise_when_no_account=True)
    with pytest.raises(NoAccountError):
        await collector.search("COMSATS")


@pytest.mark.asyncio
async def test_linkedin_collector_parsing(temp_accounts_db):
    """Verify parsing of Voyager JSON into NormalizedPost."""
    collector = LinkedInCollector(db_path=temp_accounts_db)
    
    mock_voyager_payload = {
        "elements": [
            {
                "entityUrn": "urn:li:activity:7123456789012345678",
                "commentary": {"text": {"text": "Exciting research updates from COMSATS University Islamabad!"}},
                "actor": {
                    "name": {"text": "Dr. Muhammad Ali"},
                    "urn": "urn:li:member:123456"
                },
                "socialDetail": {
                    "totalSocialActivityCounts": {
                        "numLikes": 45,
                        "numComments": 12,
                        "numShares": 8
                    }
                },
                "postedAt": 1725540000000
            }
        ]
    }

    posts = collector._parse_voyager_posts(mock_voyager_payload, limit=10)
    assert len(posts) == 1
    p = posts[0]
    assert p.platform == "linkedin"
    assert "COMSATS University" in p.text
    assert p.author_name == "Dr. Muhammad Ali"
    assert p.likes == 45
    assert p.replies == 12
    assert p.shares == 8
    assert "urn:li:activity" in p.url


@pytest.mark.asyncio
async def test_facebook_collector_no_account(temp_accounts_db):
    """Verify FacebookCollector raises NoAccountError when no account is configured."""
    collector = FacebookCollector(db_path=temp_accounts_db, raise_when_no_account=True)
    with pytest.raises(NoAccountError):
        await collector.search("COMSATS")


def test_facebook_html_parsing(temp_accounts_db):
    """Verify parsing of Facebook HTML story articles into NormalizedPost."""
    collector = FacebookCollector(db_path=temp_accounts_db)

    sample_html = """
    <html>
        <body>
            <article>
                <header>
                    <a href="https://facebook.com/comsats.official">COMSATS Official</a>
                </header>
                <div class="userContent">
                    Admissions are officially open for Fall 2026 semester at COMSATS Islamabad campus!
                </div>
                <a href="https://www.facebook.com/posts/987654321">View post</a>
                <div>120 likes 35 comments 14 shares</div>
            </article>
        </body>
    </html>
    """

    posts = collector._parse_html_posts(sample_html, limit=10)
    assert len(posts) == 1
    p = posts[0]
    assert p.platform == "facebook"
    assert "Admissions are officially open" in p.text
    assert p.author_name == "COMSATS Official"
    assert p.author_username == "comsats.official"
    assert p.likes == 120
    assert p.replies == 35
    assert p.shares == 14


@pytest.mark.asyncio
async def test_instagram_collector_parsing(temp_accounts_db):
    """Verify parsing of Instagram media items into NormalizedPost."""
    collector = InstagramCollector(db_path=temp_accounts_db)

    mock_items = [
        {
            "media": {
                "id": "31415926535",
                "code": "Cxyz123abc",
                "caption": {"text": "Campus moments at COMSATS Islamabad! #studentlife #comsats"},
                "user": {
                    "username": "comsats_student_council",
                    "full_name": "COMSATS Student Council"
                },
                "like_count": 340,
                "comment_count": 28,
                "play_count": 1500,
                "taken_at": 1725540000
            }
        }
    ]

    posts = collector._parse_media_items(mock_items, limit=10)
    assert len(posts) == 1
    p = posts[0]
    assert p.platform == "instagram"
    assert "Campus moments at COMSATS" in p.text
    assert p.author_username == "comsats_student_council"
    assert p.author_name == "COMSATS Student Council"
    assert p.likes == 340
    assert p.replies == 28
    assert p.views == 1500
    assert p.url == "https://www.instagram.com/p/Cxyz123abc/"
