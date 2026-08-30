"""Normalized post data model for unified cross-platform representation."""

from datetime import datetime, timezone
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class NormalizedPost(BaseModel):
    """Standardized representation of a social media post across all platforms."""

    id: str = Field(..., description="Unique platform post ID")
    platform: str = Field(default="x", description="Social media platform identifier (e.g. 'x')")
    text: str = Field(..., description="Full text content of the post")
    author_username: str = Field(..., description="Author's handle/username (without @)")
    author_name: str = Field(default="", description="Author's display name")
    created_at: datetime = Field(..., description="Publication timestamp (UTC)")
    url: str = Field(..., description="Canonical permalink to the post")
    likes: int = Field(default=0, description="Number of likes/favorites")
    replies: int = Field(default=0, description="Number of direct replies")
    reposts: int = Field(default=0, description="Number of retweets/reposts")
    views: Optional[int] = Field(default=None, description="Impression/view count if available")
    raw_data: Optional[Dict[str, Any]] = Field(default=None, description="Original raw response payload")

    @classmethod
    def from_twscrape(cls, tweet: Any) -> "NormalizedPost":
        """Convert a twscrape Tweet object to NormalizedPost."""
        # Tweet attributes in twscrape:
        # id: int, rawContent: str, user: User (username, displayname), date: datetime, url: str
        # likeCount: int, replyCount: int, retweetCount: int, viewCount: int/None
        user = getattr(tweet, "user", None)
        username = getattr(user, "username", "") if user else ""
        displayname = getattr(user, "displayname", "") if user else ""
        
        post_id = str(getattr(tweet, "id", ""))
        text = getattr(tweet, "rawContent", None) or getattr(tweet, "renderedContent", None) or ""
        created_at = getattr(tweet, "date", None) or datetime.now(timezone.utc)
        url = getattr(tweet, "url", f"https://x.com/{username}/status/{post_id}" if username and post_id else "")
        
        likes = getattr(tweet, "likeCount", 0) or 0
        replies = getattr(tweet, "replyCount", 0) or 0
        reposts = getattr(tweet, "retweetCount", 0) or 0
        views = getattr(tweet, "viewCount", None)

        # Raw data extraction safely
        raw_dict = None
        if hasattr(tweet, "dict"):
            try:
                raw_dict = tweet.dict()
            except Exception:
                pass
        elif hasattr(tweet, "__dict__"):
            raw_dict = {k: v for k, v in tweet.__dict__.items() if not k.startswith("_")}

        return cls(
            id=post_id,
            platform="x",
            text=text,
            author_username=username,
            author_name=displayname,
            created_at=created_at,
            url=url,
            likes=likes,
            replies=replies,
            reposts=reposts,
            views=views,
            raw_data=raw_dict,
        )

    def formatted_summary(self) -> str:
        """Return a formatted string representation for terminal CLI display."""
        date_str = self.created_at.strftime("%Y-%m-%d %H:%M:%S")
        views_str = f" | Views: {self.views:,}" if self.views is not None else ""
        return (
            f"--------------------------------------------------\n"
            f"@{self.author_username} ({self.author_name}) • {date_str}\n"
            f"\"{self.text}\"\n"
            f"Likes: {self.likes:,} | Replies: {self.replies:,} | Reposts: {self.reposts:,}{views_str}\n"
            f"Post ID: {self.id}\n"
            f"Link: {self.url}\n"
            f"--------------------------------------------------"
        )
