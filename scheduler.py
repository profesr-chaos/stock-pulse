"""Background scheduler. Run alongside the API: `python scheduler.py`.

Deliberately separate from the API process so a long scrape can never block a
request, and so restarting the API doesn't interrupt a refresh.
"""
from __future__ import annotations

from apscheduler.schedulers.blocking import BlockingScheduler

import db
import jobs
import settings

scheduler = BlockingScheduler(timezone="UTC")

# Prices hourly. Nothing here needs tick-by-tick data — a chart of the last day
# and a price from within the hour is the stated requirement, and it keeps us
# comfortably inside every source's tolerance.
scheduler.add_job(
    jobs.refresh_prices, "interval",
    minutes=settings.PRICE_REFRESH_MINUTES, id="prices",
    max_instances=1, coalesce=True,
)

scheduler.add_job(
    jobs.refresh_news, "interval",
    minutes=settings.NEWS_REFRESH_MINUTES, id="news",
    max_instances=1, coalesce=True,
)

# Rollups after the US close (21:30 UTC in summer), then housekeeping.
scheduler.add_job(jobs.aggregate_sentiment, "cron", hour=22, minute=0, id="sentiment")
scheduler.add_job(jobs.prune, "cron", hour=3, minute=30, id="prune")

# The instrument catalogue barely changes, and needs Trading212 keys at all.
scheduler.add_job(jobs.refresh_catalogue, "cron", day_of_week="mon", hour=4, id="catalogue")


def main() -> None:
    db.create_tables()
    print(f"[scheduler] prices every {settings.PRICE_REFRESH_MINUTES}m, "
          f"news every {settings.NEWS_REFRESH_MINUTES}m")

    # Bring everything current on start rather than idling until the first tick.
    jobs.catch_up()
    jobs.refresh_prices()
    jobs.refresh_news()
    jobs.aggregate_sentiment()

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print("[scheduler] stopped")
        scheduler.shutdown(wait=False)


if __name__ == "__main__":
    main()
