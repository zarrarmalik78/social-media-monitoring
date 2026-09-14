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
            item_type="post",
            text="COMSATS University Islamabad announced new scholarship programs.",
            author_username="comsats_official",
            author_name="COMSATS Official",
            created_at=datetime(2026, 8, 28, 9, 0, 0),
            url="https://x.com/comsats_official/status/post_1",
            likes=30,
            replies=4,
            reposts=10,
            shares=10,
            comments_count=4,
            views=2500,
        )

        comment1 = NormalizedPost(
            id="comment_1",
            platform="reddit",
            item_type="comment",
            parent_id="post_1",
            text="Is this scholarship available for international students at COMSATS?",
            author_username="student_abc",
            author_name="r/pakistan (Comment)",
            created_at=datetime(2026, 8, 29, 14, 0, 0),
            url="https://reddit.com/r/pakistan/comments/comment_1",
            likes=18,
            replies=2,
            reposts=0,
            shares=0,
            comments_count=2,
            views=1200,
        )

        # Save posts & comments
        saved_count = db.save_posts([post1, comment1], searched_query="COMSATS")
        assert saved_count == 2

        # Retrieve all
        all_items = db.get_posts()
        assert len(all_items) == 2

        # Filter by keyword
        comsats_items = db.get_posts(query="COMSATS")
        assert len(comsats_items) == 2

        # Filter by item_type
        posts_only = db.get_posts(item_type="post")
        assert len(posts_only) == 1
        assert posts_only[0].id == "post_1"

        comments_only = db.get_posts(item_type="comment")
        assert len(comments_only) == 1
        assert comments_only[0].id == "comment_1"
        assert comments_only[0].parent_id == "post_1"

        # Check history
        history = db.get_search_history()
        assert len(history) == 1
        assert history[0]["query"] == "COMSATS"
        assert history[0]["results_count"] == 2

        # Check stats
        stats = db.get_stats()
        assert stats["total_posts"] == 2
        assert stats["total_searches"] == 1
        assert stats["posts_by_type"]["post"] == 1
        assert stats["posts_by_type"]["comment"] == 1
