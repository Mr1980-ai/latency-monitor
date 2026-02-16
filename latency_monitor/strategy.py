"""
strategy.py
==============

This module contains core logic for ingesting data from the ESPN NFL summary
endpoint and from Kalshi's WebSocket feed.  It exposes utilities for
identifying noteworthy in‑game events ("spikes") in the play‑by‑play data,
calculating shifts in win probability, and computing recommended position
sizes using the Half‑Kelly criterion.  Importantly, this module does **not**
execute trades on your behalf.  It only surfaces potential signals and
calculated bet fractions so that a human can make the final decision.

Usage example::

    import asyncio
    from dotenv import load_dotenv
    from pykalshi import Kalshi
    from strategy import monitor_game_and_market

    load_dotenv()
    kalshi_client = Kalshi(api_key_id=os.getenv("KALSHI_API_KEY_ID"),
                           private_key=os.getenv("KALSHI_PRIVATE_KEY"))
    asyncio.run(monitor_game_and_market("401546382", "NFL23-NEP@NYJ", kalshi_client))

The ``monitor_game_and_market`` coroutine runs an ESPN poller and listens
for order book updates concurrently, emitting signals to stdout when
meaningful discrepancies are detected.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

import aiohttp


@dataclass
class SpikeEvent:
    """Represents a play‑by‑play event that may materially change win probability.

    Attributes
    ----------
    description: str
        Human‑readable description of the play.
    quarter: Optional[int]
        Game quarter when the play occurred.
    clock: Optional[str]
        Clock time (e.g. "05:34") when the play occurred.
    raw: Dict[str, Any]
        The full event dictionary as returned by ESPN.
    """

    description: str
    quarter: Optional[int]
    clock: Optional[str]
    raw: Dict[str, Any]


async def fetch_espn_summary(session: aiohttp.ClientSession, game_id: str) -> Dict[str, Any]:
    """Fetch the NFL game summary from ESPN.

    Parameters
    ----------
    session : aiohttp.ClientSession
        An aiohttp session to reuse connections.
    game_id : str
        The ESPN "event" identifier for the game.

    Returns
    -------
    Dict[str, Any]
        Parsed JSON response from ESPN.
    """
    url = (
        f"https://site.web.api.espn.com/apis/site/v2/sports/football/nfl/summary?event={game_id}"
    )
    async with session.get(url) as resp:
        resp.raise_for_status()
        return await resp.json()


def detect_spikes(play_by_play: Iterable[Dict[str, Any]]) -> List[SpikeEvent]:
    """Scan the play‑by‑play array for events likely to move win probability.

    ESPN's play‑by‑play data is nested: drives contain a list of items
    representing individual plays.  This function applies a simple
    heuristic—looking for keywords indicating turnovers, scores or large
    momentum swings—to identify candidate spike events.

    Parameters
    ----------
    play_by_play : Iterable[Dict[str, Any]]
        The ``playByPlay`` array from the ESPN summary response.

    Returns
    -------
    List[SpikeEvent]
        A list of detected spike events with descriptive metadata.
    """
    spikes: List[SpikeEvent] = []
    keywords = [
        "interception",
        "fumble",
        "touchdown",
        "field goal",
        "safety",
        "blocked",
        "turnover",
        "sack",
    ]
    for drive in play_by_play:
        items = drive.get("items") or []
        for event in items:
            text: str = event.get("text", "").lower()
            if any(kw in text for kw in keywords):
                spikes.append(
                    SpikeEvent(
                        description=event.get("text", ""),
                        quarter=event.get("period", {}).get("number"),
                        clock=event.get("clock", {}).get("displayValue"),
                        raw=event,
                    )
                )
    return spikes


def compute_half_kelly_fraction(price: float, estimated_probability: float) -> float:
    """Calculate the Half‑Kelly fraction for a binary outcome.

    The Kelly criterion maximises long‑term capital growth.  Using the
    Half‑Kelly (multiplying the full Kelly stake by 0.5) reduces volatility
    while retaining roughly 71% of the expected return.  The formula

        f* = 0.5 * ((b * p - q) / b)

    applies to a bet that pays one unit for each unit staked (i.e. even odds).
    In prediction markets like Kalshi, contract prices are quoted as values
    between 0 and 1 representing the cost to win one dollar.  The variable
    ``b`` represents the odds in decimal form minus one::

        b = (1 / price) - 1

    Parameters
    ----------
    price : float
        Market price of the contract (0 < price < 1).  For example, a price
        of 0.4 means you pay 40 cents to win one dollar.
    estimated_probability : float
        Your updated subjective probability that the event will occur (0 ≤ p ≤ 1).

    Returns
    -------
    float
        Fraction of your bankroll to stake.  Returns zero if inputs are
        outside sensible ranges.
    """
    if price <= 0 or price >= 1 or estimated_probability <= 0 or estimated_probability >= 1:
        return 0.0
    b = (1.0 / price) - 1.0
    p = estimated_probability
    q = 1.0 - p
    return 0.5 * ((b * p - q) / b)


def reciprocal_pricing(no_bid_price: float) -> float:
    """Calculate the implied ask price for a "Yes" contract given the "No" bid price.

    On Kalshi, markets trade complementary contracts: a "Yes" pays out if the
    event occurs, while a "No" pays if it does not.  The sum of the bid price
    for one side and the ask price for the other ideally equals one (leaving
    aside fees).  If you observe the bid price for the "No" side, the
    corresponding ask for the "Yes" side can be approximated as::

        ask_yes = 1 - bid_no

    Parameters
    ----------
    no_bid_price : float
        Bid price for the "No" contract (0 ≤ price ≤ 1).

    Returns
    -------
    float
        Implied ask price for the "Yes" contract.
    """
    if no_bid_price < 0 or no_bid_price > 1:
        return 0.0
    return 1.0 - no_bid_price


async def monitor_game_and_market(
    game_id: str,
    ticker: str,
    kalshi_client: Any,
    win_prob_change_threshold: float = 0.05,
    poll_interval: float = 0.5,
) -> None:
    """Monitor an NFL game and a Kalshi market, printing arbitrage signals.

    This coroutine concurrently polls ESPN's game summary for play‑by‑play
    updates and listens to a Kalshi order book stream.  When the estimated
    probability of the game outcome shifts by more than ``win_prob_change_threshold``
    but the market price does not move accordingly, a potential arbitrage
    opportunity exists.  Rather than submitting an order, this function
    simply logs the opportunity and the Half‑Kelly fraction to stake.

    Parameters
    ----------
    game_id : str
        ESPN event identifier.
    ticker : str
        Kalshi market ticker (e.g. "NFL23-NEP@NYJ").
    kalshi_client : Any
        An authenticated client object from the ``pykalshi`` library.  It must
        implement a ``subscribe_orderbook`` coroutine yielding orderbook
        snapshots and a ``subscribe_trades`` coroutine for trade executions.
    win_prob_change_threshold : float, optional
        Minimum change in win probability (as a fraction) to trigger a signal.
    poll_interval : float, optional
        Seconds to wait between ESPN polls.  The ESPN endpoint usually updates
        once per second; sub‑second intervals are safe but more aggressive.
    """
    async with aiohttp.ClientSession() as session:
        previous_win_prob: Optional[float] = None
        current_market_price: Optional[float] = None

        async def espn_poller() -> None:
            nonlocal previous_win_prob
            while True:
                try:
                    summary = await fetch_espn_summary(session, game_id)
                    # The summary contains a top‑level "winProbability" array with
                    # probabilities for both teams.  We'll consider the home team
                    # probability.  If not available, skip.
                    wp = summary.get("winProbability")
                    home_prob: Optional[float] = None
                    if wp and isinstance(wp, list) and len(wp) > 0:
                        # Some responses structure winProbability differently; account for nested keys
                        prob = wp[0]
                        # Try various possible keys for home win percentage
                        for key in ["homeWinPercentage", "homeWinPercent"]:
                            val = prob.get(key)
                            if val is not None:
                                home_prob = float(val)
                                break
                    if home_prob is not None:
                        if previous_win_prob is not None:
                            change = abs(home_prob - previous_win_prob)
                            if change >= win_prob_change_threshold:
                                # Identify spikes and log them
                                spikes = detect_spikes(summary.get("plays", []))
                                for spike in spikes:
                                    print(
                                        f"Spike detected: {spike.description} (Q{spike.quarter} {spike.clock})"
                                    )
                                print(
                                    f"Win probability changed from {previous_win_prob:.3f} to {home_prob:.3f} (Δ={change:.3f})"
                                )
                                # Compute half‑Kelly fraction if market price known
                                if current_market_price is not None:
                                    fstar = compute_half_kelly_fraction(
                                        price=current_market_price,
                                        estimated_probability=home_prob,
                                    )
                                    print(
                                        f"Recommended Half‑Kelly fraction at price {current_market_price:.2f}: {fstar:.4f}"
                                    )
                        previous_win_prob = home_prob
                except Exception as e:
                    print(f"ESPN poller error: {e}")
                await asyncio.sleep(poll_interval)

        async def kalshi_orderbook_listener() -> None:
            nonlocal current_market_price
            try:
                async for orderbook in kalshi_client.subscribe_orderbook(ticker):
                    # Expect orderbook to contain best bid and ask for YES contracts in cents
                    best_bid = orderbook.get("yes_bid")
                    best_ask = orderbook.get("yes_ask")
                    if best_bid is not None and best_ask is not None:
                        mid_cents = (float(best_bid) + float(best_ask)) / 2.0
                        current_market_price = mid_cents / 100.0
            except Exception as e:
                print(f"Order book listener error: {e}")

        # Run both tasks concurrently
        await asyncio.gather(espn_poller(), kalshi_orderbook_listener())
