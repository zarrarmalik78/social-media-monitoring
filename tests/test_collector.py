"""Unit tests for XCollector and exception handling."""

import os
import tempfile
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime
from types import SimpleNamespace

from app.collectors.x_collector import XCollector
from app.collectors.base import NoAccountError, CollectorError, AuthError
from app.models.post import NormalizedPost


@pytest.mark.asyncio
async def test_x_collector_empty_pool_status():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "accounts.db")
        collector = XCollector(db_path=db_path)

        status = await collector.check_status()
        assert status["ready"] is False
        assert status["total_accounts"] == 0
        assert status["active_accounts"] == 0


@pytest.mark.asyncio
async def test_x_collector_search_without_accounts_raises_no_account_error():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "accounts.db")
        collector = XCollector(db_path=db_path)

        with pytest.raises(NoAccountError) as exc_info:
            await collector.search("IIUI")

        assert "No active X/Twitter accounts found" in str(exc_info.value)


@pytest.mark.asyncio
async def test_add_cookie_validation():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "accounts.db")
        collector = XCollector(db_path=db_path)

        # Missing required cookie fields
        with pytest.raises(ValueError) as exc:
            await collector.add_account_cookies("test_acc", "some_random_cookie=value")
        assert "auth_token" in str(exc.value)


@pytest.mark.asyncio
async def test_mocked_successful_search():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "accounts.db")
        collector = XCollector(db_path=db_path)

        # Mock check_status to indicate ready
        collector.check_status = AsyncMock(return_value={"ready": True, "active_accounts": 1, "total_accounts": 1})

        mock_post = NormalizedPost(
            id="1122334455",
            text="International Islamic University Islamabad announces new computer science lab.",
            author_username="iiui_official",
            author_name="IIUI Official",
            created_at=datetime(2026, 8, 30, 11, 0, 0),
            url="https://x.com/iiui_official/status/1122334455",
            likes=55,
            replies=10,
            reposts=12,
            views=3400,
        )

        with patch.object(collector, "_execute_post_search", new=AsyncMock(return_value=[mock_post])):
            posts = await collector.search("IIUI", limit=10)

            assert len(posts) == 1
            post = posts[0]
            assert isinstance(post, NormalizedPost)
            assert post.id == "1122334455"
            assert post.author_username == "iiui_official"
            assert "International Islamic University" in post.text
            assert post.likes == 55

