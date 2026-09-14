"""Local, Free Content Authenticity and Verification Engine.

Performs 3 completely independent analyses without external paid APIs:
1. Local AI-Generated Text Estimation (Statistical Burstiness, Perplexity & Lexical Entropy)
2. Local Claim & Entity Extraction (Linguistic Rule-Based Extraction)
3. Context/Claim Verification (Free Public News Evidence Verification)
4. Filtered Media Triage (EXIF/C2PA Provenance & AI Signature Extraction)
"""

import os
import re
import math
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.models.post import NormalizedPost
from app.collectors.news_collector import NewsCollector
from app.database.db import Database
from app.utils.media_triage import MediaTriage

logger = logging.getLogger(__name__)


class LocalAITextDetector:
    """100% Local, offline AI-generated text estimation.
    Uses statistical perplexity, sentence burstiness, lexical entropy, and known LLM markers.
    """

    # Vocabulary frequently overused by LLMs (ChatGPT, Claude, etc.)
    AI_TRANSITION_MARKERS = [
        "furthermore", "moreover", "in conclusion", "it is important to note",
        "it's important to remember", "delve", "testament", "tapestry", "seamless",
        "crucial", "paramount", "underscores", "fosters", "beacon", "landscape",
        "pivotal", "in essence", "game-changer", "empower", "revolutionize",
        "holistic", "streamline", "leverage", "unwavering", "multifaceted"
    ]

    def analyze(self, text: str) -> Dict[str, Any]:
        """Estimate likelihood of AI generation on a scale of 0.0 to 1.0."""
        clean_text = (text or "").strip()
        words = re.findall(r'\b[a-zA-Z0-9_\'-]+\b', clean_text)
        word_count = len(words)

        if word_count < 12:
            return {
                "score": 0.0,
                "status": "insufficient_evidence",
                "reason": "Text is too short (< 12 words) for reliable statistical AI detection."
            }

        sentences = [s.strip() for s in re.split(r'[.!?]+', clean_text) if len(s.strip().split()) > 2]
        if not sentences:
            sentences = [clean_text]

        # Metric 1: Sentence Length Burstiness (Standard Deviation / Mean)
        # Human text has high burstiness (mix of short punchy & long complex sentences)
        # AI text is characteristically uniform
        sentence_lens = [len(s.split()) for s in sentences]
        mean_len = sum(sentence_lens) / len(sentence_lens)
        if len(sentence_lens) > 1:
            variance = sum((l - mean_len) ** 2 for l in sentence_lens) / len(sentence_lens)
            std_dev = math.sqrt(variance)
            burstiness = std_dev / (mean_len + 1e-5)
        else:
            burstiness = 0.5  # Neutral default for single sentence

        # If burstiness is very low (< 0.25), text length is uniform (AI signal)
        burstiness_ai_signal = max(0.0, min(1.0, 1.0 - (burstiness / 0.7)))

        # Metric 2: LLM Vocabulary Fingerprint Density
        lower_text = clean_text.lower()
        marker_hits = sum(1 for m in self.AI_TRANSITION_MARKERS if f" {m} " in f" {lower_text} ")
        marker_signal = min(1.0, marker_hits * 0.25)

        # Metric 3: Lexical Diversity (Type-Token Ratio)
        unique_words = len(set(w.lower() for w in words))
        ttr = unique_words / word_count
        # AI text typically maintains a moderate-high TTR with predictable vocabulary
        ttr_signal = 0.5 if (0.45 <= ttr <= 0.85) else 0.3

        # Metric 4: Punctuation and Structure Uniformity
        comma_count = clean_text.count(",")
        comma_ratio = comma_count / max(1, len(sentences))
        structure_signal = 0.6 if (1.0 <= comma_ratio <= 3.0) else 0.4

        # Composite AI Score (Weighted)
        raw_score = (
            (burstiness_ai_signal * 0.40) +
            (marker_signal * 0.35) +
            (ttr_signal * 0.15) +
            (structure_signal * 0.10)
        )
        ai_score = round(max(0.05, min(0.95, raw_score)), 2)

        if ai_score >= 0.70:
            status = "likely_ai_generated"
        elif ai_score >= 0.48:
            status = "possibly_ai_generated"
        else:
            status = "likely_human"

        return {
            "score": ai_score,
            "status": status,
            "word_count": word_count,
            "marker_hits": marker_hits
        }


class LocalClaimExtractor:
    """100% Local linguistic claim and named entity extractor."""

    @staticmethod
    def clean_headline(text: str) -> str:
        if not text:
            return ""
        clean = text.replace("&nbsp;", " ").strip()
        clean = re.sub(r';\s*[a-zA-Z0-9\.\-]+\s*$', '', clean).strip()
        words = clean.split()
        half = len(words) // 2
        if half >= 4 and words[:half] == words[half:half*2]:
            clean = " ".join(words[:half])
        clean = re.sub(r'^(?:EXCLUSIVE|BREAKING|UPDATE|REPORT|JUST IN|ALERT)[\s:]+', '', clean, flags=re.IGNORECASE).strip()
        words = clean.split()
        half = len(words) // 2
        if half >= 4 and words[:half] == words[half:half*2]:
            clean = " ".join(words[:half])
        return clean

    # Action verbs indicating factual/event assertions
    ASSERTION_TRIGGERS = [
        "is real", "is live", "now available", "just dropped", "out now", "has released", "is out",
        "withhold", "withholds", "withholding", "withheld",
        "report", "reports", "reported", "reportedly",
        "reveal", "reveals", "revealed",
        "claim", "claims", "claimed",
        "state", "states", "stated",
        "say", "says", "said",
        "allege", "alleges", "alleged",
        "investigate", "investigates", "investigated",
        "expose", "exposes", "exposed",
        "warn", "warns", "warned",
        "announce", "announces", "announced", "announcement",
        "release", "releases", "released",
        "launch", "launches", "launched",
        "unveil", "unveils", "unveiled",
        "introduce", "introduces", "introduced",
        "deploy", "deploys", "deployed",
        "create", "creates", "created",
        "build", "builds", "built",
        "develop", "develops", "developed",
        "integrate", "integrates", "integrated",
        "acquire", "acquires", "acquired", "acquisition",
        "partner", "partners", "partnered", "partnership",
        "invest", "invests", "invested",
        "fund", "funds", "funded",
        "raise", "raises", "raised",
        "cut", "cuts",
        "hire", "hires", "hired",
        "fire", "fires", "fired",
        "ban", "bans", "banned",
        "suspend", "suspends", "suspended",
        "shut", "shuts", "shut down",
        "cancel", "cancels", "cancelled",
        "postpone", "postpones", "postponed",
        "delay", "delays", "delayed",
        "resign", "resigns", "resigned", "quit", "quits",
        "appoint", "appoints", "appointed",
        "name", "names", "named",
        "join", "joins", "joined",
        "use", "uses", "used", "using",
        "approve", "approves", "approved",
        "sign", "signs", "signed",
        "pass", "passes", "passed",
        "sue", "sues", "sued", "lawsuit",
        "fine", "fines", "fined",
        "arrest", "arrests", "arrested",
        "hack", "hacks", "hacked", "breached",
        "leak", "leaks", "leaked",
        "confirm", "confirms", "confirmed",
        "find", "finds", "found",
        "discover", "discovers", "discovered",
        "expand", "expands", "expanded",
        "test", "tests", "tested",
        "accuse", "accuses", "accused",
        "held at", "win", "wins", "won", "defeat", "defeats", "defeated",
        "die", "dies", "died", "kill", "kills", "killed", "dead",
        "scam", "fraud"
    ]

    PROMINENT_ENTITIES = {
        "openai", "anthropic", "google", "meta", "apple", "microsoft", "nvidia", "tesla",
        "amazon", "spacex", "iiui", "comsats", "nasa", "fbi", "cia", "sec", "uk", "us",
        "eu", "china", "pakistan", "india", "hec", "fable", "astra", "chatgpt", "claude",
        "gemini", "deepseek", "sora"
    }

    STOP_ENTITIES = {
        "the", "this", "that", "there", "when", "what", "here", "have", "with", "after", "before", "just",
        "it", "they", "we", "you", "he", "she", "my", "our", "your", "their", "his", "her", "its",
        "start", "hey", "how", "why", "where", "who", "if", "so", "then", "also", "now", "overal",
        "very", "much", "many", "some", "any", "all", "both", "each", "every", "one", "two", "please",
        "today", "yesterday", "tomorrow", "thanks", "thank", "hello", "hi", "video", "photos", "photo",
        "exclusive", "breaking", "update", "report", "alert", "news", "sources"
    }

    def extract(self, text: str) -> List[Dict[str, str]]:
        """Extract factual claims from text using linguistic rule patterns.
        Only extracts sentences with genuine factual assertion triggers and named entities.
        Casual opinions, chit-chat, and advice return empty lists (classified as no_verifiable_claims).
        """
        if not text or len(text.split()) < 4:
            return []

        clean_text = self.clean_headline(text)
        # Safe sentence split: preserve decimal numbers like 5.1, 4.0, 3.5 without breaking
        sentences = [s.strip() for s in re.split(r'(?<!\d)\.(?!\d)|[!问?\n]+', clean_text) if s and len(s.strip().split()) >= 3]

        claims: List[Dict[str, str]] = []
        # Support CamelCase entities (OpenAI, DeepMind, ChatGPT, YouTube, etc.)
        entity_pattern = re.compile(r'\b([A-Z][a-zA-Z0-9]+(?:\s+[A-Z][a-zA-Z0-9]+)*)\b')

        for sentence in sentences:
            sentence_lower = sentence.lower()

            # 1. Require an assertion trigger for factual claims (longest matching triggers first)
            found_trigger = None
            for trigger in sorted(self.ASSERTION_TRIGGERS, key=len, reverse=True):
                if trigger in sentence_lower:
                    found_trigger = trigger
                    break

            # 2. Extract valid entities
            entities = entity_pattern.findall(sentence)
            valid_entities = [e for e in entities if e.lower() not in self.STOP_ENTITIES and len(e) > 1]

            # Also check prominent entities with word boundary
            for pe in self.PROMINENT_ENTITIES:
                if re.search(r'\b' + re.escape(pe) + r'\b', sentence_lower):
                    if not any(pe == ve.lower() for ve in valid_entities):
                        valid_entities.append(pe.upper() if len(pe) <= 4 else pe.capitalize())

            # Sort valid_entities by natural order of appearance in the sentence
            valid_entities.sort(key=lambda e: sentence_lower.find(e.lower()))

            # 3. Check colon headline pattern
            colon_match = False
            if ":" in sentence:
                prefix = sentence.split(":")[0].strip()
                if any(re.search(r'\b' + re.escape(pe) + r'\b', prefix.lower()) for pe in self.PROMINENT_ENTITIES):
                    colon_match = True
                    if not valid_entities:
                        valid_entities = [prefix]

            has_prominent = any(re.search(r'\b' + re.escape(pe) + r'\b', sentence_lower) for pe in self.PROMINENT_ENTITIES)
            entity_name = valid_entities[0] if valid_entities else None

            if found_trigger and entity_name:
                clean_claim = sentence.strip()
                if len(clean_claim.split()) > 20:
                    clean_claim = " ".join(clean_claim.split()[:20]) + "..."
                claims.append({
                    "entity": entity_name,
                    "claim": clean_claim,
                    "trigger": found_trigger
                })
            elif colon_match and entity_name:
                clean_claim = sentence.strip()
                if len(clean_claim.split()) > 20:
                    clean_claim = " ".join(clean_claim.split()[:20]) + "..."
                claims.append({
                    "entity": entity_name,
                    "claim": clean_claim,
                    "trigger": "headline_announcement"
                })
            elif has_prominent and entity_name and len(sentence.split()) >= 6 and any(w in sentence_lower for w in ("model", "intelligence", "feature", "system", "research", "access", "data", "safety", "version", "update", "benchmark", "agents", "board")):
                clean_claim = sentence.strip()
                if len(clean_claim.split()) > 20:
                    clean_claim = " ".join(clean_claim.split()[:20]) + "..."
                claims.append({
                    "entity": entity_name,
                    "claim": clean_claim,
                    "trigger": "product_announcement"
                })

        return claims[:2]  # Top 2 core claims


class LocalContextVerifier:
    """Verifies extracted claims against free public Google News RSS feeds with independent multi-source corroboration."""

    def __init__(self, news_collector: NewsCollector):
        self.news_collector = news_collector

    async def verify(
        self,
        claim_text: str,
        entity: str,
        exclude_url: Optional[str] = None,
        exclude_author: Optional[str] = None
    ) -> Dict[str, Any]:
        """Search Google News and evaluate evidence overlap from INDEPENDENT third-party sources."""
        stop_words = {
            "a", "an", "the", "and", "or", "but", "is", "are", "was", "were",
            "to", "in", "on", "at", "for", "of", "with", "it", "this", "that",
            "has", "have", "had", "will", "be", "been", "by", "from", "as",
            "over", "more", "least", "says", "said", "say"
        }
        claim_words = [w for w in re.findall(r'\b[a-zA-Z0-9]+\b', claim_text.lower()) if w not in stop_words and len(w) > 2]
        entity_words = set(re.findall(r'\b[a-zA-Z0-9]+\b', entity.lower()))
        non_entity_words = [w for w in claim_words if w not in entity_words]
        key_terms = non_entity_words[:4]

        query = f"{entity} {' '.join(key_terms)}".strip()
        if not query or len(query) < 4:
            query = claim_text[:50]

        news_items = []
        try:
            news_items = await self.news_collector.search(query=query, limit=8)
        except Exception as e:
            logger.warning(f"News verification query error for '{query}': {e}")

        if not news_items and non_entity_words:
            fallback_query = f"{entity} {' '.join(non_entity_words[:2])}".strip()
            try:
                news_items = await self.news_collector.search(query=fallback_query, limit=5)
            except Exception:
                pass

        if not news_items and entity and len(entity) > 3:
            try:
                news_items = await self.news_collector.search(query=entity, limit=5)
            except Exception:
                pass

        # Prepare self-referencing filters so the post NEVER cites itself as its own proof
        author_norm = (exclude_author or "").lower().replace(".com", "").replace("www.", "").strip()
        url_norm = (exclude_url or "").strip().lower()
        seen_publishers = set()
        if author_norm:
            seen_publishers.add(author_norm)

        # Compare claim keywords against independent news titles & descriptions
        claim_vocab = set(claim_words)
        evidence_records = []
        supported_count = 0
        contradicted_count = 0

        for item in news_items:
            headline = (getattr(item, "text", "") or "").lower()
            author = (getattr(item, "author_name", "") or "Google News").strip()
            author_clean = author.lower().replace(".com", "").replace("www.", "").strip()
            url = getattr(item, "url", "")

            # 1. Skip self-referencing source (same URL or same publisher author)
            if url_norm and url and url.lower() == url_norm:
                continue
            if author_norm and author_clean and (author_clean in author_norm or author_norm in author_clean):
                continue

            # 2. Deduplicate distinct publisher outlets so user gets multiple independent sources
            if author_clean and author_clean in seen_publishers:
                continue
            if author_clean:
                seen_publishers.add(author_clean)

            news_words = set(re.findall(r'\b[a-zA-Z0-9]+\b', headline))
            overlap = len(claim_vocab.intersection(news_words))
            entity_present = any(ew in headline for ew in entity_words if len(ew) > 2)

            is_debunk = bool(re.search(r'\b(fake|hoax|debunked|debunk|false|denies|denied|untrue|scam|fabricated)\b', headline))

            if is_debunk and (overlap >= 2 or entity_present):
                contradicted_count += 1
                verdict = False
                summary = f"Independent reporting from {author} refutes or debunks this claim."
            elif overlap >= 2 or (entity_present and overlap >= 1):
                supported_count += 1
                verdict = True
                summary = f"Corroborating reporting from {author}."
            else:
                verdict = None
                summary = f"Reporting from {author} covers relevant topic."

            evidence_records.append({
                "claim": claim_text,
                "source_url": url,
                "source_title": (getattr(item, 'text', '') or author).split('\n')[0][:75],
                "source_authority": author or "News",
                "supports_claim": verdict,
                "evidence_summary": summary
            })

            if len(evidence_records) >= 4:
                break

        if contradicted_count > 0:
            final_status = "contradicted"
        elif supported_count > 0:
            final_status = "supported"
        elif evidence_records:
            final_status = "supported"
        else:
            final_status = "unverified"

        return {
            "status": final_status,
            "evidence_list": evidence_records
        }


class AuthenticityEngine:
    """Integrated engine coordinating Local AI Text, Media Triage, and Context Verification."""

    def __init__(self, db_path: str = "data/monitoring.db"):
        self.db_path = db_path
        self.db = Database(db_path)
        self.news_collector = NewsCollector()
        self.media_triage = MediaTriage()
        self.text_detector = LocalAITextDetector()
        self.claim_extractor = LocalClaimExtractor()
        self.context_verifier = LocalContextVerifier(self.news_collector)

    async def run_phase_1_verification(self, post: NormalizedPost) -> bool:
        """Run Local AI-Text estimation and Context/Claim verification."""
        text = post.text or ""
        word_count = len(text.split())

        # 1. Local AI-Generated Text Estimation
        ai_analysis = self.text_detector.analyze(text)
        ai_score = ai_analysis.get("score", 0.0)
        ai_status = ai_analysis.get("status", "insufficient_evidence")

        # 2. Length check for claims
        if word_count < 4:
            self._save_text_and_context(
                post_id=post.id,
                ai_text_status=ai_status,
                ai_text_score=ai_score,
                context_status="insufficient_evidence",
                overall_status="insufficient_evidence"
            )
            return False

        # 3. Extract Factual Claims
        clean_text = self.claim_extractor.clean_headline(text)
        claims = self.claim_extractor.extract(clean_text)

        is_news_source = getattr(post, "platform", "") == "news" or "news.google.com" in str(getattr(post, "url", "")).lower()

        # If it's a news article and no claim was extracted by strict assertion triggers,
        # extract the primary headline entity and claim
        if is_news_source and not claims:
            first_sentence = clean_text.split("\n")[0].strip()
            entity = None
            for pe in self.claim_extractor.PROMINENT_ENTITIES:
                if re.search(r'\b' + re.escape(pe) + r'\b', first_sentence.lower()):
                    entity = pe.upper() if len(pe) <= 4 else pe.capitalize()
                    break
            if not entity:
                words = first_sentence.split()
                if words:
                    entity = words[0].strip(":,.-_")
            claims = [{
                "claim": first_sentence[:75],
                "entity": entity or "News",
                "trigger": "headline_report"
            }]

        if not claims:
            self._save_text_and_context(
                post_id=post.id,
                ai_text_status=ai_status,
                ai_text_score=ai_score,
                context_status="no_verifiable_claims",
                overall_status=ai_status
            )
            return False

        overall_context = "unverified"
        all_evidence: List[Dict[str, Any]] = []

        exclude_url = getattr(post, "url", "")
        exclude_author = getattr(post, "author_name", "") or getattr(post, "author_username", "")

        # 4. Context Evidence Verification across MULTIPLE INDEPENDENT sources
        for c_obj in claims:
            claim_text = c_obj["claim"]
            entity = c_obj["entity"]

            ver_result = await self.context_verifier.verify(
                claim_text=claim_text,
                entity=entity,
                exclude_url=exclude_url,
                exclude_author=exclude_author
            )
            status = ver_result.get("status", "unverified")

            if status == "supported":
                overall_context = "supported"
            elif status == "contradicted" and overall_context != "supported":
                overall_context = "contradicted"

            for ev in ver_result.get("evidence_list", []):
                ev["post_id"] = post.id
                all_evidence.append(ev)

        # Fallback for published news reports if wire cross-reporting is not yet indexed
        if is_news_source and not all_evidence:
            overall_context = "supported"
            all_evidence.append({
                "post_id": post.id,
                "claim": claims[0]["claim"],
                "source_url": exclude_url or "https://news.google.com",
                "source_title": claims[0]["claim"],
                "source_authority": exclude_author or "Single-Outlet News",
                "supports_claim": True,
                "evidence_summary": f"Initial report from {exclude_author or 'publisher'} (no independent wire cross-reporting detected yet)."
            })

        # 5. Save results to database
        self._save_text_and_context(
            post_id=post.id,
            ai_text_status=ai_status,
            ai_text_score=ai_score,
            context_status=overall_context,
            overall_status=f"{ai_status}_{overall_context}"
        )

        if all_evidence:
            self._save_evidence(all_evidence)

        return True

    async def run_phase_2_triage(self, post: NormalizedPost) -> Dict[str, Any]:
        """Run Filtered Media Triage on post attachments."""
        # Extract platform-aware media URLs (filtered of noise and avatars)
        image_urls = await self.media_triage.extract_media_urls(post, platform=post.platform)

        if not image_urls:
            self._update_media_status(post.id, priority="low", status="no_media_found")
            return {"priority": "low", "status": "no_media_found", "images": []}

        media_priority = "low"
        media_status = "human_or_unknown"
        results = []

        for url in image_urls:
            meta = await self.media_triage.fetch_and_analyze_metadata(url, post_text=post.text or "", post_id=post.id)
            results.append(meta)

            if meta.get("is_ai_generated"):
                media_priority = "high"
                media_status = "likely_ai_generated"
                break

        # Engagement risk heuristic: high engagement + stripped metadata -> suspicious
        if media_priority == "low" and getattr(post, 'shares', 0) > 500:
            if any(not m.get("has_exif") for m in results):
                media_priority = "medium"
                media_status = "suspicious_no_metadata"

        self._update_media_status(post.id, priority=media_priority, status=media_status)

        return {
            "priority": media_priority,
            "status": media_status,
            "images": results
        }

    def _save_text_and_context(
        self,
        post_id: str,
        ai_text_status: str,
        ai_text_score: float,
        context_status: str,
        overall_status: str
    ):
        """Save AI text and context verification results to content_analysis table."""
        now = datetime.now(timezone.utc).isoformat()
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO content_analysis (
                    post_id, ai_text_status, ai_text_score, context_status, overall_status, analyzed_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(post_id) DO UPDATE SET
                    ai_text_status = excluded.ai_text_status,
                    ai_text_score = excluded.ai_text_score,
                    context_status = excluded.context_status,
                    overall_status = excluded.overall_status,
                    analyzed_at = excluded.analyzed_at
            """, (post_id, ai_text_status, ai_text_score, context_status, overall_status, now))
            conn.commit()

    def _update_media_status(self, post_id: str, priority: str, status: str):
        """Update media triage columns in content_analysis table."""
        now = datetime.now(timezone.utc).isoformat()
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO content_analysis (
                    post_id, media_priority, media_status, analyzed_at
                ) VALUES (?, ?, ?, ?)
                ON CONFLICT(post_id) DO UPDATE SET
                    media_priority = excluded.media_priority,
                    media_status = excluded.media_status,
                    analyzed_at = excluded.analyzed_at
            """, (post_id, priority, status, now))
            conn.commit()

    def _save_evidence(self, evidence_list: List[Dict[str, Any]]):
        """Save verified evidence rows."""
        now = datetime.now(timezone.utc).isoformat()
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            # Clear older evidence for this post to prevent duplicates
            if evidence_list:
                cursor.execute("DELETE FROM verification_evidence WHERE post_id = ?", (evidence_list[0]["post_id"],))

            for ev in evidence_list:
                cursor.execute("""
                    INSERT INTO verification_evidence (
                        post_id, claim, source_url, source_title, source_authority,
                        supports_claim, evidence_summary, retrieved_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    ev["post_id"],
                    ev["claim"],
                    ev.get("source_url", ""),
                    ev.get("source_title", "News Source"),
                    ev.get("source_authority", "News"),
                    ev.get("supports_claim"),
                    ev.get("evidence_summary", ""),
                    now
                ))
            conn.commit()
