"""Local SQLite database manager for storing and querying posts and comments."""

import os
import json
import sqlite3
from contextlib import contextmanager
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
from app.models.post import NormalizedPost


class Database:
    """Manages SQLite storage for collected social media posts, comments, and search queries."""

    def __init__(self, db_path: str = "data/monitoring.db"):
        """Initialize SQLite database connection and create tables if needed."""
        self.db_path = db_path
        os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
        self._init_db()

    @contextmanager
    def _get_connection(self):
        """Get a configured sqlite3 connection object."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self) -> None:
        """Create tables and apply schema migrations."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Posts and comments table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS posts (
                    id TEXT PRIMARY KEY,
                    platform TEXT NOT NULL DEFAULT 'x',
                    item_type TEXT NOT NULL DEFAULT 'post',
                    parent_id TEXT,
                    text TEXT NOT NULL,
                    author_username TEXT NOT NULL,
                    author_name TEXT,
                    created_at TEXT NOT NULL,
                    url TEXT NOT NULL,
                    likes INTEGER NOT NULL DEFAULT 0,
                    replies INTEGER NOT NULL DEFAULT 0,
                    reposts INTEGER NOT NULL DEFAULT 0,
                    shares INTEGER NOT NULL DEFAULT 0,
                    comments_count INTEGER NOT NULL DEFAULT 0,
                    views INTEGER,
                    raw_data TEXT,
                    searched_query TEXT,
                    collected_at TEXT NOT NULL,
                    sentiment_score REAL DEFAULT 0.0,
                    sentiment_label TEXT DEFAULT 'Neutral',
                    topics TEXT DEFAULT '[]'
                )
            """)
            
            # Add dynamic columns if upgrading from older schema version
            cursor.execute("PRAGMA table_info(posts)")
            columns = [col[1] for col in cursor.fetchall()]
            if "sentiment_score" not in columns:
                cursor.execute("ALTER TABLE posts ADD COLUMN sentiment_score REAL DEFAULT 0.0")
            if "sentiment_label" not in columns:
                cursor.execute("ALTER TABLE posts ADD COLUMN sentiment_label TEXT DEFAULT 'Neutral'")
            if "topics" not in columns:
                cursor.execute("ALTER TABLE posts ADD COLUMN topics TEXT DEFAULT '[]'")
            if "item_type" not in columns:
                cursor.execute("ALTER TABLE posts ADD COLUMN item_type TEXT DEFAULT 'post'")
            if "parent_id" not in columns:
                cursor.execute("ALTER TABLE posts ADD COLUMN parent_id TEXT")
            if "shares" not in columns:
                cursor.execute("ALTER TABLE posts ADD COLUMN shares INTEGER DEFAULT 0")
            if "comments_count" not in columns:
                cursor.execute("ALTER TABLE posts ADD COLUMN comments_count INTEGER DEFAULT 0")
            
            # Sync existing records where reposts/replies had values
            cursor.execute("UPDATE posts SET shares = reposts WHERE (shares IS NULL OR shares = 0) AND reposts > 0")
            cursor.execute("UPDATE posts SET comments_count = replies WHERE (comments_count IS NULL OR comments_count = 0) AND replies > 0")
            cursor.execute("UPDATE posts SET reposts = shares WHERE (reposts IS NULL OR reposts = 0) AND shares > 0")
            cursor.execute("UPDATE posts SET replies = comments_count WHERE (replies IS NULL OR replies = 0) AND comments_count > 0")

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

            # Authenticity & Verification Tables
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS content_analysis (
                    post_id TEXT PRIMARY KEY,
                    ai_text_status TEXT,
                    ai_text_score REAL,
                    media_priority TEXT,
                    media_status TEXT,
                    context_status TEXT,
                    overall_status TEXT,
                    analyzed_at TEXT,
                    FOREIGN KEY(post_id) REFERENCES posts(id) ON DELETE CASCADE
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS verification_evidence (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    post_id TEXT,
                    claim TEXT NOT NULL,
                    source_url TEXT,
                    source_title TEXT,
                    source_authority TEXT,
                    supports_claim BOOLEAN,
                    evidence_summary TEXT,
                    retrieved_at TEXT,
                    FOREIGN KEY(post_id) REFERENCES posts(id) ON DELETE CASCADE
                )
            """)

            # Indices
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_posts_author ON posts(author_username)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_posts_created ON posts(created_at)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_posts_query ON posts(searched_query)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_posts_type ON posts(item_type)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_searches_query ON searches(query)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_content_analysis_context ON content_analysis(context_status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_verification_post_id ON verification_evidence(post_id)")

            conn.commit()

    def save_posts(self, posts: List[NormalizedPost], searched_query: Optional[str] = None) -> int:
        """Insert or update posts and comments in SQLite."""
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
                topics_json = json.dumps(post.topics) if hasattr(post, 'topics') else '[]'
                created_iso = post.created_at.isoformat() if isinstance(post.created_at, datetime) else str(post.created_at)

                likes = int(post.likes or 0)
                reposts = int(post.reposts or 0)
                shares = int(getattr(post, 'shares', reposts) or reposts or 0)
                max_shares = max(shares, reposts)

                replies = int(post.replies or 0)
                comments_count = int(getattr(post, 'comments_count', replies) or replies or 0)
                max_comments = max(comments_count, replies)

                cursor.execute("""
                    INSERT INTO posts (
                        id, platform, item_type, parent_id, text, author_username, author_name,
                        created_at, url, likes, replies, reposts, shares, comments_count, views,
                        raw_data, searched_query, collected_at,
                        sentiment_score, sentiment_label, topics
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        item_type = excluded.item_type,
                        parent_id = excluded.parent_id,
                        likes = excluded.likes,
                        replies = excluded.replies,
                        reposts = excluded.reposts,
                        shares = excluded.shares,
                        comments_count = excluded.comments_count,
                        views = excluded.views,
                        text = excluded.text,
                        collected_at = excluded.collected_at,
                        sentiment_score = excluded.sentiment_score,
                        sentiment_label = excluded.sentiment_label,
                        topics = excluded.topics
                """, (
                    post.id,
                    post.platform,
                    getattr(post, 'item_type', 'post'),
                    getattr(post, 'parent_id', None),
                    post.text,
                    post.author_username,
                    post.author_name,
                    created_iso,
                    post.url,
                    likes,
                    max_comments,
                    max_shares,
                    max_shares,
                    max_comments,
                    post.views,
                    raw_json,
                    searched_query,
                    collected_at,
                    getattr(post, 'sentiment_score', 0.0),
                    getattr(post, 'sentiment_label', 'Neutral'),
                    topics_json
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
        platform: Optional[str] = None,
        item_type: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[NormalizedPost]:
        """Fetch saved posts from SQLite, optionally filtered by keyword query, platform, and content type."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            conditions = []
            params = []

            if query:
                like_pattern = f"%{query}%"
                conditions.append("(text LIKE ? OR author_username LIKE ? OR searched_query LIKE ?)")
                params.extend([like_pattern, like_pattern, like_pattern])

            if platform and platform.lower() != "all":
                conditions.append("platform = ?")
                params.append(platform.lower().strip())

            if item_type and item_type.lower() != "all":
                conditions.append("item_type = ?")
                params.append(item_type.lower().strip())

            where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
            sql = f"SELECT * FROM posts {where_clause} ORDER BY created_at DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])

            cursor.execute(sql, params)

            rows = cursor.fetchall()
            posts = []
            for row in rows:
                raw_dict = json.loads(row["raw_data"]) if row["raw_data"] else None
                try:
                    dt = datetime.fromisoformat(row["created_at"])
                except Exception:
                    dt = datetime.now(timezone.utc)
                    
                # Extract AI topics safely
                try:
                    topics_val = row["topics"] if "topics" in row.keys() else "[]"
                    topics_list = json.loads(topics_val)
                except Exception:
                    topics_list = []

                sentiment_score = row["sentiment_score"] if "sentiment_score" in row.keys() else 0.0
                sentiment_label = row["sentiment_label"] if "sentiment_label" in row.keys() else "Neutral"
                row_item_type = row["item_type"] if "item_type" in row.keys() and row["item_type"] else "post"
                parent_id = row["parent_id"] if "parent_id" in row.keys() else None

                likes = int(row["likes"] or 0)
                reposts = int(row["reposts"] or 0) if "reposts" in row.keys() and row["reposts"] is not None else 0
                shares_val = row["shares"] if "shares" in row.keys() and row["shares"] is not None else 0
                max_shares = max(int(shares_val or 0), reposts)

                replies = int(row["replies"] or 0) if "replies" in row.keys() and row["replies"] is not None else 0
                comments_val = row["comments_count"] if "comments_count" in row.keys() and row["comments_count"] is not None else 0
                max_comments = max(int(comments_val or 0), replies)

                posts.append(NormalizedPost(
                    id=row["id"],
                    platform=row["platform"],
                    item_type=row_item_type,
                    parent_id=parent_id,
                    text=row["text"],
                    author_username=row["author_username"],
                    author_name=row["author_name"] or "",
                    created_at=dt,
                    url=row["url"],
                    likes=likes,
                    replies=max_comments,
                    reposts=max_shares,
                    shares=max_shares,
                    comments_count=max_comments,
                    views=row["views"],
                    raw_data=raw_dict,
                    sentiment_score=sentiment_score,
                    sentiment_label=sentiment_label,
                    topics=topics_list
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

            cursor.execute("SELECT COUNT(DISTINCT searched_query) FROM posts WHERE searched_query IS NOT NULL")
            unique_queries = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM searches")
            total_searches = cursor.fetchone()[0]

            cursor.execute("SELECT MIN(created_at), MAX(created_at) FROM posts")
            min_date, max_date = cursor.fetchone()

            cursor.execute("SELECT platform, COUNT(*) FROM posts GROUP BY platform")
            by_platform = {r[0]: r[1] for r in cursor.fetchall()}

            cursor.execute("SELECT item_type, COUNT(*) FROM posts GROUP BY item_type")
            by_type = {r[0]: r[1] for r in cursor.fetchall()}

            return {
                "total_posts": total_posts,
                "unique_queries": unique_queries,
                "total_searches": total_searches,
                "oldest_post": min_date,
                "newest_post": max_date,
                "posts_by_platform": by_platform,
                "posts_by_type": by_type,
            }
