"""Market overview: leaders, growing coins, new listings, trending coins, news,
and a plain English summary built from fixed rules.

Every sentence here comes from measured data (price trend, size, age, attention).
None of it is a prediction. The summary never says a coin will go up.
"""

NEW_DAYS = 90          # listed on Binance less than this many days ago
GROWING_MAX = 8
LEADERS_MAX = 10
NEWS_MAX = 6
TRENDING_MAX = 7


def sma(vals, n):
    return sum(vals[-n:]) / n if len(vals) >= n else None


def metrics(c):
    """c: closed daily candles, oldest first. Plain numbers used by every section."""
    closes = [x["c"] for x in c]
    last = closes[-1]
    out = {"price": last, "days_listed": len(c), "ma20": sma(closes, 20), "ma50": sma(closes, 50),
           "ma200": sma(closes, 200)}
    for d in (7, 30, 90):
        out[f"ch{d}"] = round((last / closes[-d - 1] - 1) * 100, 1) if len(closes) > d else None
    hi = max(x["h"] for x in c)
    out["from_high_pct"] = round((last / hi - 1) * 100, 1)
    out["since_listing_pct"] = round((last / c[0]["o"] - 1) * 100, 1) if c[0]["o"] else None
    out["above20"] = out["ma20"] is not None and last > out["ma20"]
    out["above50"] = out["ma50"] is not None and last > out["ma50"]
    out["uptrend"] = bool(out["above50"] and out["ma20"] and out["ma50"] and out["ma20"] > out["ma50"])
    out["downtrend"] = bool(out["ma50"] and last < out["ma50"] and out["ma20"] and out["ma20"] < out["ma50"])
    return out


def trend_word(m):
    if m["uptrend"]:
        return "Uptrend"
    if m["downtrend"]:
        return "Downtrend"
    return "Sideways"


def _pct(x):
    return f"{x:+.0f}%" if x is not None else "n/a"


def leader_note(sym, m):
    t = trend_word(m)
    if t == "Uptrend":
        s = f"{sym} is in an uptrend, above its 20 and 50 day averages, {_pct(m['ch30'])} over 30 days."
        s += " Large coins move slower and survive bad markets better than small ones."
        s += " Wait for a breakout signal or a dip toward the 20 day average rather than buying a spike."
    elif t == "Downtrend":
        s = f"{sym} is in a downtrend, below its 50 day average, {_pct(m['ch30'])} over 30 days."
        s += " Buying a falling leader is a bet that the drop is over, and the data does not show that yet."
        s += " Waiting for it to get back above the 50 day average is the safer rule."
    else:
        s = f"{sym} is moving sideways, {_pct(m['ch30'])} over 30 days, between its averages."
        s += " No clear direction, so there is no edge in buying now. A breakout signal would change that."
    return s


def growing_note(sym, m):
    s = f"{sym} is {_pct(m['ch30'])} over 30 days and {_pct(m['ch7'])} this week, above its 50 day average."
    if (m["ch30"] or 0) > 100:
        s += " That run is extreme. Coins that double in a month often give back a large part of it, so this is late to chase."
    elif (m["from_high_pct"] or 0) > -5:
        s += " It is near its high, so a breakout signal could come soon. Watch it rather than buy ahead of the signal."
    else:
        s += f" It sits {abs(m['from_high_pct']):.0f}% under its recent high. Strength can continue, but buying after a run means a deeper fall if it turns."
    return s


def new_note(sym, m, rank=None):
    if rank and rank <= 100:
        s = f"{sym} is new on Binance (about {m['days_listed']} days) but not a new coin: it is ranked {rank} by market cap and traded elsewhere before."
        s += f" It is {_pct(m['since_listing_pct'])} since its Binance listing and {abs(m['from_high_pct']):.0f}% below the high since then."
        s += " Too little Binance history for the screener's rules, so judge it like a leader once it has 90 days of data."
        return s
    s = f"{sym} was listed about {m['days_listed']} days ago and is {_pct(m['since_listing_pct'])} since its first day"
    s += f", {abs(m['from_high_pct']):.0f}% below its high." if m["from_high_pct"] < -1 else ", at its high."
    s += " New coins are the riskiest group: early investors, team tokens and airdrop holders often sell for months."
    s += " Too little history for the screener's rules. If you want exposure, use a very small amount you can lose."
    return s


def trending_note(item):
    rank = item.get("rank")
    s = "Many people are searching for it on CoinGecko right now. That is attention, not quality, and attention often peaks near a top."
    if rank and rank > 300:
        s += " It is a small coin (rank " + str(rank) + "), so moves both ways are violent."
    if not item.get("on_binance"):
        s += " Not in this screener's Binance list, so none of the checks here apply."
    return s


def regime(btc, coins, n_signals):
    """btc: metrics for BTC. coins: list of metrics. Returns facts and the summary paragraph."""
    have = [m for m in coins if m["ma50"] is not None]
    breadth = round(100 * sum(m["above50"] for m in have) / len(have)) if have else None
    up = btc and btc["ma50"] and btc["price"] > btc["ma50"]
    up200 = btc and btc["ma200"] and btc["price"] > btc["ma200"]
    facts = (f"BTC is {'above' if up else 'below'} its 50 day average and {'above' if up200 else 'below'} its 200 day average,"
             f" and {breadth}% of coins are above their 50 day average.")
    if up and up200 and (breadth or 0) >= 55:
        mood, text = "Uptrend", "The market is in an uptrend. " + facts
    elif (breadth is not None and breadth <= 25) or (not up and not up200 and (breadth or 100) <= 40):
        mood, text = "Downtrend", ("The market is weak. " + facts +
                                   " Most breakouts fail even in good markets, so in a weak market protecting cash matters more than finding a winner.")
    else:
        mood, text = "Mixed", "The market is mixed. " + facts + " No clear tide either way."
    if n_signals:
        text += (f" Today there {'is' if n_signals == 1 else 'are'} {n_signals} signal{'s' if n_signals != 1 else ''}."
                 " If you act, act only on those: read the caution flags, size so a stop out costs about 1% of your capital, and note the sell level.")
    else:
        text += (" There is no signal today, so by the rules there is nothing to buy."
                 " Use the lists below to learn the market and build your own watchlist, not as buy tips.")
    text += " Should you invest at all? Only money you can afford to lose completely, and only after a few weeks of paper trading these signals."
    return {"mood": mood, "breadth_pct": breadth, "btc_above_50d": bool(up), "btc_above_200d": bool(up200), "summary": text}


def build(cands, btc_sym="BTC", gecko_top=None, trending=None, news=None, skip=()):
    """cands: {symbol: {"candles": [...], "qv": quote volume}}. Returns the overview dict.
    gecko_top: CoinGecko markets rows ordered by market cap, or None.
    trending: CoinGecko trending rows, or None. news: list of headline dicts, or None."""
    ms = {s: metrics(v["candles"]) for s, v in cands.items() if len(v["candles"]) >= 8}
    old = {s: m for s, m in ms.items() if m["days_listed"] >= NEW_DAYS}

    # leaders: biggest by market cap that trade here; fall back to biggest by volume
    order = [r["symbol"].upper() for r in (gecko_top or [])]
    ranks = {r["symbol"].upper(): r.get("market_cap_rank") for r in (gecko_top or [])}
    if not order:
        order = sorted(cands, key=lambda s: cands[s]["qv"], reverse=True)
    leaders = []
    for s in order:
        if s in old and s not in skip and s not in [x["symbol"] for x in leaders]:
            m = old[s]
            leaders.append({"symbol": s, "trend": trend_word(m), "price": m["price"], "ch7": m["ch7"], "ch30": m["ch30"],
                            "from_high_pct": m["from_high_pct"], "note": leader_note(s, m)})
        if len(leaders) >= LEADERS_MAX:
            break
    lead_set = {x["symbol"] for x in leaders}

    growing = [(s, m) for s, m in old.items() if s not in lead_set and s not in skip and m["uptrend"] and (m["ch30"] or 0) > 0]
    growing.sort(key=lambda x: x[1]["ch30"], reverse=True)
    growing = [{"symbol": s, "trend": trend_word(m), "price": m["price"], "ch7": m["ch7"], "ch30": m["ch30"],
                "from_high_pct": m["from_high_pct"], "note": growing_note(s, m)} for s, m in growing[:GROWING_MAX]]

    new = [(s, m) for s, m in ms.items() if m["days_listed"] < NEW_DAYS and s not in skip]
    new.sort(key=lambda x: x[1]["days_listed"])
    new = [{"symbol": s, "days_listed": m["days_listed"], "price": m["price"], "since_listing_pct": m["since_listing_pct"],
            "from_high_pct": m["from_high_pct"], "rank": ranks.get(s),
            "note": new_note(s, m, ranks.get(s))} for s, m in new[:8]]

    trend_rows = []
    for t in (trending or [])[:TRENDING_MAX]:
        it = t.get("item", t)
        row = {"symbol": (it.get("symbol") or "").upper(), "name": it.get("name"), "rank": it.get("market_cap_rank"),
               "ch24": round((it.get("data") or {}).get("price_change_percentage_24h", {}).get("usd") or 0, 1)}
        row["on_binance"] = row["symbol"] in cands
        row["note"] = trending_note(row)
        trend_rows.append(row)

    return {"leaders": leaders, "growing": growing, "new_listings": new, "trending": trend_rows,
            "news": (news or [])[:NEWS_MAX], "_btc": ms.get(btc_sym), "_all": list(old.values())}
