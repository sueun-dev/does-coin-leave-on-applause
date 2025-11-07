#!/usr/bin/env python3
"""Fetch listed coins for five major exchanges.

Exchanges covered:
1. Binance (spot markets, trading symbols).
2. Coinbase Advanced Trade (spot products).
3. Bybit (spot markets).
4. Upbit KRW market only.
5. OKX (spot instruments).

The script hits each exchange's public REST endpoint, extracts the distinct base
assets (coins) that are currently tradeable, and prints a consolidated JSON
object to stdout or writes it to a file when --output is provided.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import logging
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

DATA_DIR = Path("data")
DEFAULT_OUTPUT_PATH = DATA_DIR / "listed_coins.json"
DEFAULT_COMMON_OUTPUT_PATH = DATA_DIR / "common_coins.json"
USER_AGENT = "does-coin-leave-on-applause/coin-lister (+github.com/sueun-dev)"
logger = logging.getLogger(__name__)
BINANCE_URLS = [
    # Public data mirror accessible from most regions.
    "https://data-api.binance.vision/api/v3/exchangeInfo",
    "https://api.binance.com/api/v3/exchangeInfo",
    # Alternative hosts in case geo-blocks or rate limiting kick in.
    "https://api1.binance.com/api/v3/exchangeInfo",
    "https://api2.binance.com/api/v3/exchangeInfo",
    "https://api3.binance.com/api/v3/exchangeInfo",
    "https://www.binance.com/api/v3/exchangeInfo",
    "https://data.binance.com/api/v3/exchangeInfo",
]
COINBASE_PRODUCTS_URL = "https://api.exchange.coinbase.com/products"
BYBIT_URL = "https://api.bybit.com/v5/market/instruments-info"
COINGECKO_BYBIT_TICKERS_URL = (
    "https://api.coingecko.com/api/v3/exchanges/bybit_spot/tickers"
)
UPBIT_MARKETS_URL = "https://api.upbit.com/v1/market/all"
OKX_URL = "https://www.okx.com/api/v5/public/instruments"


class FetchError(RuntimeError):
    """Raised when an API request fails or returns malformed data."""


def fetch_json(url: str, params: Optional[Dict[str, str]] = None) -> dict | list:
    """Perform a GET request and parse JSON response."""
    if params:
        query = urlencode(params)
        url_with_query = f"{url}?{query}"
    else:
        url_with_query = url

    request = Request(
        url_with_query,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        },
    )
    logger.debug("GET %s", url_with_query)
    try:
        with urlopen(request, timeout=30) as response:
            if response.status != 200:
                raise FetchError(f"{url_with_query} returned status {response.status}")
            payload = response.read()
    except HTTPError as exc:
        raise FetchError(f"HTTP error while fetching {url_with_query}: {exc}") from exc
    except URLError as exc:
        raise FetchError(f"Network error while fetching {url_with_query}: {exc}") from exc
    return json.loads(payload)


def fetch_binance_assets() -> List[str]:
    """Return sorted list of Binance spot base assets that are active."""
    last_error: Optional[Exception] = None
    for url in BINANCE_URLS:
        log_exchange("binance", f"Requesting exchangeInfo from {url}")
        try:
            data = fetch_json(url)
        except FetchError as exc:
            last_error = exc
            log_exchange("binance", f"Endpoint {url} failed ({exc}); trying next", logging.WARNING)
            continue
        symbols = data.get("symbols", [])
        assets = {
            symbol["baseAsset"]
            for symbol in symbols
            if symbol.get("status") == "TRADING" and "baseAsset" in symbol
        }
        log_exchange("binance", f"Fetched {len(assets)} unique base assets from {url}")
        return sorted(assets)
    raise FetchError(f"Binance exchangeInfo failed for all endpoints: {last_error}")


def fetch_coinbase_assets() -> List[str]:
    """Return sorted base currencies from Coinbase Advanced Trade products."""
    log_exchange("coinbase", "Requesting online products list")
    products = fetch_json(COINBASE_PRODUCTS_URL)
    assets = {
        product["base_currency"]
        for product in products
        if product.get("status") == "online" and "base_currency" in product
    }
    log_exchange("coinbase", f"Fetched {len(assets)} base assets")
    return sorted(assets)


def fetch_bybit_assets() -> List[str]:
    """Return sorted base coins from Bybit spot instruments."""
    errors: List[str] = []
    try:
        log_exchange("bybit", "Attempting native Bybit API (v5)")
        return _fetch_bybit_native()
    except FetchError as exc:
        errors.append(f"native API failed: {exc}")
        log_exchange("bybit", f"Native API failed ({exc}); falling back to CoinGecko", logging.WARNING)
    try:
        log_exchange("bybit", "Attempting CoinGecko Bybit spot fallback")
        return _fetch_bybit_via_coingecko()
    except FetchError as exc:
        errors.append(f"CoinGecko fallback failed: {exc}")
        raise FetchError("; ".join(errors)) from exc


def _fetch_bybit_native() -> List[str]:
    assets: Set[str] = set()
    cursor: Optional[str] = None
    page = 1
    while True:
        params = {"category": "spot"}
        if cursor:
            params["cursor"] = cursor
        log_exchange("bybit", f"Native API request page {page} (cursor={cursor})", logging.DEBUG)
        response = fetch_json(BYBIT_URL, params=params)
        result = response.get("result") or {}
        instrument_list: List[dict] = list(result.get("list") or [])
        for instrument in instrument_list:
            if instrument.get("status") == "Trading" and instrument.get("baseCoin"):
                assets.add(instrument["baseCoin"])
        cursor = result.get("nextPageCursor")
        log_exchange(
            "bybit",
            f"Page {page} returned {len(instrument_list)} instruments; accumulated {len(assets)} assets",
            logging.DEBUG,
        )
        if not cursor:
            break
        time.sleep(0.2)  # polite pause for subsequent paged calls
        page += 1
    log_exchange("bybit", f"Native API succeeded with {len(assets)} assets")
    return sorted(assets)


def _fetch_bybit_via_coingecko(max_pages: int = 50) -> List[str]:
    """Fallback path: use CoinGecko's Bybit spot tickers to infer coin list."""
    assets: Set[str] = set()
    for page in range(1, max_pages + 1):
        log_exchange("bybit", f"CoinGecko fallback requesting page {page}", logging.DEBUG)
        data = _fetch_coingecko_with_retry(page)
        tickers: Iterable[dict] = data.get("tickers") or []
        if not tickers:
            if page == 1 and not assets:
                raise FetchError("CoinGecko returned no tickers for Bybit spot (page 1)")
            break
        for ticker in tickers:
            base = ticker.get("base")
            if base:
                assets.add(base.upper())
        log_exchange(
            "bybit",
            f"CoinGecko page {page} yielded {len(tickers)} tickers; accumulated {len(assets)} assets",
            logging.DEBUG,
        )
        time.sleep(10.0)  # respect CoinGecko's stricter anonymous rate limits
    if not assets:
        raise FetchError("CoinGecko returned an empty Bybit spot asset set")
    log_exchange("bybit", f"CoinGecko fallback succeeded with {len(assets)} assets", logging.INFO)
    return sorted(assets)


def _fetch_coingecko_with_retry(page: int, retries: int = 6) -> dict:
    params = {"page": page}
    backoff = 10.0
    for attempt in range(retries):
        try:
            return fetch_json(COINGECKO_BYBIT_TICKERS_URL, params=params)
        except FetchError as exc:
            message = str(exc)
            if "429" in message and attempt < retries - 1:
                log_exchange(
                    "bybit",
                    f"CoinGecko rate limited on page {page}; retrying in {backoff:.1f}s "
                    f"(attempt {attempt + 1}/{retries})",
                    logging.WARNING,
                )
                time.sleep(backoff)
                backoff = min(backoff * 1.5, 30.0)
                continue
            raise


def fetch_upbit_krw_assets() -> List[str]:
    """Return sorted list of coins listed on Upbit's KRW market."""
    log_exchange("upbit_krw", "Requesting full market list")
    markets = fetch_json(UPBIT_MARKETS_URL)
    assets = {
        entry["market"].split("-")[1]
        for entry in markets
        if entry.get("market", "").startswith("KRW-")
    }
    log_exchange("upbit_krw", f"Fetched {len(assets)} KRW-market coins")
    return sorted(assets)


def fetch_okx_assets() -> List[str]:
    """Return sorted base currencies from OKX spot instruments."""
    params = {"instType": "SPOT"}
    log_exchange("okx", "Requesting spot instrument list")
    response = fetch_json(OKX_URL, params=params)
    instruments: Iterable[dict] = response.get("data") or []
    assets = {
        instrument["baseCcy"]
        for instrument in instruments
        if instrument.get("state") == "live" and instrument.get("baseCcy")
    }
    log_exchange("okx", f"Fetched {len(assets)} live spot assets")
    return sorted(assets)


EXCHANGE_FETCHERS = {
    "binance": fetch_binance_assets,
    "coinbase": fetch_coinbase_assets,
    "bybit": fetch_bybit_assets,
    "upbit_krw": fetch_upbit_krw_assets,
    "okx": fetch_okx_assets,
}
EXCHANGE_LABELS = {
    "binance": "Binance",
    "coinbase": "Coinbase Advanced Trade",
    "bybit": "Bybit",
    "upbit_krw": "Upbit (KRW market)",
    "okx": "OKX",
}


def log_exchange(name: str, message: str, level: int = logging.INFO) -> None:
    label = EXCHANGE_LABELS.get(name, name)
    logger.log(level, "[%s] %s", label, message)


def write_json_file(path: Path, payload: object, indent: int) -> None:
    """Write payload as JSON to path, creating directories as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(payload, ensure_ascii=False, indent=indent)
    path.write_text(serialized, encoding="utf-8")
    logger.info("Wrote %s (%d bytes)", path, path.stat().st_size)


def emit_json(path: Path, payload: object, indent: int, label: str) -> None:
    """Write payload either to stdout (when path == '-') or to disk."""
    if str(path) == "-":
        print(json.dumps(payload, ensure_ascii=False, indent=indent))
        logger.info("Wrote %s to stdout", label)
    else:
        write_json_file(path, payload, indent)


def compute_common_coins(listings: Dict[str, List[str]]) -> List[str]:
    """Return sorted list of coins present on every exchange."""
    sets: List[Set[str]] = []
    for name, coins in listings.items():
        asset_set = {coin.upper() for coin in coins}
        if not asset_set:
            logger.warning(
                "[%s] No assets found; common coin set will be empty", EXCHANGE_LABELS.get(name, name)
            )
            return []
        sets.append(asset_set)
    if not sets:
        return []
    common = set.intersection(*sets)
    logger.info("Computed %d coins that are listed on all %d exchanges", len(common), len(sets))
    return sorted(common)


def gather_all() -> Dict[str, List[str]]:
    """Fetch assets for each exchange and return a combined mapping."""
    results: Dict[str, List[str]] = {}
    for name, fetcher in EXCHANGE_FETCHERS.items():
        log_exchange(name, "Starting fetch")
        start = time.time()
        assets = fetcher()
        duration = time.time() - start
        log_exchange(
            name,
            f"Completed fetch: {len(assets)} assets (took {duration:.1f}s)",
        )
        results[name] = assets
    return results


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch listed coins for Binance, Coinbase, Bybit, Upbit KRW, and OKX.",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help=f"Path to write per-exchange listings JSON (default: {DEFAULT_OUTPUT_PATH}). Use '-' for stdout.",
    )
    parser.add_argument(
        "--indent",
        type=int,
        default=2,
        help="Number of spaces to use when pretty-printing JSON.",
    )
    parser.add_argument(
        "--common-output",
        type=Path,
        default=DEFAULT_COMMON_OUTPUT_PATH,
        help=(
            f"Path to write coins listed on every exchange "
            f"(default: {DEFAULT_COMMON_OUTPUT_PATH})."
        ),
    )
    parser.add_argument(
        "--skip-common-output",
        action="store_true",
        help="Skip writing the all-exchange common coin list.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging verbosity (default: INFO).",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
    logger.debug("Initialized logger at level %s", args.log_level.upper())
    try:
        payload = gather_all()
    except FetchError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    emit_json(args.output, payload, args.indent, "per-exchange listings")

    if args.skip_common_output:
        logger.info("Skipping common coin output per --skip-common-output flag")
        return 0

    common_coins = compute_common_coins(payload)
    common_payload = {
        "count": len(common_coins),
        "exchanges": sorted(payload.keys()),
        "coins": common_coins,
    }
    emit_json(
        args.common_output,
        common_payload,
        args.indent,
        "coins listed on every exchange",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
