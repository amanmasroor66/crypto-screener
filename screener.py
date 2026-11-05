"""Daily spot crypto screener: breakout and reversal setups.

Uses Binance public market data only. No account or API keys needed.
Writes signals.json for the dashboard and optionally sends a Telegram brief.
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

BASE = "https://data-api.binance.vision"  # public data host, works from US servers
MIN_QUOTE_VOL = 5_000_000   # USDT traded in 24h
TOP_N = 150                 # candidates scanned, by volume
STABLES = {"USDC", "FDUSD", "TUSD", "USDP", "DAI", "USDE", "EUR", "AEUR", "XUSD", "USD1", "PYUSD", "BFUSD"}
BAD_SUFFIX = ("UP", "DOWN", "BULL", "BEAR")


def get(path, params=None):
    url = BASE + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "crypto-screener/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def candidates(tickers):
    out = []
    for t in tickers:
        s = t["symbol"]
        if not s.endswith("USDT"):
            continue
        base = s[:-4]
        if base in STABLES or base.endswith(BAD_SUFFIX):
            continue
        qv = float(t["quoteVolume"])
        if qv < MIN_QUOTE_VOL:
            continue
        out.append((s, base, qv, float(t["priceChangePercent"])))
    out.sort(key=lambda x: x[2], reverse=True)
    return out[:TOP_N]


def parse(klines):
    # drop the still-forming candle (last one)
    rows = klines[:-1]
    return [
        {"o": float(k[1]), "h": float(k[2]), "l": float(k[3]), "c": float(k[4]), "v": float(k[5]) * float(k[4])}
        for k in rows
    ]


def sma(vals, n):
    return sum(vals[-n:]) / n


def analyse(c):
    """c: list of closed daily candles, oldest first. Returns signal dict or None."""
    if len(c) < 60:
        return None
    last = c[-1]
    closes = [x["c"] for x in c]
    vol_avg20 = sum(x["v"] for x in c[-21:-1]) / 20
    if vol_avg20 <= 0:
        return None
    vol_ratio = last["v"] / vol_avg20

    # ---- Breakout: close above the highest high of the prior 42 days, on 2x volume
    prior = c[-43:-1]
    prior_high = max(x["h"] for x in prior)
    prior_low = min(x["l"] for x in prior)
    base_range = (prior_high - prior_low) / prior_low if prior_low else 9
    if last["c"] > prior_high and vol_ratio >= 2.0:
        stop = prior_low if (last["c"] - prior_low) / last["c"] < 0.30 else min(x["l"] for x in c[-10:]) * 0.98
        return build("Breakout", last, stop, vol_ratio,
                     f"Closed above the 42 day high ({fmt(prior_high)}) on {vol_ratio:.1f}x average volume.")

    # ---- Reversal: deep drawdown, tight base, price back above the 20 day average
    high90 = max(x["h"] for x in c[-90:])
    drawdown = (high90 - last["c"]) / high90
    base20 = c[-20:]
    b_hi = max(x["h"] for x in base20)
    b_lo = min(x["l"] for x in base20)
    tight = (b_hi - b_lo) / b_lo <= 0.40
    ma20 = sma(closes, 20)
    higher_low = min(x["l"] for x in c[-10:]) > min(x["l"] for x in c[-30:-10])
    if drawdown >= 0.50 and tight and last["c"] > ma20 and higher_low and vol_ratio >= 1.5:
        stop = b_lo * 0.98
        return build("Reversal", last, stop, vol_ratio,
                     f"Down {drawdown*100:.0f}% from the 90 day high, now above its 20 day average "
                     f"with a higher low and {vol_ratio:.1f}x volume.")
    return None


def near_miss(c):
    """Watchlist: closed within 3% under the 42 day high, not yet broken out."""
    if len(c) < 60:
        return None
    last = c[-1]
    prior = c[-43:-1]
    hi = max(x["h"] for x in prior)
    lo = min(x["l"] for x in prior)
    vol_avg20 = sum(x["v"] for x in c[-21:-1]) / 20
    if vol_avg20 <= 0 or last["c"] >= hi:
        return None
    gap = (hi - last["c"]) / hi
    if gap > 0.03 or (hi - lo) / lo > 1.0:  # skip wild, non breakout style charts
        return None
    return {
        "price": last["c"],
        "trigger": hi,
        "gap_pct": round(gap * 100, 1),
        "vol_ratio": round(last["v"] / vol_avg20, 1),
        "why": f"Needs a daily close above {fmt(hi)} on strong volume to trigger.",
    }


def fmt(x):
    return f"{x:.6g}"


def build(kind, last, stop, vol_ratio, why):
    price = last["c"]
    risk = (price - stop) / price
    if risk <= 0:
        return None
    return {
        "type": kind,
        "price": price,
        "stop": stop,
        "risk_pct": round(risk * 100, 1),
        # position size so that a stop out loses 1% of total capital
        "size_for_1pct_loss": round(min(1 / risk, 100), 1),
        "vol_ratio": round(vol_ratio, 1),
        "why": why,
    }


def quality(sig, qv):
    """Plain score, higher means cleaner setup. Not a prediction."""
    s = 0
    s += min(sig["vol_ratio"], 5)
    s += 2 if qv > 50e6 else 1 if qv > 15e6 else 0
    s += 2 if sig["risk_pct"] <= 12 else 1 if sig["risk_pct"] <= 20 else 0
    return round(s, 1)


def run(fetch=get):
    tickers = fetch("/api/v3/ticker/24hr")
    cands = candidates(tickers)
    btc = next((t for t in tickers if t["symbol"] == "BTCUSDT"), None)
    eth = next((t for t in tickers if t["symbol"] == "ETHUSDT"), None)
    results = []
    watch = []
    for sym, base, qv, chg in cands:
        try:
            k = fetch("/api/v3/klines", {"symbol": sym, "interval": "1d", "limit": 120})
        except Exception as e:  # skip a failing symbol, keep the run alive
            print("skip", sym, e, file=sys.stderr)
            continue
        candles = parse(k)
        sig = analyse(candles)
        if not sig:
            nm = near_miss(candles)
            if nm:
                nm.update({"symbol": base, "pair": sym, "qvol_musd": round(qv / 1e6, 1), "chg24h": round(chg, 1)})
                watch.append(nm)
        if sig:
            sig.update({"symbol": base, "pair": sym, "qvol_musd": round(qv / 1e6, 1), "chg24h": round(chg, 1)})
            sig["score"] = quality(sig, qv)
            results.append(sig)
        time.sleep(0.05)
    results.sort(key=lambda x: x["score"], reverse=True)
    watch.sort(key=lambda x: x["gap_pct"])
    return {
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
        "scanned": len(cands),
        "market": {
            "BTC": {"price": float(btc["lastPrice"]), "chg24h": float(btc["priceChangePercent"])} if btc else None,
            "ETH": {"price": float(eth["lastPrice"]), "chg24h": float(eth["priceChangePercent"])} if eth else None,
        },
        "signals": results,
        "watchlist": watch[:15],
        "notes": [
            "Filters only. Not advice and not a prediction.",
            "Check token unlock dates (tokenomist.ai) before any buy.",
            "Use the stop level. Size so a stop out costs about 1% of capital.",
        ],
    }


def telegram(text):
    token, chat = os.environ.get("TELEGRAM_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        return
    data = urllib.parse.urlencode({"chat_id": chat, "text": text}).encode()
    urllib.request.urlopen(f"https://api.telegram.org/bot{token}/sendMessage", data, timeout=30)


def brief(out):
    lines = [f"Crypto screener {out['generated_utc']} UTC"]
    m = out["market"]
    if m.get("BTC"):
        lines.append(f"BTC {m['BTC']['price']:.0f} ({m['BTC']['chg24h']:+.1f}%)")
    if not out["signals"]:
        lines.append("No clean setups today. Doing nothing is a valid trade.")
    for s in out["signals"][:6]:
        lines.append(f"{s['symbol']} {s['type']} | price {fmt(s['price'])} | stop {fmt(s['stop'])} "
                     f"| risk {s['risk_pct']}% | vol {s['vol_ratio']}x")
    for w in out.get("watchlist", [])[:5]:
        lines.append(f"Watch {w['symbol']} | {w['gap_pct']}% below trigger {fmt(w['trigger'])}")
    lines.append("Check unlocks first. Not advice.")
    return "\n".join(lines)


if __name__ == "__main__":
    out = run()
    with open("signals.json", "w") as f:
        json.dump(out, f, indent=2)
    print(brief(out))
    telegram(brief(out))
