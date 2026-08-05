"""The optional catalogue seed.

The loader is small, but it is the one thing standing between a shipped file and
the `stocks` table, and a silent failure there looks exactly like "search is a
bit rubbish today" rather than an error.
"""
from __future__ import annotations

import json

import pytest

import db
import seed_catalogue
import settings


def write_seed(tmp_path, *instruments: tuple):
    path = tmp_path / "catalogue.json"
    path.write_text(json.dumps([
        {"symbol": s, "name": n, "type": t, "currency": c}
        for s, n, t, c in instruments
    ]), encoding="utf-8")
    return path


class TestSeedCatalogue:
    def test_loads_instruments(self, temp_db, tmp_path):
        path = write_seed(tmp_path,
                          ("RKLB", "Rocket Lab Corporation", "STOCK", "USD"),
                          ("SHEL.L", "Shell plc", "STOCK", "GBP"))
        assert seed_catalogue.seed(path) == 2

        rocket = db.stocks.get_stock("RKLB")
        assert rocket["name"] == "Rocket Lab Corporation"
        assert rocket["type"] == "STOCK"
        assert rocket["currency_code"] == "USD"

    def test_seeded_instruments_are_searchable(self, temp_db, tmp_path):
        """The whole point of seeding: local search answers before anything has
        been followed."""
        seed_catalogue.seed(write_seed(
            tmp_path, ("RKLB", "Rocket Lab Corporation", "STOCK", "USD")))
        assert [s["short_name"] for s in db.stocks.search_stocks("rocket")] == ["RKLB"]

    def test_re_running_is_idempotent(self, temp_db, tmp_path):
        """Re-seeding after a rebuild must not double the catalogue."""
        path = write_seed(tmp_path, ("RKLB", "Rocket Lab Corporation", "STOCK", "USD"))
        assert seed_catalogue.seed(path) == 1
        assert seed_catalogue.seed(path) == 0
        assert db.stocks.count_stocks() == 1

    def test_a_blank_currency_is_stored_as_null(self, temp_db, tmp_path):
        """Yahoo does not price every instrument, so the column is optional.
        An empty value must not become the string "" — `to_stock` falls back to
        the quote currency and "" would win over it."""
        seed_catalogue.seed(write_seed(tmp_path, ("XYZ", "Some Fund", "ETF", "")))
        assert db.stocks.get_stock("XYZ")["currency_code"] is None

    def test_seeding_does_not_disturb_a_followed_stock(self, stocked_db, tmp_path):
        """Re-seeding refreshes names, but resolution and quotes are the app's,
        not the file's — a seed must never blank them."""
        seed_catalogue.seed(write_seed(tmp_path, ("AAPL", "Apple Inc.", "STOCK", "USD")))

        apple = db.stocks.get_stock("AAPL")
        assert apple["name"] == "Apple Inc."      # refreshed from the file
        assert apple["yahoo_symbol"] == "AAPL"    # resolution survives
        assert apple["price"] == 338.19           # so does the quote
        assert "AAPL" in db.watchlist.get_symbols()


class TestSeedOnStartup:
    """`seed_if_empty` runs in the API's lifespan, so its failure modes are
    startup failure modes."""

    @pytest.fixture(autouse=True)
    def _seeding_on(self, monkeypatch, tmp_path):
        """conftest disables startup seeding suite-wide; these tests are the
        ones that need it on, pointed at a fixture file."""
        monkeypatch.setattr(settings, "SEED_ON_START", True)
        monkeypatch.setattr(seed_catalogue, "CATALOGUE", write_seed(
            tmp_path, ("RKLB", "Rocket Lab Corporation", "STOCK", "USD")))

    def test_seeds_an_empty_catalogue(self, temp_db):
        assert seed_catalogue.seed_if_empty() == 1
        assert db.stocks.get_stock("RKLB")["name"] == "Rocket Lab Corporation"

    def test_does_nothing_when_the_catalogue_has_rows(self, stocked_db):
        """A second boot must not re-upsert ten thousand rows, and a user who
        has built their own catalogue must not have ours merged into it."""
        before = db.stocks.count_stocks()
        assert seed_catalogue.seed_if_empty() == 0
        assert db.stocks.count_stocks() == before
        assert db.stocks.get_stock("RKLB") is None

    def test_respects_the_off_switch(self, temp_db, monkeypatch):
        monkeypatch.setattr(settings, "SEED_ON_START", False)
        assert seed_catalogue.seed_if_empty() == 0
        assert db.stocks.count_stocks() == 0

    def test_a_missing_seed_file_is_not_an_error(self, temp_db, monkeypatch, tmp_path):
        monkeypatch.setattr(seed_catalogue, "CATALOGUE", tmp_path / "absent.json")
        assert seed_catalogue.seed_if_empty() == 0

    def test_a_corrupt_seed_file_does_not_stop_startup(self, temp_db, monkeypatch, tmp_path):
        """Degrade to thin local search, never to a dead API."""
        broken = tmp_path / "broken.json"
        broken.write_text("{not json", encoding="utf-8")
        monkeypatch.setattr(seed_catalogue, "CATALOGUE", broken)
        assert seed_catalogue.seed_if_empty() == 0
