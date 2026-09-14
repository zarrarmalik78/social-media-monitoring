"""AI Sentiment and Topic Classification Engine."""

import re
from typing import Dict, List, Any
try:
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
except ImportError:
    # Fallback if uninstalled, though we pip installed it
    class SentimentIntensityAnalyzer:
        def polarity_scores(self, text: str) -> Dict[str, float]:
            return {"compound": 0.0, "pos": 0.0, "neu": 1.0, "neg": 0.0}

class SocialAnalyzer:
    """Lightweight NLP processor for sentiment and topic modeling."""

    def __init__(self):
        self.vader = SentimentIntensityAnalyzer()
        
        # Domain-specific keyword heuristics for universities
        self.topic_keywords = {
            "Admissions & Fees": ["admission", "apply", "deadline", "fee", "merit list", "eligibility", "scholarship", "prospectus", "enroll", "aggregate", "test", "nts", "nat"],
            "Academics & Research": ["exam", "result", "thesis", "study", "department", "degree", "bs", "ms", "phd", "assignment", "faculty", "professor", "gpa", "cgpa", "midterm", "final", "quiz"],
            "Campus Life & Events": ["event", "sports", "seminar", "competition", "hackathon", "society", "festival", "trip", "welcome party", "farewell", "societies"],
            "Complaints & Issues": ["worst", "issue", "problem", "strike", "protest", "bad", "terrible", "transport", "hostel", "management", "slow", "pathetic", "unprofessional", "scam", "unfair"],
            "Announcements": ["official", "notification", "holiday", "closed", "schedule", "timetable", "update", "notice"]
        }

    def analyze_sentiment(self, text: str) -> Dict[str, Any]:
        """Analyze text sentiment and return score and label."""
        if not text:
            return {"score": 0.0, "label": "Neutral"}
        
        # VADER compound score ranges from -1 (most extreme negative) to +1 (most extreme positive)
        scores = self.vader.polarity_scores(text)
        compound = scores["compound"]
        
        if compound >= 0.05:
            label = "Positive"
        elif compound <= -0.05:
            label = "Negative"
        else:
            label = "Neutral"
            
        return {"score": compound, "label": label}

    def extract_topics(self, text: str) -> List[str]:
        """Extract matching topics based on heuristic keywords."""
        if not text:
            return []
            
        text_lower = text.lower()
        matched_topics = []
        
        # Pre-compile a simple word boundary search to avoid partial matches
        # but for simplicity and speed, 'in' string search is often enough if keywords are distinct,
        # but regex word boundary is safer.
        for topic, keywords in self.topic_keywords.items():
            for kw in keywords:
                if re.search(r'\b' + re.escape(kw) + r'\b', text_lower):
                    matched_topics.append(topic)
                    break # One match is enough per category
                    
        return matched_topics

    def analyze_post(self, text: str) -> Dict[str, Any]:
        """Perform full analysis on a post's text."""
        sentiment = self.analyze_sentiment(text)
        topics = self.extract_topics(text)
        
        return {
            "sentiment_score": sentiment["score"],
            "sentiment_label": sentiment["label"],
            "topics": topics
        }

    def enrich_posts(self, posts: List[Any]) -> None:
        """Enrich a list of NormalizedPost objects with sentiment and topic intelligence in-place."""
        for p in posts:
            res = self.analyze_post(getattr(p, "text", ""))
            p.sentiment_score = res["sentiment_score"]
            p.sentiment_label = res["sentiment_label"]
            p.topics = res["topics"]

# Singleton instance
analyzer = SocialAnalyzer()

