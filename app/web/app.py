"""FastAPI application for Social Media Monitoring local web dashboard."""

import os
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, HTTPException, Query, Body
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from app.collectors.x_collector import XCollector
from app.collectors.base import CollectorError, NoAccountError, AuthError, RateLimitError, NetworkError
from app.database.db import Database
from app.models.post import NormalizedPost

app = FastAPI(
    title="Social Media Monitoring",
    description="Local prototype for X (Twitter) keyword search and social monitoring",
    version="0.1.0"
)

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
collector = XCollector()
db = Database()


class SearchRequest(BaseModel):
    query: str
    limit: int = 20
    product: str = "Latest"
    save_to_db: bool = True


class AddCookieRequest(BaseModel):
    name: str
    cookies: str


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
async def perform_search(req: SearchRequest):
    """Execute keyword search against X and return normalized posts."""
    query = req.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Search query cannot be empty.")

    try:
        posts = await collector.search(query=query, limit=req.limit, product=req.product)
        
        saved_count = 0
        if req.save_to_db and posts:
            saved_count = db.save_posts(posts, searched_query=query)
        elif req.save_to_db and not posts:
            db.log_search(query, results_count=0)

        return {
            "query": query,
            "count": len(posts),
            "saved_count": saved_count,
            "posts": [p.model_dump() for p in posts],
        }

    except NoAccountError as e:
        raise HTTPException(
            status_code=401,
            detail={
                "code": "NO_ACCOUNT",
                "message": str(e),
                "instruction": "Please add an account session cookie via the Accounts tab."
            }
        )
    except (AuthError, RateLimitError, NetworkError, CollectorError) as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {e}")


@app.get("/api/posts")
async def get_saved_posts(
    q: Optional[str] = Query(None, description="Optional search filter"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """Retrieve saved posts from local SQLite database."""
    posts = db.get_posts(query=q, limit=limit, offset=offset)
    return {
        "count": len(posts),
        "posts": [p.model_dump() for p in posts],
    }


@app.get("/api/history")
async def get_search_history(limit: int = Query(20, ge=1, le=100)):
    """Retrieve past search queries."""
    history = db.get_search_history(limit=limit)
    return {"history": history}


@app.post("/api/accounts/cookies")
async def add_cookies(req: AddCookieRequest):
    """Add session cookies to the X account pool."""
    if not req.name or not req.cookies:
        raise HTTPException(status_code=400, detail="Account name and cookies are required.")
    
    try:
        await collector.add_account_cookies(req.name, req.cookies)
        return {"status": "ok", "message": f"Successfully registered cookies for '{req.name}'."}
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


# Mount static directory and root fallback
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/")
    async def serve_index():
        return FileResponse(os.path.join(STATIC_DIR, "index.html"))
