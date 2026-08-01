"""Data access. Import the submodules, not a flat namespace of 60 functions —
`news.get_news(...)` says where the data lives, `get_news(...)` doesn't.
"""
from . import events, news, prices, sentiment, stocks, summaries, watchlist
from .connection import create_tables, get_connection

__all__ = [
    "create_tables",
    "get_connection",
    "events",
    "news",
    "prices",
    "sentiment",
    "stocks",
    "summaries",
    "watchlist",
]
