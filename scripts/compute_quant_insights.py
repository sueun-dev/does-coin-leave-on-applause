#!/usr/bin/env python3
"""Compute cross-exchange quant insights from stored daily histories."""

from __future__ import annotations

import argparse
import json
import math
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

UTC = timezone.utc
DATA_DIR = Path("data")
HIST_DIR = DATA_DIR / "daily_histories"
COMMON_COINS_PATH = DATA_DIR / "common_coins.json"
OUTPUT_DIR = DATA_DIR / "analytics"
OUTPUT_PATH = OUTPUT_DIR / "quant_insights.json"
PRIMARY_EXCHANGE_ORDER = ["binance", "coinbase", "okx", "bybit", "upbit"]


def load_common_coins(path: Path) -> List[str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return [coin.upper() for coin in data.get("coins", [])]


def load_coin_history(coin: str) -> Optional[dict]:
    path = HIST_DIR / f"{coin}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def compute_series_metrics(candles: List[dict]) -> Optional[dict]:
    if len(candles) < 2:
        return None
    closes = [float(entry["close"]) for entry in candles]
    first_close, last_close = closes[0], closes[-1]
    if first_close <= 0 or last_close <= 0:
        return None

    cum_return = last_close / first_close - 1
    log_returns = [
        math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes)) if closes[i - 1] > 0
    ]
    volatility = statistics.pstdev(log_returns) * math.sqrt(365) if log_returns else 0.0

    max_price = closes[0]
    max_drawdown = 0.0
    for price in closes:
        max_price = max(max_price, price)
        if max_price > 0:
            drawdown = price / max_price - 1
            max_drawdown = min(max_drawdown, drawdown)

    listing_date = candles[0]["timestamp_iso"]
    last_date = candles[-1]["timestamp_iso"]

    return {
        "listing_date": listing_date,
        "last_date": last_date,
        "days": len(candles),
        "cum_return": cum_return,
        "max_drawdown": max_drawdown,
        "volatility": volatility,
    }


def compute_cross_exchange_spread(exchanges: Dict[str, dict]) -> Tuple[Optional[float], Optional[float]]:
    per_timestamp: Dict[int, List[float]] = defaultdict(list)
    for exchange_data in exchanges.values():
        for candle in exchange_data.get("candles", []):
            ts = int(candle["timestamp_ms"])
            per_timestamp[ts].append(float(candle["close"]))

    spreads: List[float] = []
    absolute_spreads: List[float] = []
    for closes in per_timestamp.values():
        if len(closes) < 2:
            continue
        max_close = max(closes)
        min_close = min(closes)
        mid = (max_close + min_close) / 2 if (max_close + min_close) else 0
        if mid > 0:
            spreads.append((max_close - min_close) / mid)
        absolute_spreads.append(max_close - min_close)

    if not spreads:
        return None, None
    median_rel = statistics.median(spreads)
    median_abs = statistics.median(absolute_spreads)
    return median_rel, median_abs


def build_coin_metrics(
    coin: str,
    payload: dict,
    exchange_metrics: Dict[str, List[dict]],
) -> Optional[dict]:
    exchanges = payload.get("exchanges") or {}
    if not exchanges:
        return None

    primary_exchange = None
    for key in PRIMARY_EXCHANGE_ORDER:
        if key in exchanges:
            primary_exchange = key
            break
    if not primary_exchange:
        primary_exchange = next(iter(exchanges.keys()))

    primary_candles = exchanges.get(primary_exchange, {}).get("candles", [])
    series_metrics = compute_series_metrics(primary_candles)
    if not series_metrics:
        return None

    # Per-exchange metrics for global aggregation
    for name, data in exchanges.items():
        metrics = compute_series_metrics(data.get("candles", []))
        if metrics:
            exchange_metrics[name].append({"coin": coin, **metrics})

    median_rel_spread, median_abs_spread = compute_cross_exchange_spread(exchanges)

    return {
        "coin": coin,
        "primary_exchange": primary_exchange,
        "median_rel_spread": median_rel_spread,
        "median_abs_spread": median_abs_spread,
        **series_metrics,
    }


def summarize_exchange_metrics(metrics: Dict[str, List[dict]]) -> Dict[str, dict]:
    summary = {}
    for name, entries in metrics.items():
        if not entries:
            continue
        summary[name] = {
            "count": len(entries),
            "avg_cum_return": statistics.mean(e["cum_return"] for e in entries),
            "median_drawdown": statistics.median(e["max_drawdown"] for e in entries),
            "median_volatility": statistics.median(e["volatility"] for e in entries),
        }
    return summary


def build_distribution(data: Iterable[dict], key: str, limit: Optional[int] = None) -> List[dict]:
    items = sorted(data, key=lambda item: item.get(key, 0))
    if limit:
        items = items[:limit]
    return [{"coin": item["coin"], key: item.get(key, 0)} for item in items]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compute quant insights from daily histories.")
    parser.add_argument("--coins", type=Path, default=COMMON_COINS_PATH, help="Path to common_coins.json")
    parser.add_argument("--hist-dir", type=Path, default=HIST_DIR, help="Directory with per-coin histories")
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH, help="Output JSON path")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    coins = load_common_coins(args.coins)
    if not coins:
        print("No coins found; run scripts/fetch_listed_coins.py first.", flush=True)
        return 1

    exchange_metrics: Dict[str, List[dict]] = defaultdict(list)
    per_coin: Dict[str, dict] = {}

    for coin in coins:
        payload = load_coin_history(coin)
        if not payload:
            continue
        metrics = build_coin_metrics(coin, payload, exchange_metrics)
        if metrics:
            per_coin[coin] = metrics

    if not per_coin:
        print("No coin metrics generated; ensure daily histories exist.", flush=True)
        return 1

    coin_metric_list = list(per_coin.values())
    top_decliners = sorted(coin_metric_list, key=lambda item: item["cum_return"])[:5]
    top_gainers = sorted(coin_metric_list, key=lambda item: item["cum_return"], reverse=True)[:5]
    top_spreads = [
        item for item in sorted(
            (m for m in coin_metric_list if m.get("median_rel_spread") is not None),
            key=lambda itm: itm["median_rel_spread"],
            reverse=True,
        )[:10]
    ]

    summary = {
        "coins": len(per_coin),
        "median_cum_return": statistics.median(item["cum_return"] for item in coin_metric_list),
        "median_drawdown": statistics.median(item["max_drawdown"] for item in coin_metric_list),
        "median_volatility": statistics.median(item["volatility"] for item in coin_metric_list),
        "median_spread": statistics.median(
            item["median_rel_spread"] for item in coin_metric_list if item.get("median_rel_spread") is not None
        ),
    }

    payload = {
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "coins_processed": len(per_coin),
        "coin_metrics": per_coin,
        "summary": summary,
        "top_decliners": top_decliners,
        "top_gainers": top_gainers,
        "top_spreads": top_spreads,
        "exchange_summary": summarize_exchange_metrics(exchange_metrics),
        "return_distribution": build_distribution(coin_metric_list, "cum_return"),
        "spread_distribution": [
            {"coin": item["coin"], "median_rel_spread": item["median_rel_spread"]}
            for item in coin_metric_list
            if item.get("median_rel_spread") is not None
        ],
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {args.output} (coins={len(per_coin)})", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
