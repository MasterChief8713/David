#!/usr/bin/env python3
"""
Polymarket Insider Trade Detector
==================================
Monitors geopolitical/conflict markets on Polymarket for suspicious trading patterns:
- Large bets (>$5K) on low-probability outcomes (<30%)
- Sudden volume spikes on quiet markets
- Clusters of wallets betting the same direction

Sends alerts to Telegram when flags trigger.

No API key needed — all Polymarket endpoints are public.
"""

import os
import sys
import json
import time
import logging
import hashlib
import requests
from datetime import datetime, timezone
from pathlib import Path

# ─── Config ───────────────────────────────────────────────────────────
GAMMA_API = "https://gamma-api.polymarket.com"
DATA_API = "https://data-api.polymarket.com"

# Detection thresholds
MIN_BET_SIZE_USD = 19900       # Flag bets above this (cost basis)
LOW_ODDS_THRESHOLD = 0.30     # Flag bets on outcomes below 30%
VOLUME_SPIKE_MULT = 5          # Flag if hourly volume > 5x baseline (DISABLED — too noisy)
VOLUME_SPIKE_ENABLED = False   # Set True to re-enable
WALLET_CLUSTER_MIN = 3         # Flag if 3+ wallets bet same direction in 1hr
MIN_CLUSTER_TOTAL_USD = 20000  # Total cluster volume must exceed this to alert
POLL_INTERVAL_SEC = 300        # Check every 5 minutes

# Geopolitical keywords for event discovery
GEO_KEYWORDS = [
    'war', 'military', 'strike', 'bomb', 'invade', 'invasion', 'attack',
    'conflict', 'ceasefire', 'nuclear', 'troops', 'iran', 'israel',
    'russia', 'ukraine', 'china', 'taiwan', 'korea', 'nato', 'clash',
    'capture', 'sanctions', 'assassination', 'coup', 'regime', 'annex',
    'hamas', 'hezbollah', 'putin', 'zelenskyy', 'netanyahu', 'erdogan',
    'xi jinping', 'kim jong', 'disarm', 'normalize'
]

STATE_FILE = Path(__file__).parent.parent / "data" / "polymarket_detector_state.json"

# Telegram
TG_BOT_TOKEN = None
TG_CHAT_ID = "7109293950"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
log = logging.getLogger("polymarket-detector")


# ─── State ─────────────────────────────────────────────────────────────
def load_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {"alerted": [], "baselines": {}, "last_run": None}


def save_state(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    state["alerted"] = state["alerted"][-500:]
    state["last_run"] = datetime.now(timezone.utc).isoformat()
    STATE_FILE.write_text(json.dumps(state, indent=2))


def make_hash(parts):
    key = "-".join(str(p) for p in parts)
    return hashlib.md5(key.encode()).hexdigest()[:12]


# ─── API ───────────────────────────────────────────────────────────────
def get_geo_events():
    """Fetch active geopolitical events with their embedded markets."""
    geo_markets = []
    try:
        resp = requests.get(f"{GAMMA_API}/events", params={
            "limit": 100, "active": "true", "closed": "false"
        }, timeout=15)
        events = resp.json()

        for event in events:
            title = event.get("title", "").lower()
            tags = event.get("tags", [])
            tag_labels = []
            for t in (tags or []):
                if isinstance(t, dict):
                    tag_labels.append(t.get("label", "").lower())
                elif isinstance(t, str):
                    tag_labels.append(t.lower())

            is_geo = (
                any(kw in title for kw in GEO_KEYWORDS)
                or "geopolitics" in " ".join(tag_labels)
                or "world affairs" in " ".join(tag_labels)
                or "foreign policy" in " ".join(tag_labels)
            )

            if not is_geo:
                continue

            # Fetch full event with embedded markets
            event_id = event.get("id")
            try:
                eresp = requests.get(f"{GAMMA_API}/events/{event_id}", timeout=10)
                full_event = eresp.json()
                for m in full_event.get("markets", []):
                    if m.get("closed"):
                        continue
                    m["_event_title"] = event.get("title", "")
                    m["_event_id"] = event_id
                    geo_markets.append(m)
            except Exception as e:
                log.warning(f"Failed to fetch event {event_id}: {e}")

            time.sleep(0.1)  # Rate limit

        log.info(f"Tracking {len(geo_markets)} markets across geopolitical events")
        return geo_markets

    except Exception as e:
        log.error(f"Failed to fetch events: {e}")
        return []


def get_recent_trades(token_id, limit=200):
    """Get recent trades for a specific token."""
    try:
        resp = requests.get(f"{DATA_API}/trades", params={
            "asset": token_id, "limit": limit
        }, timeout=10)
        data = resp.json()
        return data if isinstance(data, list) else []
    except Exception as e:
        log.warning(f"Trade fetch failed: {e}")
        return []


# ─── Detection ─────────────────────────────────────────────────────────
def analyze_market(market, state):
    """Analyze one market for suspicious activity."""
    alerts = []
    question = market.get("question", "Unknown")
    event_title = market.get("_event_title", "")

    try:
        prices = json.loads(market.get("outcomePrices", "[]"))
        outcomes = json.loads(market.get("outcomes", "[]"))
        token_ids = json.loads(market.get("clobTokenIds", "[]"))
    except (json.JSONDecodeError, TypeError):
        return alerts

    if not prices or not token_ids:
        return alerts

    for i, (price_str, token_id) in enumerate(zip(prices, token_ids)):
        try:
            price = float(price_str)
        except (ValueError, TypeError):
            continue

        outcome = outcomes[i] if i < len(outcomes) else f"Outcome {i}"

        # Only watch low-probability outcomes
        if price > LOW_ODDS_THRESHOLD:
            continue

        trades = get_recent_trades(token_id)
        if not trades:
            continue

        now_ts = int(time.time())
        one_hour_ago = now_ts - 3600
        recent = [t for t in trades if t.get("timestamp", 0) > one_hour_ago]

        if not recent:
            continue

        # ─── FLAG 1: Large individual bets ───
        for t in recent:
            if t.get("side") != "BUY":
                continue
            size = float(t.get("size", 0))
            t_price = float(t.get("price", 0))
            cost = size * t_price
            th = make_hash([t.get("proxyWallet", ""), t.get("timestamp", ""), size, token_id])

            if cost >= MIN_BET_SIZE_USD and th not in state.get("alerted", []):
                alerts.append({
                    "type": "LARGE_BET",
                    "hash": th,
                    "market": question,
                    "event": event_title,
                    "outcome": outcome,
                    "odds": f"{price:.1%}",
                    "cost": f"${cost:,.0f}",
                    "shares": f"{size:,.0f}",
                    "price": f"{t_price:.1%}",
                    "wallet": t.get("proxyWallet", "")[:16] + "...",
                    "name": t.get("pseudonym", "Anonymous"),
                    "time": datetime.fromtimestamp(t.get("timestamp", 0), tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
                    "polymarket_url": f"https://polymarket.com/event/{market.get('_event_id', '')}"
                })

        # ─── FLAG 2: Volume spike ───
        slug = market.get("slug", "")
        baseline_key = f"{slug}_{i}"
        hourly_vol = sum(
            float(t.get("size", 0)) * float(t.get("price", 0))
            for t in recent if t.get("side") == "BUY"
        )

        baseline = state.get("baselines", {}).get(baseline_key, 0)
        if VOLUME_SPIKE_ENABLED and baseline > 100 and hourly_vol > baseline * VOLUME_SPIKE_MULT and hourly_vol > 2000:
            sh = make_hash(["spike", slug, i, now_ts // 3600])
            if sh not in state.get("alerted", []):
                alerts.append({
                    "type": "VOLUME_SPIKE",
                    "hash": sh,
                    "market": question,
                    "event": event_title,
                    "outcome": outcome,
                    "odds": f"{price:.1%}",
                    "hourly_vol": f"${hourly_vol:,.0f}",
                    "baseline": f"${baseline:,.0f}",
                    "mult": f"{hourly_vol/baseline:.1f}x",
                    "trades": len(recent),
                    "polymarket_url": f"https://polymarket.com/event/{market.get('_event_id', '')}"
                })

        # Update baseline (exponential moving average)
        state.setdefault("baselines", {})[baseline_key] = (
            hourly_vol if baseline == 0
            else (baseline * 0.9) + (hourly_vol * 0.1)
        )

        # ─── FLAG 3: Wallet cluster ───
        wallets = {}
        for t in recent:
            if t.get("side") != "BUY":
                continue
            w = t.get("proxyWallet", "")
            if not w:
                continue
            if w not in wallets:
                wallets[w] = {"total": 0, "count": 0, "name": t.get("pseudonym", "")}
            wallets[w]["total"] += float(t.get("size", 0)) * float(t.get("price", 0))
            wallets[w]["count"] += 1

        big_wallets = {w: d for w, d in wallets.items() if d["total"] > 1000}
        total_cluster_vol = sum(d["total"] for d in big_wallets.values())
        if total_cluster_vol < MIN_CLUSTER_TOTAL_USD:
            big_wallets = {}  # Not enough total volume to trigger
        if len(big_wallets) >= WALLET_CLUSTER_MIN:
            ch = make_hash(["cluster", slug, i, now_ts // 3600])
            if ch not in state.get("alerted", []):
                total = sum(d["total"] for d in big_wallets.values())
                alerts.append({
                    "type": "WALLET_CLUSTER",
                    "hash": ch,
                    "market": question,
                    "event": event_title,
                    "outcome": outcome,
                    "odds": f"{price:.1%}",
                    "wallet_count": len(big_wallets),
                    "total_vol": f"${total:,.0f}",
                    "top_wallets": [
                        f"{w[:12]}... ${d['total']:,.0f} ({d['name']})"
                        for w, d in sorted(big_wallets.items(), key=lambda x: x[1]["total"], reverse=True)[:5]
                    ],
                    "polymarket_url": f"https://polymarket.com/event/{market.get('_event_id', '')}"
                })

    return alerts


# ─── Telegram ──────────────────────────────────────────────────────────
def send_alert(alert):
    """Send alert via Telegram or print to stdout."""
    emoji = {"LARGE_BET": "🚨", "VOLUME_SPIKE": "📈", "WALLET_CLUSTER": "🕸️"}.get(alert["type"], "⚠️")

    if alert["type"] == "LARGE_BET":
        msg = (
            f"{emoji} *POLYMARKET: LARGE BET DETECTED*\n\n"
            f"*Market:* {alert['market']}\n"
            f"*Outcome:* {alert['outcome']} (currently {alert['odds']})\n"
            f"*Bet:* {alert['cost']} ({alert['shares']} shares @ {alert['price']})\n"
            f"*Trader:* {alert['name']} ({alert['wallet']})\n"
            f"*Time:* {alert['time']}\n\n"
            f"[View on Polymarket]({alert.get('polymarket_url', '')})\n\n"
            f"_Large bet on low-probability outcome — possible insider signal_"
        )
    elif alert["type"] == "VOLUME_SPIKE":
        msg = (
            f"{emoji} *POLYMARKET: VOLUME SPIKE*\n\n"
            f"*Market:* {alert['market']}\n"
            f"*Outcome:* {alert['outcome']} (currently {alert['odds']})\n"
            f"*Volume:* {alert['hourly_vol']} ({alert['mult']} above baseline {alert['baseline']})\n"
            f"*Trades:* {alert['trades']} in last hour\n\n"
            f"[View on Polymarket]({alert.get('polymarket_url', '')})\n\n"
            f"_Unusual volume spike on low-probability outcome_"
        )
    elif alert["type"] == "WALLET_CLUSTER":
        wallets_str = "\n".join(f"  • {w}" for w in alert.get("top_wallets", []))
        msg = (
            f"{emoji} *POLYMARKET: WALLET CLUSTER*\n\n"
            f"*Market:* {alert['market']}\n"
            f"*Outcome:* {alert['outcome']} (currently {alert['odds']})\n"
            f"*Wallets:* {alert['wallet_count']} betting same direction\n"
            f"*Total:* {alert['total_vol']}\n\n"
            f"{wallets_str}\n\n"
            f"[View on Polymarket]({alert.get('polymarket_url', '')})\n\n"
            f"_Coordinated betting on low-probability outcome_"
        )
    else:
        msg = f"{emoji} Alert: {json.dumps(alert, indent=2)}"

    if not TG_BOT_TOKEN:
        log.info(f"ALERT (no TG token): {alert['type']} | {alert.get('market', '')[:50]}")
        print(msg)
        return

    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage",
            json={
                "chat_id": TG_CHAT_ID,
                "text": msg,
                "parse_mode": "Markdown",
                "disable_web_page_preview": True
            },
            timeout=10
        )
        if resp.ok:
            log.info(f"Alert sent: {alert['type']} | {alert.get('market', '')[:50]}")
        else:
            log.error(f"TG failed: {resp.text[:200]}")
    except Exception as e:
        log.error(f"TG error: {e}")


# ─── Main ──────────────────────────────────────────────────────────────
def filter_spray_bettors(alerts):
    """Remove wallets that bet across 3+ different markets — hedgers, not insiders.
    Real insider signal = concentrated conviction on ONE market."""
    # Count how many unique markets each wallet appears in
    wallet_markets = {}
    for a in alerts:
        if a["type"] != "LARGE_BET":
            continue
        wallet = a.get("wallet", "")
        market = a.get("market", "")
        if wallet not in wallet_markets:
            wallet_markets[wallet] = set()
        wallet_markets[wallet].add(market)

    # Identify spray bettors (3+ markets)
    spray_wallets = {w for w, markets in wallet_markets.items() if len(markets) >= 3}
    if spray_wallets:
        log.info(f"Filtering {len(spray_wallets)} spray bettors across 3+ markets")

    # Filter them out
    return [a for a in alerts if a.get("wallet", "") not in spray_wallets]


def run_scan(state):
    log.info("Scanning...")
    markets = get_geo_events()
    all_alerts = []

    for market in markets:
        alerts = analyze_market(market, state)
        all_alerts.extend(alerts)
        time.sleep(0.15)  # Rate limit

    # Filter out spray bettors (same wallet across many markets = hedging, not insider)
    all_alerts = filter_spray_bettors(all_alerts)

    for alert in all_alerts:
        send_alert(alert)
        state.setdefault("alerted", []).append(alert["hash"])

    save_state(state)
    log.info(f"Done: {len(all_alerts)} alerts from {len(markets)} markets")
    return all_alerts


def main():
    global TG_BOT_TOKEN

    # Try openclaw config for bot token (check accounts.default first)
    config_file = Path.home() / ".openclaw" / "openclaw.json"
    if config_file.exists():
        try:
            config = json.loads(config_file.read_text())
            tg = config.get("channels", {}).get("telegram", {})
            TG_BOT_TOKEN = tg.get("botToken")
            if not TG_BOT_TOKEN:
                accounts = tg.get("accounts", {})
                default_acc = accounts.get("default", {})
                TG_BOT_TOKEN = default_acc.get("botToken")
        except Exception:
            pass

    # Fallback: env file
    if not TG_BOT_TOKEN:
        env_file = Path.home() / ".openclaw" / "secrets" / "email.env"
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                if line.startswith("TG_BOT_TOKEN="):
                    TG_BOT_TOKEN = line.split("=", 1)[1].strip().strip('"\'')

    if not TG_BOT_TOKEN:
        TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN")

    if not TG_BOT_TOKEN:
        log.warning("No Telegram bot token — alerts will print to stdout")

    state = load_state()

    if "--once" in sys.argv:
        alerts = run_scan(state)
        print(f"\nScan complete: {len(alerts)} alerts")
        return

    log.info(f"Polymarket Insider Detector — polling every {POLL_INTERVAL_SEC}s")
    log.info(f"Thresholds: bet>${MIN_BET_SIZE_USD}, odds<{LOW_ODDS_THRESHOLD:.0%}, spike>{VOLUME_SPIKE_MULT}x, cluster>={WALLET_CLUSTER_MIN}")

    while True:
        try:
            run_scan(state)
        except KeyboardInterrupt:
            log.info("Stopped")
            break
        except Exception as e:
            log.error(f"Error: {e}")
        time.sleep(POLL_INTERVAL_SEC)


if __name__ == "__main__":
    main()
