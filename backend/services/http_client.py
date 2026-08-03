"""The scraping substrate: one polite-but-aggressive HTTP client.

Everything that talks to a third party goes through here so that rate limiting,
retries, backoff and failure isolation are decided in one place instead of
being reinvented (or forgotten) per scraper.

How it pushes throughput without getting blocked:

* **Adaptive per-host rate.** Each host starts at a conservative request rate
  and ratchets *up* while responses stay clean, then halves the moment a host
  answers 429/403/503. So we discover a host's real ceiling instead of guessing
  a fixed sleep, and we stop hammering the instant it complains.
* **Retry-After is obeyed.** When a host tells us how long to wait, waiting
  exactly that long is both the polite and the fastest-to-recover option.
* **Circuit breaker.** After repeated failures a host is dropped for a cooling
  period, with exponential extension. One dead source can't stall a refresh.
* **Stable browser fingerprints per host.** A consistent, realistic header set
  per host looks like a browser session; randomising headers on every request
  to the same host looks like exactly what it is. The fingerprint is rotated
  only when a host starts pushing back.
* **Connection reuse** (keep-alive), so many requests share one negotiated
  connection instead of re-handshaking. HTTP/1.1 only — see `http2=False`.
* **Short-lived response cache**, so several scrapers wanting the same feed in
  one refresh cost one request.

Deliberately not here: proxy rotation, CAPTCHA solving, or anything that
defeats an access control rather than sharing a host's capacity fairly. Where a
source pushes back, the answer is another source — hence the fallback chains in
prices.py and news/.
"""
from __future__ import annotations

import random
import threading
import time
from dataclasses import dataclass, field
from urllib.parse import urlsplit

import httpx

import settings

# ── Browser fingerprints ─────────────────────────────────────────────────
# Real, current header sets. A mismatched trio (Chrome UA + Firefox Accept +
# no sec-ch-ua) is a stronger bot signal than an old UA, so these are kept
# internally consistent.
_FINGERPRINTS: list[dict[str, str]] = [
    {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
        "sec-ch-ua": '"Chromium";v="140", "Not=A?Brand";v="24", "Google Chrome";v="140"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "Accept-Language": "en-GB,en;q=0.9",
    },
    {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36",
        "sec-ch-ua": '"Chromium";v="139", "Not=A?Brand";v="24", "Google Chrome";v="139"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"macOS"',
        "Accept-Language": "en-US,en;q=0.9",
    },
    {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:130.0) "
                      "Gecko/20100101 Firefox/130.0",
        "Accept-Language": "en-GB,en;q=0.8",
    },
    {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
                      "(KHTML, like Gecko) Version/18.0 Safari/605.1.15",
        "Accept-Language": "en-GB,en;q=0.9",
    },
]

_BASE_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
              "application/rss+xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
    "Connection": "keep-alive",
}

# Per-host starting/ceiling request rates, requests per second. Yahoo's JSON
# endpoints tolerate a lot; Google News throttles a scraped RSS search sooner.
#
# Where a host publishes a limit we honour it as a hard ceiling rather than
# probing up into it: SEC's fair-access policy states 10 req/s, so the ceiling
# here stays well under that.
_HOST_RATES: dict[str, tuple[float, float]] = {
    "query1.finance.yahoo.com": (4.0, 12.0),
    "query2.finance.yahoo.com": (4.0, 12.0),
    "feeds.finance.yahoo.com": (3.0, 8.0),
    "news.google.com": (1.5, 5.0),
    "finviz.com": (1.0, 3.0),
    "www.bing.com": (1.0, 4.0),
    "api.nasdaq.com": (1.0, 4.0),
    "www.nasdaq.com": (1.0, 3.0),
    "www.sec.gov": (2.0, 8.0),
    "quote.cnbc.com": (2.0, 6.0),
}
_DEFAULT_RATE = (1.5, 4.0)
_MIN_RATE = 0.2
# How far behind "now" the slot cursor may start, i.e. how much of an idle
# host's unused capacity is still spendable at once. Preserves the burst the
# old token bucket allowed.
_BURST_SECONDS = 1.0

_THROTTLE_STATUSES = frozenset({403, 420, 429, 503})
_RETRY_STATUSES = frozenset({408, 425, 500, 502, 504, 522, 524}) | _THROTTLE_STATUSES

# Successes needed before probing a higher rate.
_PROBE_AFTER = 8
_PROBE_FACTOR = 1.25
_THROTTLE_FACTOR = 0.5
_BREAKER_THRESHOLD = 5
_BREAKER_BASE_COOLDOWN = 45.0
_BREAKER_MAX_COOLDOWN = 600.0


@dataclass(slots=True)
class Fetched:
    """A response, detached from the client so it can be cached safely."""
    url: str
    status: int
    text: str
    content: bytes
    headers: dict
    from_cache: bool = False

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300

    def json(self):
        import json
        return json.loads(self.text)


@dataclass(slots=True)
class _HostState:
    rate: float
    max_rate: float
    # Monotonic time of the next unreserved request slot. See `_acquire`.
    next_slot: float = 0.0
    consecutive_ok: int = 0
    consecutive_fail: int = 0
    blocked_until: float = 0.0
    breaker_trips: int = 0
    fingerprint: int = field(default_factory=lambda: random.randrange(len(_FINGERPRINTS)))
    requests: int = 0
    throttled: int = 0
    failures: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock)


class Scraper:
    """Thread-safe. Construct one and share it (see the module-level `scraper`).

    `clock` and `sleep` are injectable so the limiter and breaker can be tested
    without real time passing.
    """

    def __init__(
        self,
        *,
        timeout: float | None = None,
        max_retries: int | None = None,
        cache_ttl: float | None = None,
        transport: httpx.BaseTransport | None = None,
        clock=time.monotonic,
        sleep=time.sleep,
    ):
        self.timeout = timeout if timeout is not None else settings.SCRAPE_TIMEOUT
        self.max_retries = max_retries if max_retries is not None else settings.SCRAPE_MAX_RETRIES
        self.cache_ttl = cache_ttl if cache_ttl is not None else settings.SCRAPE_CACHE_TTL
        self._clock = clock
        self._sleep = sleep
        self._hosts: dict[str, _HostState] = {}
        self._hosts_lock = threading.Lock()
        self._cache: dict[str, tuple[float, Fetched]] = {}
        self._cache_lock = threading.Lock()
        self._client = httpx.Client(
            # HTTP/1.1 only. Under threads h2 multiplexes every request onto one
            # connection whose hpack dynamic table is a deque mutated without a
            # lock, which raises "deque mutated during iteration" mid-sweep. No
            # host here needs h2 and nothing reads response.http_version;
            # keep-alive still reuses connections, and the pool below then has
            # no shared per-connection state to corrupt.
            http2=False,
            follow_redirects=True,
            timeout=httpx.Timeout(self.timeout, connect=min(6.0, self.timeout)),
            limits=httpx.Limits(max_connections=settings.SCRAPE_CONCURRENCY * 2,
                                max_keepalive_connections=settings.SCRAPE_CONCURRENCY),
            transport=transport,
        )

    # ── public ───────────────────────────────────────────────────────────

    def get(
        self,
        url: str,
        *,
        params: dict | None = None,
        headers: dict | None = None,
        cache: bool = True,
        retries: int | None = None,
    ) -> Fetched | None:
        """Fetch a URL. Returns None if it never succeeded — callers treat that
        as "this source had nothing" and move to the next one."""
        cache_key = self._cache_key(url, params)
        if cache and (hit := self._cache_get(cache_key)):
            return hit

        host = _host_of(url)
        state = self._state(host)
        attempts = (retries if retries is not None else self.max_retries) + 1

        for attempt in range(attempts):
            if not self._acquire(state):
                return None  # circuit open

            try:
                response = self._client.get(
                    url, params=params, headers=self._headers(state, headers)
                )
            except httpx.HTTPError as exc:
                self._on_failure(state)
                if attempt == attempts - 1:
                    print(f"[scrape] {host} gave up after {attempts}: {type(exc).__name__}")
                    return None
                self._sleep(self._backoff(attempt))
                continue

            if response.status_code in _RETRY_STATUSES:
                throttled = response.status_code in _THROTTLE_STATUSES
                if throttled:
                    self._on_throttle(state, _retry_after(response))
                else:
                    self._on_failure(state)
                if attempt == attempts - 1:
                    print(f"[scrape] {host} -> {response.status_code} after {attempts} tries")
                    return None
                self._sleep(_retry_after(response) or self._backoff(attempt))
                continue

            # A 404 is a real answer, not evidence we can go faster. Letting it
            # count made miss-heavy traffic (symbols.resolve tries up to four
            # candidates by design) probe every host up to its ceiling.
            self._on_success(state, probe=response.is_success)
            fetched = Fetched(
                url=str(response.url),
                status=response.status_code,
                text=response.text,
                content=response.content,
                headers=dict(response.headers),
            )
            if cache and fetched.ok:
                self._cache_put(cache_key, fetched)
            return fetched

        return None

    def get_json(self, url: str, **kwargs) -> dict | list | None:
        result = self.get(url, **kwargs)
        if not result or not result.ok:
            return None
        try:
            return result.json()
        except ValueError:
            print(f"[scrape] {_host_of(url)} returned non-JSON")
            return None

    def get_many(self, requests: list[dict]) -> list[Fetched | None]:
        """Run several `get` calls concurrently, preserving input order.

        Each dict is kwargs for `get`, with `url` included. Per-host token
        buckets still apply, so this parallelises *across* hosts and stays
        polite *within* one.
        """
        if not requests:
            return []
        if len(requests) == 1:
            return [self.get(**requests[0])]

        from concurrent.futures import ThreadPoolExecutor

        workers = min(settings.SCRAPE_CONCURRENCY, len(requests))
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="scrape") as pool:
            return list(pool.map(lambda kw: self.get(**kw), requests))

    def stats(self) -> list[dict]:
        """Per-host counters, exposed on /health so throttling is visible."""
        now = self._clock()
        with self._hosts_lock:
            items = list(self._hosts.items())
        return sorted(
            (
                {
                    "host": host,
                    "requests": s.requests,
                    "throttled": s.throttled,
                    "failures": s.failures,
                    "rate_per_sec": round(s.rate, 2),
                    "max_rate": s.max_rate,
                    "circuit_open": s.blocked_until > now,
                }
                for host, s in items
            ),
            key=lambda d: -d["requests"],
        )

    def close(self) -> None:
        self._client.close()

    # ── rate limiting / breaker ──────────────────────────────────────────

    def _state(self, host: str) -> _HostState:
        with self._hosts_lock:
            state = self._hosts.get(host)
            if state is None:
                start, ceiling = _HOST_RATES.get(host, _DEFAULT_RATE)
                state = _HostState(rate=start, max_rate=ceiling)
                self._hosts[host] = state
            return state

    def _acquire(self, state: _HostState) -> bool:
        """Reserve a slot and wait for it. False means the circuit is open.

        Virtual scheduling, not a token bucket. A *count* cannot be reserved
        without holding the lock across the sleep, so every waiter used to read
        the same empty bucket, compute the same wait and proceed — making the
        real rate `nominal × threads`. A *cursor* is advanced under the lock and
        waited for outside it, so N threads take N distinct slots.
        """
        with state.lock:
            now = self._clock()
            if state.blocked_until > now:
                return False
            slot = max(state.next_slot, now - _BURST_SECONDS)
            state.next_slot = slot + 1.0 / state.rate
            state.requests += 1

        # No jitter: it only existed to desynchronise lockstep waiters, which
        # distinct slots now prevent by construction.
        if (wait := slot - now) > 0:
            self._sleep(wait)
            # A queue of waiters must not all land on a host that started
            # refusing while they slept.
            with state.lock:
                if state.blocked_until > self._clock():
                    return False
        return True

    def _on_success(self, state: _HostState, probe: bool = True) -> None:
        """`probe=False` clears the failure run without counting toward a rate
        increase — for answers that are final but not 2xx, e.g. a 404."""
        with state.lock:
            state.consecutive_fail = 0
            state.breaker_trips = 0
            if not probe:
                return
            state.consecutive_ok += 1
            if state.consecutive_ok >= _PROBE_AFTER and state.rate < state.max_rate:
                state.rate = min(state.max_rate, state.rate * _PROBE_FACTOR)
                state.consecutive_ok = 0

    def _on_throttle(self, state: _HostState, retry_after: float | None) -> None:
        with state.lock:
            state.throttled += 1
            state.consecutive_ok = 0
            state.rate = max(_MIN_RATE, state.rate * _THROTTLE_FACTOR)
            # A host that dislikes us may dislike this fingerprint; try another.
            state.fingerprint = (state.fingerprint + 1) % len(_FINGERPRINTS)
            if retry_after:
                state.blocked_until = max(state.blocked_until, self._clock() + retry_after)
        self._register_failure(state)

    def _on_failure(self, state: _HostState) -> None:
        with state.lock:
            state.failures += 1
            state.consecutive_ok = 0
        self._register_failure(state)

    def _register_failure(self, state: _HostState) -> None:
        with state.lock:
            state.consecutive_fail += 1
            if state.consecutive_fail >= _BREAKER_THRESHOLD:
                state.breaker_trips += 1
                cooldown = min(
                    _BREAKER_MAX_COOLDOWN,
                    _BREAKER_BASE_COOLDOWN * (2 ** (state.breaker_trips - 1)),
                )
                state.blocked_until = self._clock() + cooldown
                state.consecutive_fail = 0
                print(f"[scrape] circuit open for {cooldown:.0f}s (rate now {state.rate:.2f}/s)")

    def _backoff(self, attempt: int) -> float:
        """Exponential with full jitter: spreads retries instead of syncing them."""
        return random.uniform(0, min(8.0, 0.6 * (2 ** attempt)))

    # ── headers / cache ──────────────────────────────────────────────────

    def _headers(self, state: _HostState, extra: dict | None) -> dict:
        headers = {**_BASE_HEADERS, **_FINGERPRINTS[state.fingerprint]}
        if extra:
            headers.update(extra)
        return headers

    @staticmethod
    def _cache_key(url: str, params: dict | None) -> str:
        if not params:
            return url
        return url + "?" + "&".join(f"{k}={v}" for k, v in sorted(params.items()))

    def _cache_get(self, key: str) -> Fetched | None:
        if self.cache_ttl <= 0:
            return None
        with self._cache_lock:
            entry = self._cache.get(key)
            if not entry:
                return None
            expiry, value = entry
            if expiry < self._clock():
                del self._cache[key]
                return None
        return Fetched(value.url, value.status, value.text, value.content,
                       value.headers, from_cache=True)

    def _cache_put(self, key: str, value: Fetched) -> None:
        if self.cache_ttl <= 0:
            return
        with self._cache_lock:
            if len(self._cache) > 512:          # ponytail: crude cap, it's a
                self._cache.clear()             # 5-minute cache, not a store
            self._cache[key] = (self._clock() + self.cache_ttl, value)

    def clear_cache(self) -> None:
        with self._cache_lock:
            self._cache.clear()


def _host_of(url: str) -> str:
    try:
        return (urlsplit(url).hostname or "unknown").lower()
    except ValueError:
        return "unknown"


def _retry_after(response) -> float | None:
    raw = response.headers.get("Retry-After")
    if not raw:
        return None
    try:
        return max(0.0, min(120.0, float(raw)))     # cap: we'd rather fail over
    except ValueError:
        from normalize import now_utc, parse_datetime
        when = parse_datetime(raw)
        if not when:
            return None
        return max(0.0, min(120.0, (when - now_utc()).total_seconds()))


# The shared instance. Scrapers import this.
scraper = Scraper()
