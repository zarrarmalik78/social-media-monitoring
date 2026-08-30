"""Unit tests for SQLite database layer."""

import os
import tempfile
from datetime import datetime
from app.database.db import Database
from app.models.post import NormalizedPost


def test_sqlite_save_and_retrieve():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_file = os.path.join(tmpdir, "test_monitoring.db")
        db = Database(db_file)

        post1 = NormalizedPost(
            id="post_1",
            platform="x",
            text="COMSATS University Islamabad announced new scholarship programs.",
            author_username="comsats_official",
            author_name="COMSATS Official",
            created_at=datetime(2026, 8, 28, 9, 0, 0),
            url="https://x.com/comsats_official/status/post_1",
            likes=30,
            replies=4,
            reposts=10,
            views=2500,
        )

        post2 = NormalizedPost(
            id="post_2",
            platform="x",
            text="IIUI annual sports gala kicks off next Monday.",
            author_username="iiui_news",
            author_name="IIUI News",
            created_at=datetime(2026, 8, 29, 14, 0, 0),
            url="https://x.com/iiui_news/status/post_2",
            likes=18,
            replies=2,
            reposts=3,
            views=1200,
        )

        # Save posts
        saved_count = db.save_posts([post1, post2], searched_query="universities")
        assert saved_count == 2

        # Retrieve all
        all_posts = db.get_posts()
        assert len(all_posts) == 2

        # Filter by keyword
        comsats_posts = db.get_posts(query="COMSATS")
        assert len(comsats_posts) == 1
        assert comsats_posts[0].author_username == "comsats_official"

        # Check history
        history = db.get_search_history()
        assert len(history) == 1
        assert history[0]["query"] == "universities"
        assert history[0]["results_count"] == 2

        # Check stats
        stats = db.get_stats()
        assert stats["total_posts"] == 2
        assert stats["unique_authors"] == 2
        assert stats["total_searches"] == 1
