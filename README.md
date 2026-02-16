# Latency Monitor for NFL Games and Kalshi Markets

This project provides a set of Python scripts to help you monitor live
NFL games via ESPN and compare the evolving win probabilities against
prices in the corresponding Kalshi prediction market.  The goal is to
identify potential discrepancies between your updated view of a game's
outcome and the market's current price.  **This project does not
execute trades automatically.**

## Overview

The system consists of three modules:

* `strategy.py` – Implements the ESPN poller and a simple heuristic to
  detect "spike" plays (turnovers, scores, etc.) in the play‑by‑play
  data.  It also provides functions to compute a Half‑Kelly stake and
  to derive reciprocal prices from Kalshi order book data.
* `whale_tracker.py` – Subscribes to Kalshi's trade channel and
  logs any single trade whose notional value exceeds a configurable
  threshold (default: $10,000).  Watching large trades can help
  surface "smart money" movements in relatively illiquid markets.
* `main.py` – Loads environment variables, constructs a `pykalshi`
  client and orchestrates the ESPN poller, order book monitor and
  whale tracker concurrently.

## Installation

1. **Clone or download** this repository and navigate into the
   `latency_monitor` directory.
2. **Create a virtual environment** (optional but recommended)::

       python -m venv .venv
       source .venv/bin/activate

3. **Install dependencies** from `requirements.txt`::

       pip install -r requirements.txt

4. **Create a `.env` file** based on `.env.example` and fill in your
   Kalshi API credentials, ESPN game ID, and market ticker.

## Usage

Once configured, run the monitor via the `main.py` entry point::

    python -m latency_monitor.main

The script will begin polling the ESPN summary endpoint at a sub‑second
interval and will maintain a persistent WebSocket connection to
Kalshi for order book and trade updates.  When the home team's win
probability changes significantly following a spike event, the script
calculates the Half‑Kelly fraction based on the current market price
and prints a recommendation.  Whale trades are logged with their
notional value.

### Example Output

```
Spike detected: Mac Jones pass intercepted by Sauce Gardner (Q3 12:17)
Win probability changed from 0.45 to 0.38 (Δ=0.07)
Recommended Half‑Kelly fraction at price 0.42: -0.03
Whale Alert! $12,345.67 traded on NFL23-NEP@NYJ (side: YES).
```

## Running as a Service on Hostinger

To keep the monitor running continuously on your Hostinger VPS, you can
set it up as a `systemd` service.  Assuming your project lives in
`/home/username/latency_monitor` and you are using a virtual
environment located at `/home/username/latency_monitor/.venv`, create
 a service definition file (e.g. `/etc/systemd/system/latency-monitor.service`) as root with the following contents:

```
[Unit]
Description=NFL–Kalshi latency monitor
After=network.target

[Service]
Type=simple
WorkingDirectory=/home/username/latency_monitor
EnvironmentFile=/home/username/latency_monitor/.env
ExecStart=/home/username/latency_monitor/.venv/bin/python -m latency_monitor.main
Restart=always
RestartSec=5
User=username

[Install]
WantedBy=multi-user.target
```

Replace `username` with your VPS user account.  After saving the
file, reload systemd and enable the service::

    sudo systemctl daemon-reload
    sudo systemctl enable --now latency-monitor.service

The monitor will start automatically and restart on failure.  Check
logs using `sudo journalctl -u latency-monitor.service`.

## Important Notes

* **No auto‑trading** – This project intentionally stops short of
  submitting orders.  It prints recommendations and alerts to
  standard output only.  If you choose to trade on Kalshi, you must
  do so manually and at your own risk.
* **API rate limits** – Polling ESPN at very high frequency may
  trigger rate limiting.  The default poll interval of 0.5 seconds
  should balance timeliness with courtesy to ESPN's servers.  Adjust
  `poll_interval` in `strategy.monitor_game_and_market` if needed.
* **Heuristics** – The spike detection logic is intentionally simple
  and may miss some impactful plays or generate false positives.
  Consider refining the heuristics or incorporating more advanced
  models for better performance.
* **Security** – Keep your Kalshi private key secure.  Do not
  commit the `.env` file containing credentials to version control.

## License

This project is provided for educational purposes and carries no
warranty.  Use at your own risk.
