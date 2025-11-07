#!/usr/bin/env python3
"""Download daily OHLCV histories for the intersection coins across key exchanges.

The script reads `data/common_coins.json`, resolves an appropriate spot market
for each coin on the supported exchanges, then fetches every available daily
candle from the listing date through today. Results are written per-coin under
`data/daily_histories/<COIN>.json` by default.

Exchanges and data sources:
* Binance, Bybit, OKX, Upbit → via CCXT (public REST)
* Coinbase (Advanced Trade / legacy Pro endpoint) → direct REST
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import ccxt  # type: ignore
from ccxt.base.errors import BaseError as CCXTError  # type: ignore

UTC = timezone.utc
DAY_MS = 86_400_000
USER_AGENT = "does-coin-leave-on-applause/daily-histories (+github.com/sueun-dev)"
DEFAULT_COINS_FILE = Path("data/common_coins.json")
DEFAULT_OUTPUT_DIR = Path("data/daily_histories")

# Preferred quote currencies per exchange (ordered by priority).
QUOTE_PRIORITY: Dict[str, Sequence[str]] = {
    "binance": ("USDT", "FDUSD", "BUSD", "USDC", "BTC", "ETH", "BNB", "TRY"),
    "bybit": ("USDT", "USDC", "BTC", "ETH"),
    "okx": ("USDT", "USDC", "BTC", "ETH"),
    "upbit": ("KRW",),
    "coinbase": ("USD", "USDC", "USDT", "BTC", "EUR", "GBP"),
}

# Max candles per request for CCXT fetchers.
CCXT_LIMIT_OVERRIDE: Dict[str, int] = {
    "binance": 1000,
    "bybit": 1000,
    "okx": 100,
    "upbit": 200,
}


class FetchError(RuntimeError):
    """Raised when a market cannot be resolved or data download fails."""


def isoformat_from_ms(ts_ms: int) -> str:
    return datetime.fromtimestamp(ts_ms / 1000, tz=UTC).isoformat().replace("+00:00", "Z")


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def fetch_json(url: str, params: Optional[Dict[str, object]] = None) -> object:
    """Simple JSON GET helper for Coinbase public endpoints."""
    if params:
        query = urlencode({k: v for k, v in params.items() if v is not None})
        full_url = f"{url}?{query}"
    else:
        full_url = url
    request = Request(
        full_url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        },
    )
    try:
        with urlopen(request, timeout=30) as response:
            if response.status != 200:
                raise FetchError(f"{full_url} returned HTTP {response.status}")
            payload = response.read()
    except HTTPError as exc:
        raise FetchError(f"HTTP error while fetching {full_url}: {exc}") from exc
    except URLError as exc:
        raise FetchError(f"Network error while fetching {full_url}: {exc}") from exc
    return json.loads(payload)


def load_common_coins(path: Path, only: Optional[Sequence[str]] = None) -> List[str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    coins = data.get("coins") or []
    if only:
        want = {coin.upper() for coin in only}
        coins = [coin for coin in coins if coin.upper() in want]
    return [coin.upper() for coin in coins]


def normalize_number(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float)):
        return f"{value}"
    return str(value)


def build_candle(ts_ms: int, open_, high, low, close, volume) -> Dict[str, object]:
    return {
        "timestamp_ms": int(ts_ms),
        "timestamp_iso": isoformat_from_ms(int(ts_ms)),
        "open": normalize_number(open_),
        "high": normalize_number(high),
        "low": normalize_number(low),
        "close": normalize_number(close),
        "volume": normalize_number(volume),
    }


@dataclass
class MarketRef:
    exchange: str
    base: str
    quote: str
    symbol: str  # display form, e.g., BTC/USDT
    market_id: str  # identifier used for API calls (may differ from symbol)


class BaseMarketFetcher:
    name: str
    display_name: str

    def prepare(self) -> None:
        raise NotImplementedError

    def resolve_market(self, base: str) -> MarketRef:
        raise NotImplementedError

    def fetch_candles(
        self,
        market: MarketRef,
        since_ms: Optional[int] = None,
    ) -> List[Dict[str, object]]:
        raise NotImplementedError


class CCXTExchangeFetcher(BaseMarketFetcher):
    def __init__(self, name: str, ccxt_id: str):
        self.name = name
        self.display_name = name.capitalize()
        self.ccxt_id = ccxt_id
        self.client: Optional[ccxt.Exchange] = None
        self.market_map: Dict[str, List[MarketRef]] = {}

    def prepare(self) -> None:
        if self.client is not None:
            return
        params: Dict[str, object] = {"enableRateLimit": True, "timeout": 30_000}
        if self.ccxt_id in ("bybit", "okx"):
            params["options"] = {"defaultType": "spot"}
        exchange_class = getattr(ccxt, self.ccxt_id)
        self.client = exchange_class(params)
        markets = self.client.load_markets()
        for market in markets.values():
            if not market.get("spot", True):
                continue
            base = (market.get("base") or "").upper()
            quote = (market.get("quote") or "").upper()
            if not base or not quote:
                continue
            ref = MarketRef(
                exchange=self.name,
                base=base,
                quote=quote,
                symbol=market.get("symbol") or f"{base}/{quote}",
                market_id=market.get("id") or market.get("symbol") or f"{base}/{quote}",
            )
            self.market_map.setdefault(base, []).append(ref)
        priorities = QUOTE_PRIORITY.get(self.name, ())
        for base, refs in self.market_map.items():
            refs.sort(key=lambda ref: (self._priority_index(priorities, ref.quote), ref.symbol))

    def _priority_index(self, priorities: Sequence[str], quote: str) -> int:
        try:
            return priorities.index(quote)
        except ValueError:
            return len(priorities)

    def resolve_market(self, base: str) -> MarketRef:
        self.prepare()
        refs = self.market_map.get(base.upper())
        if not refs:
            raise FetchError(f"{self.display_name} has no spot market for {base}")
        return refs[0]

    def fetch_candles(
        self,
        market: MarketRef,
        since_ms: Optional[int] = None,
    ) -> List[Dict[str, object]]:
        assert self.client is not None
        limit = CCXT_LIMIT_OVERRIDE.get(self.ccxt_id, 1000)
        timeframe = "1d"
        duration_ms = int(self.client.parse_timeframe(timeframe) * 1000)
        since: Optional[int] = since_ms
        candles: Dict[int, Dict[str, object]] = {}
        last_ts: Optional[int] = None
        while True:
            try:
                batch = self.client.fetch_ohlcv(
                    market.market_id,
                    timeframe=timeframe,
                    since=since,
                    limit=limit,
                )
            except CCXTError as exc:
                raise FetchError(f"{self.display_name} OHLCV fetch failed for {market.symbol}: {exc}") from exc
            if not batch:
                break
            new_points = 0
            for entry in batch:
                ts = int(entry[0])
                if last_ts is not None and ts <= last_ts:
                    continue
                candles[ts] = build_candle(ts, entry[1], entry[2], entry[3], entry[4], entry[5])
                new_points += 1
                last_ts = ts
            if len(batch) < limit or new_points == 0:
                break
            since = (batch[-1][0] + duration_ms)
        ordered = [candles[ts] for ts in sorted(candles)]
        if not ordered:
            raise FetchError(f"{self.display_name} returned no data for {market.symbol}")
        return ordered


class CoinbaseFetcher(BaseMarketFetcher):
    PRODUCTS_URL = "https://api.exchange.coinbase.com/products"
    CANDLES_URL_TEMPLATE = "https://api.exchange.coinbase.com/products/{product_id}/candles"

    def __init__(self) -> None:
        self.name = "coinbase"
        self.display_name = "Coinbase"
        self.market_map: Dict[str, List[MarketRef]] = {}

    def prepare(self) -> None:
        if self.market_map:
            return
        data = fetch_json(self.PRODUCTS_URL)
        priorities = QUOTE_PRIORITY.get(self.name, ())
        for product in data:
            if product.get("status") != "online":
                continue
            base = (product.get("base_currency") or "").upper()
            quote = (product.get("quote_currency") or "").upper()
            product_id = product.get("id")
            if not base or not quote or not product_id:
                continue
            ref = MarketRef(
                exchange=self.name,
                base=base,
                quote=quote,
                symbol=f"{base}/{quote}",
                market_id=product_id,
            )
            self.market_map.setdefault(base, []).append(ref)
        for base, refs in self.market_map.items():
            refs.sort(key=lambda ref: (self._priority_index(priorities, ref.quote), ref.symbol))

    def _priority_index(self, priorities: Sequence[str], quote: str) -> int:
        try:
            return priorities.index(quote)
        except ValueError:
            return len(priorities)

    def resolve_market(self, base: str) -> MarketRef:
        self.prepare()
        refs = self.market_map.get(base.upper())
        if not refs:
            raise FetchError(f"Coinbase has no market for {base}")
        return refs[0]

    def fetch_candles(
        self,
        market: MarketRef,
        since_ms: Optional[int] = None,
    ) -> List[Dict[str, object]]:
        if since_ms:
            start = datetime.fromtimestamp(since_ms / 1000, tz=UTC)
        else:
            start = datetime(2015, 1, 1, tzinfo=UTC)
        now = datetime.now(tz=UTC)
        window = timedelta(days=300)
        candles: Dict[int, Dict[str, object]] = {}
        while start < now:
            end = min(start + window, now)
            params = {
                "granularity": 86_400,  # 1 day in seconds
                "start": start.isoformat().replace("+00:00", "Z"),
                "end": end.isoformat().replace("+00:00", "Z"),
            }
            url = self.CANDLES_URL_TEMPLATE.format(product_id=market.market_id)
            batch = fetch_json(url, params=params)
            for entry in batch:
                ts_sec = int(entry[0])
                ts_ms = ts_sec * 1000
                low, high, open_, close, volume = entry[1:6]
                candles[ts_ms] = build_candle(ts_ms, open_, high, low, close, volume)
            start = end
            time.sleep(0.2)
        ordered = [candles[ts] for ts in sorted(candles)]
        if not ordered:
            raise FetchError(f"Coinbase returned no data for {market.symbol}")
        return ordered


def build_fetchers(names: Sequence[str]) -> List[BaseMarketFetcher]:
    fetchers: List[BaseMarketFetcher] = []
    for name in names:
        key = name.lower()
        if key == "coinbase":
            fetchers.append(CoinbaseFetcher())
        elif key in ("binance", "bybit", "okx", "upbit"):
            fetchers.append(CCXTExchangeFetcher(key, key))
        else:
            raise ValueError(f"Unsupported exchange '{name}'")
    return fetchers


def load_existing_coin(path: Path) -> Optional[Dict[str, object]]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def merge_candle_lists(
    existing: Optional[List[Dict[str, object]]],
    new: List[Dict[str, object]],
) -> List[Dict[str, object]]:
    if not existing:
        return sorted(new, key=lambda item: int(item["timestamp_ms"]))
    combined: Dict[int, Dict[str, object]] = {int(item["timestamp_ms"]): item for item in existing}
    for entry in new:
        combined[int(entry["timestamp_ms"])] = entry
    return [combined[key] for key in sorted(combined)]


def serialize_coin_payload(coin: str, markets: Dict[str, Dict[str, object]]) -> Dict[str, object]:
    return {
        "coin": coin,
        "generated_at": datetime.now(tz=UTC).isoformat().replace("+00:00", "Z"),
        "exchanges": markets,
    }


def harvest_coin(
    coin: str,
    fetchers: Iterable[BaseMarketFetcher],
    logger: logging.Logger,
    existing_exchanges: Optional[Dict[str, Dict[str, object]]] = None,
    incremental: bool = True,
) -> Dict[str, Dict[str, object]]:
    results: Dict[str, Dict[str, object]] = {}
    for fetcher in fetchers:
        try:
            market = fetcher.resolve_market(coin)
        except FetchError as exc:
            logger.warning("Skipping %s on %s: %s", coin, fetcher.display_name, exc)
            continue
        existing_exchange = (existing_exchanges or {}).get(fetcher.name, {})
        since_ms = None
        if incremental and existing_exchange:
            candles_list = existing_exchange.get("candles") or []
            if candles_list:
                since_ms = int(candles_list[-1]["timestamp_ms"]) + DAY_MS

        logger.info(
            "Fetching %s daily candles on %s (%s)%s",
            coin,
            fetcher.display_name,
            market.symbol,
            f" starting {isoformat_from_ms(since_ms)}" if since_ms else "",
        )
        try:
            candles = fetcher.fetch_candles(market, since_ms=since_ms)
        except FetchError as exc:
            logger.error("Failed to fetch %s on %s: %s", coin, fetcher.display_name, exc)
            if incremental and existing_exchange:
                logger.info("Retaining previously stored data for %s on %s", coin, fetcher.display_name)
                results[fetcher.name] = existing_exchange
            continue
        if incremental and existing_exchange:
            merged = merge_candle_lists(existing_exchange.get("candles"), candles)
        else:
            merged = sorted(candles, key=lambda item: int(item["timestamp_ms"]))
        if not merged:
            logger.warning("No exchange data collected for %s on %s", coin, fetcher.display_name)
            continue
        results[fetcher.name] = {
            "market": market.symbol,
            "quote": market.quote,
            "count": len(merged),
            "candles": merged,
        }
    return results


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch daily OHLCV for coins listed on every exchange.",
    )
    parser.add_argument(
        "--coins-file",
        type=Path,
        default=DEFAULT_COINS_FILE,
        help=f"Path to common coins JSON (default: {DEFAULT_COINS_FILE})",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Directory to store per-coin histories (default: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--exchanges",
        nargs="+",
        default=["binance", "coinbase", "bybit", "upbit", "okx"],
        help="Subset of exchanges to include (default: all)",
    )
    parser.add_argument(
        "--only",
        nargs="+",
        help="Optional subset of coin tickers to process (case-insensitive).",
    )
    parser.add_argument(
        "--max-coins",
        type=int,
        help="Process at most N coins (useful for smoke tests).",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip coins whose output file already exists.",
    )
    parser.add_argument(
        "--full-refresh",
        action="store_true",
        help="Ignore existing files and re-download all history from scratch.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging verbosity (default: INFO)",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
    logger = logging.getLogger("daily_histories")

    if not args.coins_file.exists():
        logger.error("Coins file %s not found", args.coins_file)
        return 1

    try:
        coins = load_common_coins(args.coins_file, args.only)
    except Exception as exc:
        logger.error("Unable to read coins from %s: %s", args.coins_file, exc)
        return 1

    if args.max_coins:
        coins = coins[: args.max_coins]

    fetchers = build_fetchers(args.exchanges)
    for fetcher in fetchers:
        logger.info("Preparing metadata for %s", fetcher.display_name)
        fetcher.prepare()

    ensure_dir(args.output_dir)
    total = len(coins)
    for idx, coin in enumerate(coins, start=1):
        output_path = args.output_dir / f"{coin}.json"
        if args.skip_existing and output_path.exists() and not args.full_refresh:
            logger.info("Skipping %s (%d/%d) – already exists", coin, idx, total)
            continue
        logger.info("Processing %s (%d/%d)", coin, idx, total)
        existing_payload = None if args.full_refresh else load_existing_coin(output_path)
        existing_exchanges = (existing_payload or {}).get("exchanges") or {}
        markets = harvest_coin(
            coin,
            fetchers,
            logger,
            existing_exchanges=existing_exchanges,
            incremental=not args.full_refresh,
        )
        if not markets and existing_exchanges and not args.full_refresh:
            logger.info("No updates for %s; retaining existing dataset", coin)
            markets = existing_exchanges
        elif existing_exchanges and not args.full_refresh:
            merged_markets = existing_exchanges.copy()
            merged_markets.update(markets)
            markets = merged_markets
        if not markets:
            logger.warning("No exchange data collected for %s; skipping write", coin)
            continue
        payload = serialize_coin_payload(coin, markets)
        output_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        logger.info(
            "Wrote %s with %s exchanges (%d total candles)",
            output_path,
            ", ".join(sorted(markets.keys())),
            sum(entry["count"] for entry in markets.values()),
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
