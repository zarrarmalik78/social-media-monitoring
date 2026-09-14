"""FastAPI application for Social Media Monitoring local web dashboard."""

import os
import json
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, HTTPException, Query, Body, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
import asyncio

from app.collectors.manager import CollectorManager
from app.collectors.base import CollectorError, NoAccountError, AuthError, RateLimitError, NetworkError
from app.database.db import Database
from app.models.post import NormalizedPost
from app.utils.query_builder import QueryBuilder, SearchQueryFilter
from app.utils.authenticity_engine import AuthenticityEngine

app = FastAPI(
    title="Social Media Monitoring",
    description="Multi-platform social media and news monitoring prototype (X, Reddit, News/RSS)",
    version="0.3.0"
)

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
collector = CollectorManager()
db = Database()
auth_engine = AuthenticityEngine()

async def run_authenticity_pipeline(posts: List[NormalizedPost]):
    """Background task to run Phase 1 and Phase 2 Authenticity Analysis."""
    for post in posts:
        try:
            # Phase 1: Context/Claim Verification
            await auth_engine.run_phase_1_verification(post)
            # Phase 2: Media Triage
            await auth_engine.run_phase_2_triage(post)
        except Exception as e:
            # Catching generic exceptions so background task continues
            pass

class SearchRequest(BaseModel):
    query: str
    limit: int = 20
    platform: str = "all"
    product: str = "Latest"
    save_to_db: bool = True


class AddCookieRequest(BaseModel):
    name: str
    cookies: str
    platform: str = "x"


@app.get("/api/status")
async def get_status():
    """Retrieve collector readiness and local database statistics."""
    collector_status = await collector.check_status()
    db_stats = db.get_stats()
    return {
        "status": "ok",
        "collector": collector_status,
        "database": db_stats,
    }


@app.post("/api/search")
async def perform_search(req: SearchRequest, background_tasks: BackgroundTasks):
    """Execute search across selected platform(s) and return normalized posts."""
    query = req.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Search query cannot be empty.")

    try:
        posts = await collector.search(
            query=query,
            limit=req.limit,
            platform=req.platform,
            product=req.product
        )
        
        saved_count = 0
        if req.save_to_db and posts:
            saved_count = db.save_posts(posts, searched_query=query)
            # Trigger authenticity engine asynchronously
            background_tasks.add_task(run_authenticity_pipeline, posts)
        elif req.save_to_db and not posts:
            db.log_search(query, results_count=0, platform=req.platform)

        post_dicts = [p.model_dump() for p in posts]
        for p in post_dicts:
            p["media_urls"] = auth_engine.media_triage.extract_media_urls_sync(p, platform=p.get("platform", ""))
            p["video_info"] = auth_engine.media_triage.extract_video_info(p, platform=p.get("platform", ""))
            
            # Instant local text verification (<0.1ms)
            t_text = p.get("text", "")
            ai_res = auth_engine.text_detector.analyze(t_text)
            claims = auth_engine.claim_extractor.extract(t_text)
            is_news = p.get("platform") == "news" or "news.google.com" in str(p.get("url", "")).lower()

            ev_list = []
            if is_news:
                ctx_status = "supported"
            else:
                w_count = len(t_text.split())
                if w_count < 4:
                    ctx_status = "insufficient_evidence"
                elif not claims:
                    ctx_status = "no_verifiable_claims"
                else:
                    ctx_status = "unverified"
                
            p["authenticity"] = {
                "post_id": p.get("id"),
                "ai_text_status": ai_res.get("status", "insufficient_evidence"),
                "ai_text_score": ai_res.get("score", 0.0),
                "context_status": ctx_status,
                "overall_status": f"{ai_res.get('status')}_{ctx_status}",
                "media_priority": "low",
                "media_status": "no_media_found",
                "evidence": ev_list
            }

        return {
            "query": query,
            "platform": req.platform,
            "count": len(posts),
            "saved_count": saved_count,
            "posts": post_dicts,
        }

    except NoAccountError as e:
        raise HTTPException(
            status_code=401,
            detail={
                "code": "NO_ACCOUNT",
                "message": str(e),
                "instruction": "Please add an account session cookie via the Accounts tab or search via Reddit/News."
            }
        )
    except (AuthError, RateLimitError, NetworkError, CollectorError) as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {e}")


@app.get("/api/posts")
async def get_saved_posts(
    q: Optional[str] = Query(None, description="Optional search filter"),
    platform: Optional[str] = Query(None, description="Optional platform filter (x, reddit, news, all)"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """Retrieve saved posts from local SQLite database."""
    posts = db.get_posts(query=q, platform=platform, limit=limit, offset=offset)
    
    # Inject authenticity data
    post_dicts = [p.model_dump() for p in posts]
    if post_dicts:
        post_ids = [p["id"] for p in post_dicts]
        placeholders = ",".join("?" * len(post_ids))
        
        with db._get_connection() as conn:
            c = conn.cursor()
            
            # Fetch content analysis
            c.execute(f"SELECT * FROM content_analysis WHERE post_id IN ({placeholders})", post_ids)
            analysis_rows = {row["post_id"]: dict(row) for row in c.fetchall()}
            
            # Fetch evidence
            c.execute(f"SELECT * FROM verification_evidence WHERE post_id IN ({placeholders})", post_ids)
            evidence_rows = c.fetchall()
            evidence_map = {}
            for row in evidence_rows:
                pid = row["post_id"]
                if pid not in evidence_map:
                    evidence_map[pid] = []
                evidence_map[pid].append(dict(row))
                
            for p in post_dicts:
                pid = p["id"]
                auth = analysis_rows.get(pid)
                is_news = p.get("platform") == "news" or "news.google.com" in str(p.get("url", "")).lower()

                p_url = str(p.get("url") or "").lower().strip()
                p_auth = str(p.get("author_name") or "").lower().replace(".com", "").replace("www.", "").strip()

                raw_ev_list = evidence_map.get(pid, [])
                clean_ev_list = []
                for ev in raw_ev_list:
                    ev_url = str(ev.get("source_url") or "").lower().strip()
                    ev_auth = str(ev.get("source_authority") or "").lower().replace(".com", "").replace("www.", "").strip()
                    # Filter out self-referencing citations
                    if p_url and ev_url and p_url == ev_url:
                        continue
                    if p_auth and ev_auth and (p_auth in ev_auth or ev_auth in p_auth):
                        continue
                    clean_ev_list.append(ev)

                if is_news:
                    ai_stat = auth.get("ai_text_status", "likely_human") if auth else "likely_human"
                    ai_sc = auth.get("ai_text_score", 0.2) if auth else 0.2

                    p["authenticity"] = {
                        "post_id": pid,
                        "ai_text_status": ai_stat,
                        "ai_text_score": ai_sc,
                        "context_status": "supported",
                        "overall_status": f"{ai_stat}_supported",
                        "media_priority": "low",
                        "media_status": "no_media_found",
                        "evidence": clean_ev_list
                    }
                    p["media_urls"] = auth_engine.media_triage.extract_media_urls_sync(p, platform=p.get("platform", ""))
                    p["video_info"] = auth_engine.media_triage.extract_video_info(p, platform=p.get("platform", ""))
                    continue

                if auth:
                    auth_data = dict(auth)
                    auth_data["evidence"] = clean_ev_list

                    # If evidence corroborates claim, ensure status is supported
                    if any(ev.get("supports_claim") is True or ev.get("supports_claim") == 1 for ev in clean_ev_list):
                        auth_data["context_status"] = "supported"
                    else:
                        t_text = p.get("text", "")
                        w_count = len(t_text.split())
                        if auth_data.get("context_status") in ("unverified", None):
                            claims = auth_engine.claim_extractor.extract(t_text)
                            if w_count < 4:
                                auth_data["context_status"] = "insufficient_evidence"
                            elif not claims:
                                auth_data["context_status"] = "no_verifiable_claims"
                    p["authenticity"] = auth_data
                else:
                    # Instant local text verification (<0.1ms) so NO post shows Pending
                    t_text = p.get("text", "")
                    ai_res = auth_engine.text_detector.analyze(t_text)
                    claims = auth_engine.claim_extractor.extract(t_text)

                    w_count = len(t_text.split())
                    if w_count < 8:
                        ctx_status = "insufficient_evidence"
                    elif not claims:
                        ctx_status = "no_verifiable_claims"
                    else:
                        ctx_status = "unverified"

                    auth_data = {
                        "post_id": pid,
                        "ai_text_status": ai_res.get("status", "insufficient_evidence"),
                        "ai_text_score": ai_res.get("score", 0.0),
                        "context_status": ctx_status,
                        "overall_status": f"{ai_res.get('status')}_{ctx_status}",
                        "media_priority": "low",
                        "media_status": "no_media_found",
                        "evidence": []
                    }
                    try:
                        auth_engine._save_text_and_context(pid, auth_data["ai_text_status"], auth_data["ai_text_score"], ctx_status, auth_data["overall_status"])
                    except Exception:
                        pass
                    p["authenticity"] = auth_data

                p["media_urls"] = auth_engine.media_triage.extract_media_urls_sync(p, platform=p.get("platform", ""))
                p["video_info"] = auth_engine.media_triage.extract_video_info(p, platform=p.get("platform", ""))
                
    return {
        "count": len(post_dicts),
        "posts": post_dicts,
    }


class MediaVerifyRequest(BaseModel):
    url: str
    post_id: Optional[str] = None


@app.post("/api/media/verify")
async def verify_single_media(req: MediaVerifyRequest):
    """Inspect and verify a single image on-demand in-memory without disk storage."""
    clean_url = req.url.strip()
    if not clean_url:
        raise HTTPException(status_code=400, detail="Image URL cannot be empty.")

    post_text = ""
    if req.post_id:
        try:
            with db._get_connection() as conn:
                c = conn.cursor()
                c.execute("SELECT text FROM posts WHERE id = ?", (req.post_id,))
                p_row = c.fetchone()
                if p_row and p_row["text"]:
                    post_text = p_row["text"]
        except Exception:
            pass

    result = await auth_engine.media_triage.fetch_and_analyze_metadata(
        clean_url, post_text=post_text, post_id=req.post_id or ""
    )

    if req.post_id:
        priority = "high" if result.get("is_ai_generated") else "low"
        status = "likely_ai_generated" if result.get("is_ai_generated") else (
            "camera_photo" if result.get("verdict") == "AUTHENTIC_CAMERA_PHOTO" else "human_or_compressed"
        )
        try:
            auth_engine._update_media_status(req.post_id, priority, status)
        except Exception:
            pass

    return {
        "success": True,
        "result": result
    }


class VideoVerifyRequest(BaseModel):
    url: str
    post_id: Optional[str] = None
    platform: Optional[str] = None


@app.post("/api/video/verify")
async def verify_single_video(req: VideoVerifyRequest):
    """Inspect and verify a single video (YouTube Shorts, IG Reels, MP4) in-memory without disk storage."""
    clean_url = req.url.strip()
    if not clean_url:
        raise HTTPException(status_code=400, detail="Video URL cannot be empty.")

    post_text = ""
    if req.post_id:
        try:
            with db._get_connection() as conn:
                c = conn.cursor()
                c.execute("SELECT text FROM posts WHERE id = ?", (req.post_id,))
                p_row = c.fetchone()
                if p_row and p_row["text"]:
                    post_text = p_row["text"]
        except Exception:
            pass

    raw_res = await auth_engine.media_triage.verify_video(
        video_url=clean_url,
        platform=req.platform or "",
        post_text=post_text,
        post_id=req.post_id or ""
    )
    result = raw_res.get("result", {})

    if req.post_id:
        priority = "high" if result.get("is_ai_video") else "low"
        status = "likely_ai_video" if result.get("is_ai_video") else (
            "natural_camera_video" if result.get("verdict") == "NATURAL_CAMERA_VIDEO" else "human_or_compressed_video"
        )
        try:
            auth_engine._update_media_status(req.post_id, priority, status)
        except Exception:
            pass

    return {
        "success": True,
        "result": result,
        "video_info": raw_res.get("video_info", {})
    }


@app.post("/api/posts/{post_id}/verify")
async def verify_post_by_id(post_id: str):
    """Run on-demand authenticity verification on a single post."""
    with db._get_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM posts WHERE id = ?", (post_id,))
        row = c.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Post not found")
        
        raw_dict = json.loads(row["raw_data"]) if row["raw_data"] else None
        try:
            dt = datetime.fromisoformat(row["created_at"])
        except Exception:
            dt = datetime.now(timezone.utc)
        
        post = NormalizedPost(
            id=row["id"],
            platform=row["platform"],
            item_type=row["item_type"] if "item_type" in row.keys() else "post",
            parent_id=row["parent_id"] if "parent_id" in row.keys() else None,
            text=row["text"],
            author_username=row["author_username"],
            author_name=row["author_name"] or "",
            created_at=dt,
            url=row["url"],
            likes=row["likes"] or 0,
            replies=row["replies"] or 0,
            reposts=row["reposts"] or 0,
            shares=row["shares"] or 0,
            comments_count=row["comments_count"] or 0,
            views=row["views"],
            raw_data=raw_dict
        )

    # Run verification & triage
    await auth_engine.run_phase_1_verification(post)
    await auth_engine.run_phase_2_triage(post)

    # Fetch updated analysis
    with db._get_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM content_analysis WHERE post_id = ?", (post_id,))
        analysis_row = c.fetchone()
        c.execute("SELECT * FROM verification_evidence WHERE post_id = ?", (post_id,))
        ev_rows = c.fetchall()

    auth_data = dict(analysis_row) if analysis_row else {}
    auth_data["evidence"] = [dict(r) for r in ev_rows]

    return {
        "success": True,
        "post_id": post_id,
        "authenticity": auth_data
    }


@app.post("/api/authenticity/batch-verify")
async def batch_verify_recent(background_tasks: BackgroundTasks, limit: int = 50):
    """Run authenticity verification on recent unverified posts."""
    posts = db.get_posts(limit=limit)
    background_tasks.add_task(run_authenticity_pipeline, posts)
    return {"status": "started", "message": f"Verification queued for {len(posts)} posts"}


@app.get("/api/analytics")
async def get_analytics(
    q: Optional[str] = Query(None, description="Optional search filter"),
    platform: Optional[str] = Query(None, description="Optional platform filter")
):
    """Retrieve aggregate analytics data for the dashboard charts."""
    # We fetch up to 1000 recent posts to generate analytics
    posts = db.get_posts(query=q, platform=platform, limit=1000, offset=0)
    
    total_mentions = len(posts)
    
    sentiment_counts = {"Positive": 0, "Neutral": 0, "Negative": 0}
    platform_counts = {}
    topic_counts = {}
    
    for p in posts:
        # Sentiment
        sentiment_counts[p.sentiment_label] += 1
        
        # Platforms
        plat = p.platform.capitalize()
        platform_counts[plat] = platform_counts.get(plat, 0) + 1
        
        # Topics
        for t in p.topics:
            topic_counts[t] = topic_counts.get(t, 0) + 1
            
    # Calculate Net Sentiment (Positive - Negative) / Total
    net_sentiment = 0.0
    if total_mentions > 0:
        net_sentiment = ((sentiment_counts["Positive"] - sentiment_counts["Negative"]) / total_mentions) * 100
        
    # Top Platform
    top_platform = max(platform_counts.items(), key=lambda x: x[1])[0] if platform_counts else "N/A"
    
    return {
        "metrics": {
            "total_mentions": total_mentions,
            "net_sentiment": round(net_sentiment, 1),
            "top_platform": top_platform,
            "velocity": f"+{total_mentions} this week" # Placeholder velocity
        },
        "charts": {
            "sentiment": sentiment_counts,
            "platforms": platform_counts,
            "topics": topic_counts
        }
    }

@app.get("/api/history")
async def get_search_history(limit: int = Query(20, ge=1, le=100)):
    """Retrieve past search queries."""
    history = db.get_search_history(limit=limit)
    return {"history": history}


@app.post("/api/accounts/cookies")
async def add_cookies(req: AddCookieRequest):
    """Add session cookies to any supported platform account pool."""
    if not req.name or not req.cookies:
        raise HTTPException(status_code=400, detail="Account name and cookies are required.")
    
    try:
        await collector.add_account_cookies(platform=req.platform, account_name=req.name, cookies=req.cookies)
        return {"status": "ok", "message": f"Successfully registered {req.platform.upper()} cookies for '{req.name}'."}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/accounts/reset-locks")
async def reset_locks():
    """Reset rate limit locks."""
    try:
        await collector.reset_locks()
        return {"status": "ok", "message": "Account locks successfully reset."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/query/build")
async def build_search_query(filters: SearchQueryFilter):
    """Compile structured filter parameters into a valid X search query string."""
    query_str = QueryBuilder.build(filters)
    validation = QueryBuilder.validate(query_str) if query_str else {"valid": True, "errors": [], "warnings": []}
    return {
        "query": query_str,
        "validation": validation,
    }


@app.post("/api/query/validate")
async def validate_search_query(body: Dict[str, str] = Body(...)):
    """Validate a raw search query string and return diagnostic feedback."""
    query = body.get("query", "")
    return QueryBuilder.validate(query)


# Mount static directory and root fallback

if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/")
    async def serve_index():
        return FileResponse(os.path.join(STATIC_DIR, "index.html"))
