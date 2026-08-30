"""X (Twitter) Collector implementation using twscrape with robust error handling."""

import os
import re
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime

from twscrape import API, gather, Account, Tweet, User

from app.models.post import NormalizedPost
from app.collectors.base import (
    BaseCollector,
    CollectorError,
    NoAccountError,
    AuthError,
    RateLimitError,
    NetworkError,
)

logger = logging.getLogger(__name__)


class XCollector(BaseCollector):
    """Collector for X (Twitter) leveraging twscrape with account pooling and resilience."""

    def __init__(self, db_path: str = "data/accounts.db", raise_when_no_account: bool = True):
        self.db_path = db_path
        
        # Ensure directory for accounts database exists
        db_dir = os.path.dirname(os.path.abspath(db_path))
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
            
        self.api = API(
            pool=self.db_path,
            raise_when_no_account=raise_when_no_account,
            wait_timeout=15,
            wait_interval=1,
        )

    async def check_status(self) -> Dict[str, Any]:
        """Inspect the current state of accounts in the pool."""
        try:
            stats = await self.api.pool.stats()
            accounts_info = await self.api.pool.accounts_info()
            
            # Format accounts list cleanly
            accounts_list = []
            for acc in accounts_info:
                if isinstance(acc, dict):
                    accounts_list.append(acc)
                else:
                    accounts_list.append({
                        "username": getattr(acc, "username", ""),
                        "logged_in": getattr(acc, "logged_in", False),
                        "active": getattr(acc, "active", False),
                        "last_used": str(getattr(acc, "last_used", None)),
                        "total_req": getattr(acc, "total_req", 0),
                        "error_msg": getattr(acc, "error_msg", None),
                    })
            
            is_ready = stats.get("active", 0) > 0
            
            return {
                "platform": "x",
                "ready": is_ready,
                "db_path": self.db_path,
                "stats": stats,
                "total_accounts": stats.get("total", 0),
                "active_accounts": stats.get("active", 0),
                "inactive_accounts": stats.get("inactive", 0),
                "accounts": accounts_list,
            }
        except Exception as e:
            logger.error(f"Failed to check XCollector status: {e}")
            return {
                "platform": "x",
                "ready": False,
                "db_path": self.db_path,
                "error": str(e),
                "total_accounts": 0,
                "active_accounts": 0,
                "inactive_accounts": 0,
                "accounts": [],
            }

    async def add_account_cookies(self, account_name: str, cookies: str) -> bool:
        """Add or update an account session using browser cookies (auth_token & ct0).
        
        Args:
            account_name: Local identifier/tag for the account.
            cookies: Cookie string (e.g. 'auth_token=xxx; ct0=yyy') or raw cookie header.
        """
        if not account_name or not cookies:
            raise ValueError("Both account_name and cookies are required.")
            
        clean_cookies = cookies.strip()
        
        # Verify that essential cookies exist
        if "auth_token" not in clean_cookies or "ct0" not in clean_cookies:
            raise ValueError(
                "Cookie string must contain at least 'auth_token' and 'ct0'. "
                "Please copy them from x.com DevTools (F12 -> Application -> Cookies)."
            )
            
        try:
            await self.api.pool.add_account_cookies(account_name, clean_cookies)
            logger.info(f"Successfully added/updated cookie session for account '{account_name}'.")
            return True
        except Exception as e:
            logger.error(f"Failed to add cookies for account '{account_name}': {e}")
            raise AuthError(f"Could not add cookie session: {e}") from e

    async def add_account_credentials(
        self,
        username: str,
        password: str,
        email: str,
        email_password: Optional[str] = None,
        proxy: Optional[str] = None,
    ) -> bool:
        """Add an account using username and password."""
        try:
            await self.api.pool.add_account(
                username=username,
                password=password,
                email=email,
                email_password=email_password or "",
                proxy=proxy,
            )
            return True
        except Exception as e:
            raise CollectorError(f"Failed to add account credentials: {e}") from e

    async def login_accounts(self) -> Dict[str, Any]:
        """Run login process for inactive credential-based accounts."""
        try:
            result = await self.api.pool.login_all()
            return result
        except Exception as e:
            raise AuthError(f"Login failed: {e}") from e

    async def reset_locks(self) -> None:
        """Reset rate limit locks on all accounts in the pool."""
        try:
            await self.api.pool.reset_locks()
        except Exception as e:
            raise CollectorError(f"Failed to reset locks: {e}") from e

    async def delete_account(self, username: str) -> bool:
        """Delete an account from the pool."""
        try:
            await self.api.pool.delete_accounts([username])
            return True
        except Exception as e:
            raise CollectorError(f"Failed to delete account {username}: {e}") from e

    async def search(
        self,
        query: str,
        limit: int = 20,
        product: str = "Latest",
        **kwargs: Any
    ) -> List[NormalizedPost]:
        """Search X for matching posts.
        
        Args:
            query: The search term (e.g. "IIUI", "COMSATS", "\"International Islamic University\"").
            limit: Target number of posts (default: 20).
            product: Search tab - "Latest" (default) or "Top".
            
        Returns:
            List of NormalizedPost objects.
        """
        clean_query = query.strip()
        if not clean_query:
            return []

        # 1. Pre-check account readiness
        status = await self.check_status()
        if status.get("active_accounts", 0) == 0:
            raise NoAccountError(
                "No active X/Twitter accounts found in the pool.\n"
                "To search X, you must add at least one account session cookie:\n"
                "  1. Open x.com in your browser (logged in).\n"
                "  2. Open DevTools (F12) -> Application -> Cookies -> https://x.com\n"
                "  3. Copy 'auth_token' and 'ct0' values.\n"
                "  4. Add them via CLI: python run_cli.py add-cookie <name> \"auth_token=...; ct0=...\"\n"
                "     or via the local Web UI Account Manager."
            )

        # 2. Execute search with twscrape
        try:
            search_gen = self.api.search(
                clean_query,
                limit=limit,
                kv={"product": product},
            )
            raw_tweets = await gather(search_gen)
            
            posts: List[NormalizedPost] = []
            for tweet in raw_tweets:
                try:
                    post = NormalizedPost.from_twscrape(tweet)
                    posts.append(post)
                except Exception as parse_err:
                    logger.warning(f"Error parsing tweet: {parse_err}")
                    continue

            return posts

        except Exception as e:
            err_str = str(e).lower()
            if "no active account" in err_str or "noaccount" in err_str:
                raise NoAccountError("All accounts in pool are inactive or locked.") from e
            elif "rate limit" in err_str or "429" in err_str:
                raise RateLimitError("X rate limit reached. Reset locks or add additional accounts.") from e
            elif "auth" in err_str or "unauthorized" in err_str or "401" in err_str or "403" in err_str:
                raise AuthError("Authentication failed. Session cookies may have expired.") from e
            elif "connection" in err_str or "timeout" in err_str or "network" in err_str:
                raise NetworkError(f"Network error while reaching X: {e}") from e
            else:
                raise CollectorError(f"Error searching X for '{clean_query}': {e}") from e
