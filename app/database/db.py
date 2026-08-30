"""Local SQLite database manager for storing and querying posts."""

import os
import json
import sqlite3
from contextlib import contextmanager
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
from app.models.post import NormalizedPost


class Database:
    """Manages SQLite storage for collected social media posts and search queries."""

    def __init__(self, db_path: str = "data/monitoring.db"):
        self.db_path = db_path
        
        # Ensure parent folder exists
        parent_dir = os.path.dirname(os.path.abspath(db_path))
        if parent_dir and not os.path.exists(parent_dir):
            os.makedirs(parent_dir, exist_ok=True)
            
        self._init_db()

    @contextmanager
    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self) -> None:
        """Create necessary tables and indices if they do not exist."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Posts table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS posts (
                    id TEXT PRIMARY KEY,
                    platform TEXT NOT NULL DEFAULT 'x',
                    text TEXT NOT NULL,
                    author_username TEXT NOT NULL,
                    author_name TEXT,
                    created_at TEXT NOT NULL,
                    url TEXT NOT NULL,
                    likes INTEGER NOT NULL DEFAULT 0,
                    replies INTEGER NOT NULL DEFAULT 0,
                    reposts INTEGER NOT NULL DEFAULT 0,
                    views INTEGER,
                    raw_data TEXT,
                    searched_query TEXT,
                    collected_at TEXT NOT NULL
                )
            """)
            
            # Search log table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS searches (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    query TEXT NOT NULL,
                    platform TEXT NOT NULL DEFAULT 'x',
                    results_count INTEGER NOT NULL DEFAULT 0,
                    searched_at TEXT NOT NULL
                )
            """)

            # Indices
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_posts_author ON posts(author_username)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_posts_created ON posts(created_at)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_posts_query ON posts(searched_query)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_searches_query ON searches(query)")

            conn.commit()

    def save_posts(self, posts: List[NormalizedPost], searched_query: Optional[str] = None) -> int:
        """Insert or update posts in SQLite."""
        if not posts:
            if searched_query:
                self.log_search(searched_query, results_count=0)
            return 0

        collected_at = datetime.now(timezone.utc).isoformat()
        saved_count = 0

        with self._get_connection() as conn:
            cursor = conn.cursor()
            for post in posts:
                def safe_serialize(o):
                    if isinstance(o, datetime):
                        return o.isoformat()
                    return str(o)
                raw_json = json.dumps(post.raw_data, default=safe_serialize) if post.raw_data else None
                created_iso = post.created_at.isoformat() if isinstance(post.created_at, datetime) else str(post.created_at)

                cursor.execute("""
                    INSERT INTO posts (
                        id, platform, text, author_username, author_name,
                        created_at, url, likes, replies, reposts, views,
                        raw_data, searched_query, collected_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        likes = excluded.likes,
                        replies = excluded.replies,
                        reposts = excluded.reposts,
                        views = excluded.views,
                        text = excluded.text,
                        collected_at = excluded.collected_at
                """, (
                    post.id,
                    post.platform,
                    post.text,
                    post.author_username,
                    post.author_name,
                    created_iso,
                    post.url,
                    post.likes,
                    post.replies,
                    post.reposts,
                    post.views,
                    raw_json,
                    searched_query,
                    collected_at,
                ))
                saved_count += 1

            # Also log search entry
            if searched_query:
                cursor.execute("""
                    INSERT INTO searches (query, platform, results_count, searched_at)
                    VALUES (?, ?, ?, ?)
                """, (searched_query, posts[0].platform if posts else "x", len(posts), collected_at))

            conn.commit()

        return saved_count

    def log_search(self, query: str, results_count: int = 0, platform: str = "x") -> None:
        """Log a search query event."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO searches (query, platform, results_count, searched_at)
                VALUES (?, ?, ?, ?)
            """, (query, platform, results_count, datetime.now(timezone.utc).isoformat()))
            conn.commit()

    def get_posts(
        self,
        query: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[NormalizedPost]:
        """Fetch saved posts from SQLite, optionally filtered by keyword query."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if query:
                like_pattern = f"%{query}%"
                cursor.execute("""
                    SELECT * FROM posts 
                    WHERE text LIKE ? OR author_username LIKE ? OR searched_query LIKE ?
                    ORDER BY created_at DESC 
                    LIMIT ? OFFSET ?
                """, (like_pattern, like_pattern, like_pattern, limit, offset))
            else:
                cursor.execute("""
                    SELECT * FROM posts 
                    ORDER BY created_at DESC 
                    LIMIT ? OFFSET ?
                """, (limit, offset))

            rows = cursor.fetchall()
            posts = []
            for row in rows:
                raw_dict = json.loads(row["raw_data"]) if row["raw_data"] else None
                try:
                    dt = datetime.fromisoformat(row["created_at"])
                except Exception:
                    dt = datetime.now(timezone.utc)

                posts.append(NormalizedPost(
                    id=row["id"],
                    platform=row["platform"],
                    text=row["text"],
                    author_username=row["author_username"],
                    author_name=row["author_name"] or "",
                    created_at=dt,
                    url=row["url"],
                    likes=row["likes"],
                    replies=row["replies"],
                    reposts=row["reposts"],
                    views=row["views"],
                    raw_data=raw_dict,
                ))
            return posts

    def get_search_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Retrieve recent search queries."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, query, platform, results_count, searched_at 
                FROM searches 
                ORDER BY searched_at DESC 
                LIMIT ?
            """, (limit,))
            rows = cursor.fetchall()
            return [dict(r) for r in rows]

    def get_stats(self) -> Dict[str, Any]:
        """Return basic database storage statistics."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM posts")
            total_posts = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(DISTINCT author_username) FROM posts")
            unique_authors = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM searches")
            total_searches = cursor.fetchone()[0]

            return {
                "total_posts": total_posts,
                "unique_authors": unique_authors,
                "total_searches": total_searches,
                "db_path": self.db_path,
            }
