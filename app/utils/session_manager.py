"""Multi-platform session cookie manager for local SQLite storage and rotation."""

import os
import sqlite3
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class SessionManager:
    """Manages session cookies and credentials for multiple social platforms in SQLite."""

    def __init__(self, db_path: str = "data/accounts.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        """Create platform_sessions table if it doesn't exist."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS platform_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    platform TEXT NOT NULL,
                    account_name TEXT NOT NULL,
                    cookies TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    last_used TEXT,
                    error_msg TEXT,
                    total_req INTEGER NOT NULL DEFAULT 0,
                    UNIQUE(platform, account_name)
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_platform_sessions ON platform_sessions(platform, active)")
            conn.commit()

    def add_session(self, platform: str, account_name: str, cookies: str) -> bool:
        """Add or update a platform session cookie."""
        clean_platform = platform.lower().strip()
        clean_name = account_name.strip()
        clean_cookies = cookies.strip()

        if not clean_platform or not clean_name or not clean_cookies:
            raise ValueError("Platform, account_name, and cookies are all required.")

        now_iso = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO platform_sessions (
                    platform, account_name, cookies, active, created_at, error_msg
                ) VALUES (?, ?, ?, 1, ?, NULL)
                ON CONFLICT(platform, account_name) DO UPDATE SET
                    cookies = excluded.cookies,
                    active = 1,
                    error_msg = NULL
            """, (clean_platform, clean_name, clean_cookies, now_iso))
            conn.commit()
            logger.info(f"Saved session for platform '{clean_platform}', account '{clean_name}'.")
            return True

    def get_active_session(self, platform: str) -> Optional[Dict[str, Any]]:
        """Retrieve the primary active session for a platform and record usage."""
        clean_platform = platform.lower().strip()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM platform_sessions 
                WHERE platform = ? AND active = 1 
                ORDER BY last_used ASC NULLS FIRST 
                LIMIT 1
            """, (clean_platform,))
            row = cursor.fetchone()
            if not row:
                return None

            now_iso = datetime.now(timezone.utc).isoformat()
            session = dict(row)
            session["total_req"] = session.get("total_req", 0) + 1
            session["last_used"] = now_iso
            # Update last_used and total_req
            cursor.execute("""
                UPDATE platform_sessions 
                SET last_used = ?, total_req = total_req + 1 
                WHERE id = ?
            """, (now_iso, session["id"]))
            conn.commit()
            return session

    def mark_error(self, platform: str, account_name: str, error_msg: str, deactivate: bool = False) -> None:
        """Record an error message on a session."""
        clean_platform = platform.lower().strip()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            active_val = 0 if deactivate else 1
            cursor.execute("""
                UPDATE platform_sessions 
                SET error_msg = ?, active = ? 
                WHERE platform = ? AND account_name = ?
            """, (error_msg, active_val, clean_platform, account_name))
            conn.commit()

    def list_sessions(self, platform: Optional[str] = None) -> List[Dict[str, Any]]:
        """List sessions across all or specific platforms."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if platform and platform.lower() != "all":
                cursor.execute("""
                    SELECT id, platform, account_name, active, created_at, last_used, error_msg, total_req 
                    FROM platform_sessions 
                    WHERE platform = ? 
                    ORDER BY created_at DESC
                """, (platform.lower().strip(),))
            else:
                cursor.execute("""
                    SELECT id, platform, account_name, active, created_at, last_used, error_msg, total_req 
                    FROM platform_sessions 
                    ORDER BY platform, created_at DESC
                """)
            return [dict(r) for r in cursor.fetchall()]

    def delete_session(self, platform: str, account_name: str) -> bool:
        """Remove a session from the store."""
        clean_platform = platform.lower().strip()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                DELETE FROM platform_sessions 
                WHERE platform = ? AND account_name = ?
            """, (clean_platform, account_name))
            conn.commit()
            return cursor.rowcount > 0

    @staticmethod
    def parse_cookie_dict(cookie_str: str) -> Dict[str, str]:
        """Convert standard 'name=val; name2=val2' cookie string into a dictionary."""
        cookies = {}
        for item in cookie_str.split(";"):
            item = item.strip()
            if "=" in item:
                k, v = item.split("=", 1)
                cookies[k.strip()] = v.strip()
        return cookies
