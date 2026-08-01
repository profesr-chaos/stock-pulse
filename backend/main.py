"""Stocky API.

Personal tool, no authentication — which is exactly why it binds to loopback
and uses a CORS allow-list rather than `*`. An unauthenticated API answering
`Access-Control-Allow-Origin: *` lets any page you happen to visit read and
modify your watchlist.
"""
from __future__ import annotations

import threading
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

import db
import jobs
import settings
from routes.insights import router as insights_router
from routes.news import events_router, router as news_router
from routes.stocks import router as stocks_router
from routes.system import router as system_router
from routes.watchlist import router as watchlist_router
from routes.ws import router as ws_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.create_tables()
    # Finish any backfill interrupted by a restart, off the request path so
    # startup isn't blocked on network I/O.
    threading.Thread(target=jobs.catch_up, name="catch-up", daemon=True).start()
    yield
    from services.http_client import scraper
    scraper.close()


app = FastAPI(
    title="Stocky",
    version="0.2.0",
    description="Free stock news and prices, scraped. No API keys, no accounts.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type"],
    # No cookies or auth headers to send, so credentials stay off.
    allow_credentials=False,
    max_age=600,
)
app.add_middleware(GZipMiddleware, minimum_size=1024)

app.include_router(system_router)
app.include_router(stocks_router)
app.include_router(news_router)
app.include_router(events_router)
app.include_router(watchlist_router)
app.include_router(insights_router)
app.include_router(ws_router)


if __name__ == "__main__":
    uvicorn.run("main:app", host=settings.HOST, port=settings.PORT, reload=True)
