# routes/stocks.py
from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel
from typing import List, Optional
from db import get_news_by_short_name, get_news_by_id, is_free, get_user_by_id
from services import summarise_article, summarise_recent_news
from jobs import update_ai_summary
from dependencies import get_current_active_user, require_pro
from db import insert_stock_summary, get_latest_stock_summary, increment_ai_tokens
from datetime import datetime, timezone, timedelta


router = APIRouter(prefix="/news", tags=["News"])

class NewsResponse(BaseModel):
    # NOT NULL in db - always present
    id: int
    short_name: str
    source: str
    publish_time: str
    url: str
    title: str

    # nullable in db - can be None
    source_url: Optional[str] = None
    source_country: Optional[str] = None
    lang: Optional[str] = None
    image: Optional[str] = None
    description: Optional[str] = None
    sentiment: Optional[float] = None
    ai_summary: Optional[str] = None

class NewsListResponse(BaseModel):
    results: List[NewsResponse]


class AiArticleResponse(BaseModel):
    id: int
    ai_summary: str


class AiStockSummaryResponse(BaseModel):
    symbol: str
    ai_summary: str


def db_to_news(item: dict) -> NewsResponse:
    return NewsResponse(
        id=item["id"],
        short_name=item["short_name"],
        source=item["source"],
        publish_time=item["publish_time"],
        url=item["url"],
        title=item["title"],
        source_url=item["source_url"],
        source_country=item["source_country"],
        lang=item["lang"],
        image=item["image"],
        description=item["description"],
        sentiment=item["sentiment"],
        ai_summary=item["AI_summary"]
    )


@router.get("/symbol_free", response_model=NewsListResponse)
def get_news_by_symbol(
    q: str = Query(...),
    since: str = Query(None)  # ISO 8601 timestamp e.g. "2026-03-22T10:00:00"
    ):

    symbols = [s.strip() for s in q.split(",")]
    news = []
    for sym in symbols:
        if not is_free(sym):
            continue
        items = get_news_by_short_name(short_name=sym, since=since)
        for item in items:
            news.append(db_to_news(item))

    print(len(news))
    return NewsListResponse(results=news)


@router.get("/symbol_premium")
def get_news_by_symbol_premium(
    q: str = Query(...),
    since: str = Query(None),
    user: dict = Depends(require_pro)  # handles tier check automatically
):
    symbols = [s.strip() for s in q.split(",")]
    news = []
    for sym in symbols:
        items = get_news_by_short_name(short_name=sym, since=since)
        for item in items:
            news.append(db_to_news(item))
    return NewsListResponse(results=news)


@router.get("/article_ai_summary/{id}", response_model=AiArticleResponse)
def get_ai_summary_by_news_id(id: int):

    article = get_news_by_id(id)
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")

    if article["AI_summary"] is not None:
        #increment_ai_tokens(user["id"], ai_summary["tokens_in"] + ai_summary["tokens_out"])
        return AiArticleResponse(id=article["id"], ai_summary=article["AI_summary"])

    ai_summary = update_ai_summary(
        news_id=article["id"],
        stock_short_name=article["short_name"],
        news_url=article["url"],
        news_title=article["title"],
        news_description=article["description"]
    )

    if ai_summary is None:
        raise HTTPException(status_code=500, detail="Failed to generate AI summary")
    
    #increment_ai_tokens(user["id"], ai_summary["tokens_in"] + ai_summary["tokens_out"])

    return AiArticleResponse(id=ai_summary["id"], ai_summary=ai_summary["ai_summary"])


@router.get("/stock_ai_summary/{stock}", response_model=AiStockSummaryResponse)
def get_stock_ai_summary(
    stock: str,
    days: int = Query(7)
):
    """
        A better way to implement this is to check if there has been new news since the previous summary.
        This will require storing the number of articles used / which articles were used in the stock_ai_summary table
    """
    # check if we already have a recent summary (within last 24 hours)
    # TODO: if no new news < 24 hours, then we also do not need to re-summarise
    existing = get_latest_stock_summary(stock)
    if existing:
        age = datetime.now(timezone.utc) - datetime.fromisoformat(existing["created_at"])
        if age < timedelta(hours=24):
            print(f"[get_stock_ai_summary] Returning cached summary for {stock}")
            return AiStockSummaryResponse(symbol=existing["short_name"], ai_summary=existing["ai_summary"])

    # generate new summary
    result = summarise_recent_news(short_name=stock, days=days)
    if result is None:
        raise HTTPException(status_code=404, detail=f"No recent news found for {stock}")

    # store in db and track token usage
    insert_stock_summary(
        short_name=stock,
        ai_summary=result["ai_summary"],
        tokens_total=result["tokens_in"] + result["tokens_out"],
        days=days
    )
    #increment_ai_tokens(user["id"], result["tokens_in"] + result["tokens_out"])

    return AiStockSummaryResponse(symbol=result["short_name"], ai_summary=result["ai_summary"])


