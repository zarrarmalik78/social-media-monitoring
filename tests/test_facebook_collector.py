"""Unit tests for dedicated FacebookCollector."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.models.post import NormalizedPost
from app.collectors.facebook_collector import FacebookCollector
from app.utils.session_manager import SessionManager


@pytest.mark.asyncio
async def test_facebook_collector_search_with_session(tmp_path):
    """Test dedicated FacebookCollector searching with an active session."""
    test_db = str(tmp_path / "accounts.db")
    sm = SessionManager(db_path=test_db)
    sm.add_session("facebook", "fb_test", "c_user=12345678; xs=abcdef123456")

    collector = FacebookCollector(db_path=test_db)

    sample_html = """
    <html>
        <body>
            <article>
                <header>
                    <a href="https://facebook.com/iiui.official">IIUI Official</a>
                </header>
                <div class="userContent">
                    Admissions are officially open for Fall 2026 semester at IIUI Islamabad campus!
                </div>
                <a href="https://www.facebook.com/posts/123456789">Permalink</a>
                <div>45 likes 12 comments 3 shares</div>
            </article>
        </body>
    </html>
    """

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = sample_html

    with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=mock_response)):
        posts = await collector.search("IIUI", limit=5)

        assert len(posts) == 1
        post = posts[0]
        assert isinstance(post, NormalizedPost)
        assert post.platform == "facebook"
        assert post.id == "123456789"
        assert "Admissions are officially open" in post.text
        assert post.author_name == "IIUI Official"
        assert post.likes == 45
        assert post.replies == 12
        assert post.shares == 3
