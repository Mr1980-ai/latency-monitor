"""
main.py
=======

Entry point for the latency monitor application.  This script wires
together the data ingestion logic defined in ``strategy.py`` and the whale
monitor defined in ``whale_tracker.py``.  When executed, it loads
credentials from a `.env` file, creates an authenticated Kalshi client
using the ``pykalshi`` library and runs the ESPN poller, order book
listener and whale watcher concurrently.

The application does **not** place trades automatically.  It merely
identifies situations where there may be a discrepancy between your
estimated probability (derived from the ESPN play‑by‑play) and the
market price.  Those signals are printed to standard output.

Environment Variables
---------------------

The following variables must be present in a `.env` file in the project
root (you can rename or relocate this file but adjust loading accordingly):

``KALSHI_API_KEY_ID``
    Your Kalshi API key ID.

``KALSHI_PRIVATE_KEY``
    RSA private key corresponding to the API key, provided as a single
    PEM‑encoded string (including newlines escaped with ``\n`` if loaded from
    an environment file).

``GAME_ID``
    ESPN event identifier for the NFL game you wish to monitor.

``KALSHI_MARKET_TICKER``
    Kalshi market ticker symbol (e.g. ``NFL23-NEP@NYJ``) associated with
    the same game.

Example `.env`::

    KALSHI_API_KEY_ID=35a8bc6b-8bf3-4cd5-91aa-b397203f90ce
    KALSHI_PRIVATE_KEY="-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----"
    GAME_ID=401546382
    KALSHI_MARKET_TICKER=NFL23-NEP@NYJ

Running::

    python -m latency_monitor.main
"""

from __future__ import annotations

import asyncio
import os
from typing import Optional

from dotenv import load_dotenv

try:
    from pykalshi import Kalshi
except ImportError:
    # Provide a friendly error if pykalshi is not installed
    Kalshi = None  # type: ignore

from .strategy import monitor_game_and_market
from .whale_tracker import monitor_whales


async def run() -> None:
    """Main coroutine to bootstrap the latency monitor application."""
    # Load variables from .env file
    load_dotenv()
    api_key_id = os.getenv("KALSHI_API_KEY_ID")
    private_key = os.getenv("KALSHI_PRIVATE_KEY")
    game_id: Optional[str] = os.getenv("GAME_ID")
    ticker: Optional[str] = os.getenv("KALSHI_MARKET_TICKER")
    if not (api_key_id and private_key and game_id and ticker):
        missing = [
            name
            for name, value in [
                ("KALSHI_API_KEY_ID", api_key_id),
                ("KALSHI_PRIVATE_KEY", private_key),
                ("GAME_ID", game_id),
                ("KALSHI_MARKET_TICKER", ticker),
            ]
            if not value
        ]
        raise RuntimeError(
            f"Missing required environment variables: {', '.join(missing)}"
        )

    if Kalshi is None:
        raise RuntimeError(
            "The pykalshi package is not installed.  Please run `pip install pykalshi`"
        )
    # Instantiate the Kalshi client using API key and private key
    kalshi_client = Kalshi(api_key_id=api_key_id, private_key=private_key)

    # Run the ESPN poller/orderbook monitor and whale tracker concurrently
    await asyncio.gather(
        monitor_game_and_market(game_id=game_id, ticker=ticker, kalshi_client=kalshi_client),
        monitor_whales(kalshi_client=kalshi_client),
    )


def main() -> None:
    """Synchronous entry point that delegates to ``run()``."""
    asyncio.run(run())


if __name__ == "__main__":
    main()
