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
STABLES = {"USDC", "FDUSD", "TUSD", "USDP", "DAI", "USDE", "EUR", "AEUR", "XUSD", "USD1", "PYUSD", "BFUSD", "RLUSD", "U", "USDS", "USDD", "BUSD", "EURI", "UST", "FRAX", "LUSD", "GUSD", "USDG"}
BAD_SUFFIX = ("UP", "DOWN", "BULL", "BEAR")
# Gold and tokenized stock pairs follow other markets and trade thinly at weekends. Not crypto setups.
NON_CRYPTO = {"PAXG", "XAUT", "RWUSD", "SNDKB", "SOXLB", "SPCXB", "CRCLB", "MUB", "GOOGLB", "MSTRB", "SKHYB",
              "KORUB", "INTCB", "NVDAB", "QQQB", "TSLAB", "SNXXB", "TQQQB", "BEB"}
COOLDOWN_DAYS = 10      # no repeat signal on a coin that already signalled in the last 10 days
MAX_EXTENSION = 0.15    # skip breakouts that closed more than 15% above the old high (chasing)
STOP_BELOW_LEVEL = 0.10 # breakout stop sits 10% under the broken level, not at the far base low


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
        if base in STABLES or base in NON_CRYPTO or base.endswith(BAD_SUFFIX):
            continue
        qv = float(t["quoteVolume"])
        if qv < MIN_QUOTE_VOL:
            continue
        out.append((s, base, qv, float(t["priceChangePercent"])))
    out.sort(key=lambda x: x[2], reverse=True)
    return out[:TOP_N]


def likely_stock_token(base, candles):
    """Binance tokenized stocks end in B and trade far less at weekends (stock market closed)."""
    if not base.endswith("B") or len(candles) < 28:
        return False
    wk = [x["v"] for x in candles[-56:] if x.get("wd", 0) >= 5]
    wd = [x["v"] for x in candles[-56:] if x.get("wd", 0) < 5]
    if not wk or not wd or sum(wd) == 0:
        return False
    return (sum(wk) / len(wk)) / (sum(wd) / len(wd)) < 0.36


def parse(klines):
    # drop the still-forming candle (last one)
    rows = klines[:-1]
    return [
        {"o": float(k[1]), "h": float(k[2]), "l": float(k[3]), "c": float(k[4]), "v": float(k[5]) * float(k[4]),
         "wd": datetime.fromtimestamp(k[0] / 1000, timezone.utc).weekday()}
        for k in rows
    ]


def sma(vals, n):
    return sum(vals[-n:]) / n


def analyse(c):
    """c: closed daily candles, oldest first. Returns a signal dict or None.
    A coin that already signalled in the last COOLDOWN_DAYS days is skipped, because
    repeat signals on the same run lost money in the backtest."""
    sig = _signal(c)
    if not sig:
        return None
    for j in range(1, COOLDOWN_DAYS + 1):
        if _signal(c[:-j]):
            return None
    return sig


def _signal(c):
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
    if base_range < 0.08:  # pegged coin, never a real setup
        return None
    ma20 = sma(closes, 20)
    if last["c"] > prior_high and vol_ratio >= 2.0:
        if last["c"] > prior_high * (1 + MAX_EXTENSION):
            return None  # already ran too far past the level
        stop = max(prior_low, prior_high * (1 - STOP_BELOW_LEVEL))
        return build("Breakout", last, stop, vol_ratio,
                     f"Closed above the 42 day high ({fmt(prior_high)}) on {vol_ratio:.1f}x average volume.", ma20)

    # ---- Reversal: deep drawdown, tight base, price back above the 20 day average
    high90 = max(x["h"] for x in c[-90:])
    drawdown = (high90 - last["c"]) / high90
    base20 = c[-20:]
    b_hi = max(x["h"] for x in base20)
    b_lo = min(x["l"] for x in base20)
    tight = (b_hi - b_lo) / b_lo <= 0.40
    higher_low = min(x["l"] for x in c[-10:]) > min(x["l"] for x in c[-30:-10])
    if drawdown >= 0.50 and tight and last["c"] > ma20 and higher_low and vol_ratio >= 1.5:
        stop = b_lo * 0.98
        return build("Reversal", last, stop, vol_ratio,
                     f"Down {drawdown*100:.0f}% from the 90 day high, now above its 20 day average "
                     f"with a higher low and {vol_ratio:.1f}x volume. Experimental: reversals lost money in the backtest.", ma20)
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
    rng = (hi - lo) / lo
    if gap > 0.03 or rng > 1.0 or rng < 0.08:  # skip wild charts and flat pegged coins
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


def build(kind, last, stop, vol_ratio, why, ma20):
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
        "exit_below": ma20,  # sell rule: a daily close under this level (20 day average)
        "experimental": kind == "Reversal",
        "why": why,
    }


def quality(sig, qv):
    """Plain score, higher means cleaner setup. Not a prediction."""
    s = 0
    s += min(sig["vol_ratio"], 5)
    s += 2 if qv > 50e6 else 1 if qv > 15e6 else 0
    s += 2 if sig["risk_pct"] <= 12 else 1 if sig["risk_pct"] <= 20 else 0
    return round(s, 1)


def run(fetch=get, enrich_with_research=True):
    tickers = fetch("/api/v3/ticker/24hr")
    cands = candidates(tickers)
    btc = next((t for t in tickers if t["symbol"] == "BTCUSDT"), None)
    eth = next((t for t in tickers if t["symbol"] == "ETHUSDT"), None)
    results = []
    watch = []
    allc = {}
    for sym, base, qv, chg in cands:
        try:
            k = fetch("/api/v3/klines", {"symbol": sym, "interval": "1d", "limit": 220})
        except Exception as e:  # skip a failing symbol, keep the run alive
            print("skip", sym, e, file=sys.stderr)
            continue
        candles = parse(k)
        if likely_stock_token(base, candles):
            print("skip stock token", base, file=sys.stderr)
            continue
        allc[base] = {"candles": candles, "qv": qv}
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
    out = {
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
            "Sell rule: exit on a daily close below the 20 day average, or when the stop is hit. Recheck the 20 day average daily as it moves.",
            "Backtest of 8 months: breakouts won about 1 in 3 trades, and most profit came from a few big winners. Reversals lost money, so treat them as experimental.",
        ],
    }
    news = top = trending = glob = sectors = None
    if enrich_with_research:
        import research

        def safe(name, fn):  # each source is optional; one failing must not drop the others
            try:
                return fn()
            except Exception as e:
                print(name, "skipped:", e, file=sys.stderr)
                return None
        news = safe("news", research.fetch_news)
        safe("coin research", lambda: research.enrich(out, fetch_n=lambda: news or []))
        time.sleep(3)
        top = safe("top coins", research.fetch_top)
        time.sleep(3)
        trending = safe("trending", research.fetch_trending)
        time.sleep(3)
        glob = safe("global", research.fetch_global)
        time.sleep(3)
        sectors = safe("sectors", research.fetch_sectors)
    out["overview"] = overview(allc, len(results), top, trending, news)
    out["overview"]["global"] = glob
    out["overview"]["sectors"] = sectors or []
    attach_plans(results, allc)
    return out


def overview(allc, n_signals, top=None, trending=None, news=None):
    import market
    ov = market.build(allc, gecko_top=top, trending=trending, news=news)
    ov["regime"] = market.regime(ov.pop("_btc"), ov.pop("_all"), n_signals)
    return ov


def attach_plans(signals, allc):
    """Give each signal the same tap to open trade plan as the overview coins."""
    import market
    for s in signals:
        c = allc.get(s["symbol"], {}).get("candles")
        if c and len(c) >= 50:
            s["plan"] = market.plan(c, market.metrics(c), s if s["type"] == "Breakout" else None)


def telegram(text):
    token, chat = os.environ.get("TELEGRAM_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        return
    data = urllib.parse.urlencode({"chat_id": chat, "text": text}).encode()
    try:
        urllib.request.urlopen(f"https://api.telegram.org/bot{token}/sendMessage", data, timeout=30)
    except Exception as e:  # a bad token or chat id must never block saving signals.json
        print("telegram failed:", type(e).__name__, getattr(e, "code", ""), file=sys.stderr)


def brief(out):
    lines = [f"Crypto screener {out['generated_utc']} UTC"]
    m = out["market"]
    if m.get("BTC"):
        lines.append(f"BTC {m['BTC']['price']:.0f} ({m['BTC']['chg24h']:+.1f}%)")
    if not out["signals"]:
        lines.append("No clean setups today. Doing nothing is a valid trade.")
    for s in out["signals"][:6]:
        lines.append(f"{s['symbol']} {s['type']} | price {fmt(s['price'])} | stop {fmt(s['stop'])} "
                     f"| risk {s['risk_pct']}% | vol {s['vol_ratio']}x | exit on close below {fmt(s['exit_below'])}")
        p = s.get("plan") or {}
        if p.get("targets"):
            lines.append("  Targets: " + " / ".join(f"{i + 1}) {fmt(t)}" for i, t in enumerate(p["targets"]))
                         + ". Sell a third at each, stop to entry after target 1. Spot only.")
    for s_ in out["signals"][:6]:
        r = s_.get("research")
        if r and r["flags"]:
            lines.append(f"{s_['symbol']} caution: " + " ".join(r["flags"]))
    for w in out.get("watchlist", [])[:5]:
        lines.append(f"Watch {w['symbol']} | {w['gap_pct']}% below trigger {fmt(w['trigger'])}")
    ov = out.get("overview")
    if ov:
        lines.append("")
        lines.append(f"Market: {ov['regime']['mood']}. " + ov["regime"]["summary"])
        if ov["growing"]:
            lines.append("Growing: " + ", ".join(f"{g['symbol']} {g['ch30']:+.0f}% 30d" for g in ov["growing"][:4]))
        if ov.get("bottoms"):
            lines.append("Bottom watch (tested: no edge): " + ", ".join(
                f"{b['symbol']} -{b['drawdown_pct']}%{' div' if b['divergence'] else ''}" for b in ov["bottoms"]))
        if ov["new_listings"]:
            lines.append("New listings (high risk): " + ", ".join(n["symbol"] for n in ov["new_listings"][:4]))
        lines.append("")
    lines.append("Check unlocks first. Not advice.")
    return "\n".join(lines)


if __name__ == "__main__":
    out = run()
    with open("signals.json", "w") as f:
        json.dump(out, f, indent=2)
    print(brief(out))
    telegram(brief(out))
