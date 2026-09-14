"""Normalized post data model for unified cross-platform representation."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class NormalizedPost(BaseModel):
    """Standardized representation of a social media post or comment across all platforms."""

    id: str = Field(..., description="Unique platform post or comment ID")
    platform: str = Field(default="x", description="Social media platform identifier (e.g. 'x', 'reddit', 'youtube')")
    item_type: str = Field(default="post", description="Content type: 'post' or 'comment'")
    parent_id: Optional[str] = Field(default=None, description="Parent post/thread ID if this is a reply or comment")
    
    text: str = Field(..., description="Full text content of the post or comment")
    author_username: str = Field(..., description="Author's handle/username (without @)")
    author_name: str = Field(default="", description="Author's display name")
    created_at: datetime = Field(..., description="Publication timestamp (UTC)")
    url: str = Field(..., description="Canonical permalink to the post or comment")
    
    # Engagement Metrics
    likes: int = Field(default=0, description="Number of likes/upvotes/favorites")
    replies: int = Field(default=0, description="Number of direct replies/comments")
    reposts: int = Field(default=0, description="Number of retweets/reposts/shares")
    shares: int = Field(default=0, description="Number of shares (synced with reposts)")
    comments_count: int = Field(default=0, description="Total comment count (synced with replies)")
    views: Optional[int] = Field(default=None, description="Impression/view count if available")
    
    # AI Intelligence (Optional to remain backward compatible)
    sentiment_score: float = Field(default=0.0, description="Sentiment polarity score (-1.0 to 1.0)")
    sentiment_label: str = Field(default="Neutral", description="Sentiment label (Positive, Neutral, Negative)")
    topics: List[str] = Field(default_factory=list, description="List of categorized topics")
    media_urls: List[str] = Field(default_factory=list, description="Extracted media image URLs for on-demand verification")
    
    raw_data: Optional[Dict[str, Any]] = Field(default=None, description="Original raw response payload")

    @classmethod
    def from_twscrape(cls, tweet: Any) -> "NormalizedPost":
        """Convert a twscrape Tweet object or raw dictionary to NormalizedPost."""
        def get_val(obj, *keys, default=None):
            if isinstance(obj, dict):
                for k in keys:
                    if k in obj and obj[k] is not None:
                        return obj[k]
            else:
                for k in keys:
                    v = getattr(obj, k, None)
                    if v is not None:
                        return v
            return default

        user = getattr(tweet, "user", None) if not isinstance(tweet, dict) else tweet.get("user")
        username = get_val(user, "username", default="") if user else ""
        displayname = get_val(user, "displayname", "name", default="") if user else ""
        
        post_id = str(get_val(tweet, "id", "id_str", default=""))
        text = get_val(tweet, "rawContent", "renderedContent", "full_text", "text", default="")
        created_at = get_val(tweet, "date", "created_at", default=None) or datetime.now(timezone.utc)
        url = get_val(tweet, "url", default="") or (f"https://x.com/{username}/status/{post_id}" if username and post_id else "")
        
        likes = int(get_val(tweet, "likeCount", "favorite_count", "favoriteCount", "likes", default=0) or 0)
        replies = int(get_val(tweet, "replyCount", "reply_count", "replies", default=0) or 0)
        reposts = int(get_val(tweet, "retweetCount", "retweet_count", "reposts", default=0) or 0)
        
        views_raw = get_val(tweet, "viewCount", "view_count", "views", default=None)
        views = None
        if views_raw is not None:
            try:
                views = int(views_raw)
            except Exception:
                views = None

        # Detect if tweet is a reply/comment to another tweet
        in_reply_to = get_val(tweet, "inReplyToTweetId", "in_reply_to_status_id_str", default=None)
        item_type = "comment" if in_reply_to else "post"
        parent_id = str(in_reply_to) if in_reply_to else None

        raw_dict = None
        if hasattr(tweet, "dict"):
            try:
                raw_dict = tweet.dict()
            except Exception:
                pass
        elif isinstance(tweet, dict):
            raw_dict = tweet
        elif hasattr(tweet, "__dict__"):
            raw_dict = {k: v for k, v in tweet.__dict__.items() if not k.startswith("_")}

        return cls(
            id=post_id,
            platform="x",
            item_type=item_type,
            parent_id=parent_id,
            text=text,
            author_username=username,
            author_name=displayname,
            created_at=created_at,
            url=url,
            likes=likes,
            replies=replies,
            reposts=reposts,
            shares=reposts,
            comments_count=replies,
            views=views,
            raw_data=raw_dict,
        )

    def formatted_summary(self) -> str:
        """Return a formatted string representation for terminal CLI display."""
        date_str = self.created_at.strftime("%Y-%m-%d %H:%M:%S")
        views_str = f" | Views: {self.views:,}" if self.views is not None else ""
        type_tag = f" [{self.item_type.upper()}]" if self.item_type != "post" else ""
        return (
            f"--------------------------------------------------\n"
            f"@{self.author_username} ({self.author_name}){type_tag} • {date_str}\n"
            f"\"{self.text}\"\n"
            f"Likes: {self.likes:,} | Replies/Comments: {self.replies:,} | Retweets/Shares: {self.reposts:,}{views_str}\n"
            f"ID: {self.id} | Link: {self.url}\n"
            f"--------------------------------------------------"
        )
