"""Unit tests for NormalizedPost model and twscrape parser."""

from datetime import datetime
from types import SimpleNamespace
from app.models.post import NormalizedPost


def test_normalized_post_direct_instantiation():
    post = NormalizedPost(
        id="1234567890",
        platform="x",
        text="Admissions open at IIUI Islamabad for Fall 2026.",
        author_username="iiui_official",
        author_name="IIUI Official",
        created_at=datetime(2026, 8, 30, 12, 0, 0),
        url="https://x.com/iiui_official/status/1234567890",
        likes=45,
        replies=12,
        reposts=8,
        views=1500,
    )

    assert post.id == "1234567890"
    assert post.platform == "x"
    assert "IIUI" in post.text
    assert post.author_username == "iiui_official"
    assert post.likes == 45
    assert post.views == 1500

    summary = post.formatted_summary()
    assert "@iiui_official" in summary
    assert "Likes: 45" in summary
    assert "Views: 1,500" in summary


def test_from_twscrape_mock_tweet():
    mock_user = SimpleNamespace(username="nust_official", displayname="NUST Pakistan")
    mock_tweet = SimpleNamespace(
        id=9876543210,
        rawContent="NUST ranked among top global institutions in engineering!",
        user=mock_user,
        date=datetime(2026, 8, 25, 10, 30, 0),
        url="https://x.com/nust_official/status/9876543210",
        likeCount=120,
        replyCount=15,
        retweetCount=42,
        viewCount=8900,
    )

    post = NormalizedPost.from_twscrape(mock_tweet)

    assert post.id == "9876543210"
    assert post.author_username == "nust_official"
    assert post.author_name == "NUST Pakistan"
    assert post.likes == 120
    assert post.replies == 15
    assert post.reposts == 42
    assert post.views == 8900
    assert "NUST" in post.text
