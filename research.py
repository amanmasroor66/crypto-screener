"""Research layer: adds checkable context to each signal.

Sources: CoinGecko (market cap, supply) and public crypto news RSS feeds.
No X or Grok: X blocks scripts and chatbot text is not evidence.
Everything here is best effort. A failure never stops the daily scan.
"""
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

GECKO = "https://api.coingecko.com/api/v3/coins/markets"
FEEDS = {"Cointelegraph": "https://cointelegraph.com/rss", "Decrypt": "https://decrypt.co/feed"}
RISK_WORDS = ("hack", "exploit", "stolen", "delist", "lawsuit", "sues", "sec charges", "investigation",
              "unlock", "rug", "depeg", "outage", "halt", "fraud")
MIN_MCAP = 50e6  # your own rule: market cap above 50M USD


def _read(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": "crypto-screener/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def _gecko(url):
    for wait in (0, 15, 30, 60):  # free tier is rate limited, so retry with a pause
        time.sleep(wait)
        try:
            return json.loads(_read(url))
        except urllib.error.HTTPError as e:
            if e.code != 429:
                raise
    raise RuntimeError("CoinGecko rate limit, gave up")


def fetch_gecko(symbols):
    q = urllib.parse.urlencode({"vs_currency": "usd", "symbols": ",".join(s.lower() for s in symbols),
                                "per_page": 250, "price_change_percentage": "30d"})
    return _gecko(GECKO + "?" + q)


def fetch_top(n=40):
    """Largest coins by market cap."""
    q = urllib.parse.urlencode({"vs_currency": "usd", "order": "market_cap_desc", "per_page": n})
    return _gecko(GECKO + "?" + q)


def fetch_global():
    """Whole market: total market cap, BTC and ETH dominance, TOTAL3 (everything except BTC and ETH)."""
    d = _gecko("https://api.coingecko.com/api/v3/global")["data"]
    tot = d["total_market_cap"]["usd"]
    btc, eth = d["market_cap_percentage"]["btc"], d["market_cap_percentage"]["eth"]
    return {"total_usd": tot, "btc_dom": round(btc, 1), "eth_dom": round(eth, 1),
            "total3_usd": tot * (100 - btc - eth) / 100, "chg24h": round(d.get("market_cap_change_percentage_24h_usd") or 0, 1)}


SECTOR_SKIP = ("ecosystem", "portfolio", "binance", "coinbase", "alleged", "ftx", "made in", "launchpad", "launchpool",
               "stablecoin", "wrapped", "bridged", "tokenized", "holdings", "index", "proof of", "smart contract", "layer 1",
               "exchange-based", "centralized exchange", "world liberty", "a16z", "galaxy", "pantera", "dwf", "multicoin",
               "paradigm", "delphi", "animoca", "polychain", "gmci", "yzi", "spartan", "blockchain capital", "framework",
               "coinlist", "kucoin", "okx", "bybit", "gate", "bitget", "mexc", "upbit", "robinhood", "us strategic", "presale")


def fetch_sectors(n=8, min_cap=1e9):
    """Narratives (AI, DePIN, Gaming, Memes...) ranked by their 24 hour market cap change."""
    rows = _gecko("https://api.coingecko.com/api/v3/coins/categories")
    out = []
    for r in rows:
        name = (r.get("name") or "").lower()
        if (r.get("market_cap") or 0) < min_cap or r.get("market_cap_change_24h") is None:
            continue
        if any(w in name for w in SECTOR_SKIP):
            continue
        out.append({"name": r["name"], "chg24h": round(r["market_cap_change_24h"], 1), "mcap_busd": round(r["market_cap"] / 1e9, 1),
                    "top": [i.replace("-", " ").title() for i in (r.get("top_3_coins_id") or [])][:3]})
    out.sort(key=lambda x: x["chg24h"], reverse=True)
    return out[:n]


def fetch_trending():
    """Coins most searched on CoinGecko in the last 24 hours."""
    return _gecko("https://api.coingecko.com/api/v3/search/trending").get("coins", [])


def fetch_news():
    items = []
    for src, url in FEEDS.items():
        try:
            root = ET.fromstring(_read(url))
        except Exception as e:
            print("news skip", src, e, file=sys.stderr)
            continue
        for it in root.iter("item"):
            items.append({"source": src, "title": (it.findtext("title") or "").strip(),
                          "link": (it.findtext("link") or "").strip()})
    return items


def match_news(symbol, name, items, limit=3):
    sym = re.compile(r"(?<![A-Za-z0-9])" + re.escape(symbol) + r"(?![A-Za-z0-9])")  # case sensitive on purpose
    nm = re.compile(r"\b" + re.escape(name) + r"\b", re.I) if name and len(name) > 3 else None
    out = []
    for n in items:
        if (len(symbol) >= 3 and sym.search(n["title"])) or (nm and nm.search(n["title"])):
            out.append(n)
    return out[:limit]


def context(row, coin, news):
    """row: signal or watch dict with Binance price. coin: CoinGecko row or None."""
    flags = []
    info = {"source": "CoinGecko + news RSS"}
    if not coin:
        flags.append("No market data found. Check the coin manually.")
        info["verified"] = False
    else:
        gp = coin.get("current_price") or 0
        info["verified"] = bool(gp) and abs(gp - row["price"]) / row["price"] < 0.10
        if not info["verified"]:
            flags.append("CoinGecko may be showing a different coin with this ticker. Check the coin manually.")
        else:
            mc = coin.get("market_cap") or 0
            circ, mx = coin.get("circulating_supply"), coin.get("max_supply") or coin.get("total_supply")
            fdv = coin.get("fully_diluted_valuation")
            info.update({"mcap_musd": round(mc / 1e6, 1), "rank": coin.get("market_cap_rank"),
                         "ath_drop_pct": round(abs(coin.get("ath_change_percentage") or 0), 0)})
            if mc and mc < MIN_MCAP:
                flags.append(f"Small cap (${mc/1e6:.0f}M). Hard to exit, so size down.")
            if circ and mx and mx > 0:
                pct = circ / mx * 100
                info["circulating_pct"] = round(pct, 0)
                if pct < 60:
                    flags.append(f"Only {pct:.0f}% of supply is circulating. More tokens are still to unlock. Check the unlock calendar.")
            elif fdv and mc and fdv / mc > 2:
                flags.append(f"Fully diluted value is {fdv/mc:.1f}x market cap. Large future supply.")
            if (coin.get("price_change_percentage_30d_in_currency") or 0) > 100:
                flags.append("Up over 100% in 30 days. Late entries often reverse.")
    risky = [n for n in news if any(w in n["title"].lower() for w in RISK_WORDS)]
    if risky:
        flags.append("Recent headline with a risk word. Read it before buying.")
    info["news"] = news
    info["flags"] = flags
    info["verdict"] = "Caution" if flags else "No red flags found"
    return info


def enrich(out, fetch_g=fetch_gecko, fetch_n=fetch_news):
    rows = out["signals"] + out["watchlist"]
    if not rows:
        return out
    try:
        coins = {c["symbol"].upper(): c for c in fetch_g(sorted({r["symbol"] for r in rows}))}
    except Exception as e:
        print("coingecko skip", e, file=sys.stderr)
        coins = {}
    try:
        items = fetch_n()
    except Exception as e:
        print("news skip", e, file=sys.stderr)
        items = []
    for r in rows:
        c = coins.get(r["symbol"].upper())
        r["research"] = context(r, c, match_news(r["symbol"], c.get("name") if c else "", items))
    return out
