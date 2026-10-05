"""Whether a symbol's exchange is in session, judged on the exchange's clock.

Two places judged it on the clock of the machine running Aria. The snapshot
header said "Market open" on any local weekday, so at 09:00 on Monday in
Shanghai — Sunday evening in New York — AAPL was "Market open". The context
sent to the model compared local hours with New York's 09:30–16:00, so a user
in Beijing had the US market "open" through the New York night.

Exchange holidays are not known here: on a holiday the usual hours still read
as a session. An unknown exchange, or a time zone this machine lacks, gives
``None``, and callers then say nothing rather than guess.
"""

from __future__ import annotations

import re
from datetime import datetime, time, timezone

try:
    from zoneinfo import ZoneInfo
except ImportError:                    # pragma: no cover - Python < 3.9
    ZoneInfo = None                    # type: ignore[assignment]

_EU = ((time(9, 0), time(17, 30)),)

# Exchange -> (time zone, regular sessions in local time).
_EXCHANGES: dict[str, tuple[str, tuple[tuple[time, time], ...]]] = {
    "US": ("America/New_York", ((time(9, 30), time(16, 0)),)),
    "CN": ("Asia/Shanghai", ((time(9, 30), time(11, 30)), (time(13, 0), time(15, 0)))),
    "HK": ("Asia/Hong_Kong", ((time(9, 30), time(12, 0)), (time(13, 0), time(16, 0)))),
    "JP": ("Asia/Tokyo", ((time(9, 0), time(11, 30)), (time(12, 30), time(15, 30)))),
    "UK": ("Europe/London", ((time(8, 0), time(16, 30)),)),
    "FR": ("Europe/Paris", _EU),
    "DE": ("Europe/Berlin", _EU),
    "NL": ("Europe/Amsterdam", _EU),
    "IT": ("Europe/Rome", _EU),
    "ES": ("Europe/Madrid", _EU),
}

_SUFFIXES = {
    ".HK": "HK", ".SS": "CN", ".SZ": "CN", ".SH": "CN", ".T": "JP", ".L": "UK",
    ".PA": "FR", ".DE": "DE", ".AS": "NL", ".MI": "IT", ".MC": "ES",
}

# US extended hours, New York time.
_US_PRE = (time(4, 0), time(9, 30))
_US_POST = (time(16, 0), time(20, 0))


def exchange_for(symbol: str) -> str | None:
    """"US", "CN", "HK", … for a symbol; "CRYPTO" for a coin pair; None if unknown."""
    s = str(symbol or "").strip().upper()
    if not s or s.startswith("^") or s.endswith(("=X", "=F")):
        return None
    if re.fullmatch(r"[A-Z0-9]{2,10}-(USD|USDT|USDC|EUR)", s):
        return "CRYPTO"
    for suffix, exchange in _SUFFIXES.items():
        if s.endswith(suffix):
            return exchange
    if re.fullmatch(r"(SH|SZ)?\d{6}", s):
        return "CN"
    if re.fullmatch(r"[A-Z]{1,5}([.-][A-Z])?", s):
        return "US"
    return None


def _local_now(exchange: str, now: datetime | None) -> datetime | None:
    if ZoneInfo is None:
        return None
    try:
        zone = ZoneInfo(_EXCHANGES[exchange][0])
    except Exception:                  # no tz database on this machine
        return None
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.astimezone()   # a naive time is this machine's local time
    return moment.astimezone(zone)


def market_session(symbol: str, now: datetime | None = None) -> str | None:
    """"open", "pre", "post", "closed" or "24/7" for the symbol's exchange; None if unknown."""
    exchange = exchange_for(symbol)
    if exchange == "CRYPTO":
        return "24/7"
    if exchange is None:
        return None
    local = _local_now(exchange, now)
    if local is None:
        return None
    if local.weekday() >= 5:
        return "closed"
    clock = local.time()
    if any(start <= clock < end for start, end in _EXCHANGES[exchange][1]):
        return "open"
    if exchange == "US":
        if _US_PRE[0] <= clock < _US_PRE[1]:
            return "pre"
        if _US_POST[0] <= clock < _US_POST[1]:
            return "post"
    return "closed"
