"""Data access. Import the submodules, not a flat namespace of 60 functions —
`news.get_news(...)` says where the data lives, `get_news(...)` doesn't.
"""
from . import news, prices, sentiment, stocks, summaries, watchlist
from .connection import create_tables, get_connection

__all__ = [
    "create_tables",
    "get_connection",
    "news",
    "prices",
    "sentiment",
    "stocks",
    "summaries",
    "watchlist",
]
