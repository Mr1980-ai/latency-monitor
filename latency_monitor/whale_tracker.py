"""
whale_tracker.py
=================

This module defines a utility to monitor Kalshi trade executions in
real time.  By watching the unfiltered trade channel, it can identify
"whale" activity—orders whose notional value exceeds a specified
threshold—and log these events to the console for discretionary
analysis.  The tracker does not place trades itself; it merely
observes and reports.

Example usage::

    from dotenv import load_dotenv
    from pykalshi import Kalshi
    import asyncio
    from whale_tracker import monitor_whales

    load_dotenv()
    kalshi_client = Kalshi(api_key_id=os.getenv("KALSHI_API_KEY_ID"),
                           private_key=os.getenv("KALSHI_PRIVATE_KEY"))
    asyncio.run(monitor_whales(kalshi_client, threshold=10_000))

Note that ``pykalshi`` must provide a ``subscribe_trades`` coroutine on
its client object that yields trade dictionaries containing at least
``price`` (in cents), ``count`` (number of contracts), ``ticker``
(market symbol) and ``side`` ("YES" or "NO").
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict


async def monitor_whales(kalshi_client: Any, threshold: float = 10_000.0) -> None:
    """Listen for large trades on Kalshi and log "whale" alerts.

    A whale alert is triggered when the notional value of a single trade
    exceeds ``threshold`` dollars.  The function iterates over an
    asynchronous generator provided by ``kalshi_client.subscribe_trades()``,
    calculates the value of each trade and prints a message if it is large.

    Parameters
    ----------
    kalshi_client : Any
        An authenticated ``pykalshi`` client instance with a
        ``subscribe_trades()`` coroutine.  Each yielded trade should be a
        dictionary containing at minimum: ``price`` (int, cents), ``count``
        (int), ``ticker`` (str) and ``side`` (str).
    threshold : float, optional
        Dollar value at which to trigger a whale alert.  Defaults to 10,000.
    """
    try:
        async for trade in kalshi_client.subscribe_trades():
            try:
                price_cents = float(trade.get("price", 0))
                count_fp = float(trade.get("count", 0))
                value = (price_cents / 100.0) * count_fp
                if value >= threshold:
                    ticker = trade.get("ticker")
                    side = trade.get("side")
                    print(
                        f"Whale Alert! ${value:,.2f} traded on {ticker} (side: {side})."
                    )
            except Exception as inner:
                print(f"Error processing trade message: {inner}. Message: {trade}")
    except Exception as outer:
        print(f"Error in whale monitor: {outer}")
