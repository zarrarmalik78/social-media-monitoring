"""X (Twitter) Collector implementation with modern GraphQL POST search and account pooling."""

import os
import json
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime

from twscrape import API, Account, Tweet, User
from twscrape.models import parse_tweets
from twscrape.xclid import XClIdGen
from twscrape.utils import encode_params

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

# Search features matching modern X client GraphQL schema
SEARCH_FEATURES = {
    "rweb_video_screen_enabled": True,
    "rweb_cashtags_enabled": True,
    "profile_label_improvements_pcf_label_in_post_enabled": True,
    "responsive_web_profile_redirect_enabled": True,
    "rweb_tipjar_consumption_enabled": True,
    "verified_phone_label_enabled": False,
    "creator_subscriptions_tweet_preview_api_enabled": True,
    "responsive_web_graphql_timeline_navigation_enabled": True,
    "premium_content_api_read_enabled": True,
    "communities_web_enable_tweet_community_results_fetch": True,
    "c9s_tweet_anatomy_moderator_badge_enabled": True,
    "responsive_web_grok_analyze_button_fetch_trends_enabled": False,
    "responsive_web_grok_analyze_post_followups_enabled": True,
    "rweb_cashtags_composer_attachment_enabled": True,
    "responsive_web_jetfuel_frame": True,
    "responsive_web_grok_share_attachment_enabled": False,
    "responsive_web_grok_annotations_enabled": True,
    "articles_preview_enabled": False,
    "responsive_web_edit_tweet_api_enabled": True,
    "rweb_conversational_replies_downvote_enabled": True,
    "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
    "view_counts_everywhere_api_enabled": True,
    "longform_notetweets_consumption_enabled": True,
    "responsive_web_twitter_article_tweet_consumption_enabled": True,
    "content_disclosure_indicator_enabled": True,
    "content_disclosure_ai_generated_indicator_enabled": True,
    "responsive_web_grok_show_grok_translated_post": True,
    "responsive_web_grok_analysis_button_from_backend": False,
    "post_ctas_fetch_enabled": True,
    "freedom_of_speech_not_reach_fetch_enabled": True,
    "standardized_nudges_misinfo": True,
    "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
    "longform_notetweets_rich_text_read_enabled": True,
    "longform_notetweets_inline_media_enabled": True,
    "responsive_web_grok_image_annotation_enabled": False,
    "responsive_web_grok_imagine_annotation_enabled": False,
    "responsive_web_grok_community_note_auto_translation_is_enabled": False,
    "responsive_web_enhance_cards_enabled": False,
}

OP_SEARCH_TIMELINE = "hyPfJYJ_XAtDYoslQc-Rgg/SearchTimeline"
QUERY_ID_SEARCH_TIMELINE = "hyPfJYJ_XAtDYoslQc-Rgg"


class XCollector(BaseCollector):
    """Collector for X (Twitter) leveraging twscrape with account pooling, resilient HTTP POST search, and auto-rotation."""

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

    def _extract_cursor(self, data: dict, cursor_type: str = "Bottom") -> Optional[str]:
        """Extract timeline pagination cursor from GraphQL response payload."""
        try:
            instructions = (
                data.get("data", {})
                .get("search_by_raw_query", {})
                .get("search_timeline", {})
                .get("timeline", {})
                .get("instructions", [])
            )
            for inst in instructions:
                entries = inst.get("entries", [])
                for entry in entries:
                    entry_id = entry.get("entryId", "")
                    if f"cursor-{cursor_type.lower()}" in entry_id.lower():
                        content = entry.get("content", {})
                        return content.get("value") or content.get("itemContent", {}).get("value")
        except Exception as e:
            logger.debug(f"Could not extract cursor from response: {e}")
        return None

    async def _execute_post_search(
        self,
        query: str,
        limit: int = 20,
        product: str = "Latest",
    ) -> List[NormalizedPost]:
        """Direct GraphQL POST search pipeline resolving current X API requirements."""
        accounts = await self.api.pool.get_all()
        active_accounts = [acc for acc in accounts if acc.active and acc.cookies]
        
        if not active_accounts:
            raise NoAccountError(
                "No active accounts with cookies found in pool.\n"
                "Please add a valid session cookie using: python run_cli.py add-cookie <name> \"auth_token=...; ct0=...\""
            )

        account = active_accounts[0]
        client = account.make_client()
        
        try:
            gen = await XClIdGen.create(cookies=account.cookies)
        except Exception as e:
            logger.warning(f"Error initializing XClIdGen: {e}")
            gen = None

        path = f"/i/api/graphql/{OP_SEARCH_TIMELINE}"
        url = f"https://x.com{path}"

        all_posts: List[NormalizedPost] = []
        seen_ids = set()
        cursor: Optional[str] = None

        try:
            while len(all_posts) < limit:
                batch_count = min(20, limit - len(all_posts))
                variables = {
                    "rawQuery": query,
                    "count": batch_count,
                    "querySource": "typed_query",
                    "product": product,
                }
                if cursor:
                    variables["cursor"] = cursor

                payload = {
                    "variables": variables,
                    "features": SEARCH_FEATURES,
                    "queryId": QUERY_ID_SEARCH_TIMELINE,
                }

                headers = {
                    "referer": f"https://x.com/search?q={query}&src=typed_query&f=live",
                    "content-type": "application/json",
                }
                if gen:
                    try:
                        headers["x-client-transaction-id"] = gen.calc("POST", path)
                    except Exception as calc_err:
                        logger.debug(f"Transaction ID calculation warning: {calc_err}")

                rep = await client.request("POST", url, json=payload, headers=headers)

                if rep.status_code == 429:
                    raise RateLimitError("Rate limit reached for SearchTimeline.")
                elif rep.status_code in (401, 403):
                    raise AuthError("Authentication failed on X Search endpoint. Please refresh cookies.")
                elif rep.status_code != 200:
                    logger.warning(f"X Search returned HTTP {rep.status_code}: {rep.text[:200]}")
                    break

                data = rep.json()
                raw_tweets = list(parse_tweets(data, limit=batch_count))
                if not raw_tweets:
                    break

                new_count = 0
                for tweet in raw_tweets:
                    t_id = str(tweet.id)
                    if t_id not in seen_ids:
                        seen_ids.add(t_id)
                        try:
                            post = NormalizedPost.from_twscrape(tweet)
                            all_posts.append(post)
                            new_count += 1
                        except Exception as p_err:
                            logger.warning(f"Error normalizing tweet {t_id}: {p_err}")

                    if len(all_posts) >= limit:
                        break

                if new_count == 0:
                    break

                next_cursor = self._extract_cursor(data, "Bottom")
                if not next_cursor or next_cursor == cursor:
                    break
                cursor = next_cursor

            return all_posts

        finally:
            await client.aclose()

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

        # 2. Execute search
        try:
            return await self._execute_post_search(
                query=clean_query,
                limit=limit,
                product=product,
            )
        except (NoAccountError, AuthError, RateLimitError, NetworkError):
            raise
        except Exception as e:
            err_str = str(e).lower()
            if "rate limit" in err_str or "429" in err_str:
                raise RateLimitError("X rate limit reached. Reset locks or add additional accounts.") from e
            elif "auth" in err_str or "unauthorized" in err_str or "401" in err_str or "403" in err_str:
                raise AuthError("Authentication failed. Session cookies may have expired.") from e
            elif "connection" in err_str or "timeout" in err_str or "network" in err_str:
                raise NetworkError(f"Network error while reaching X: {e}") from e
            else:
                raise CollectorError(f"Error searching X for '{clean_query}': {e}") from e

