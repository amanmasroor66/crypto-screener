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
                            "from_high_pct": m["from_high_pct"], "note": leader_note(s, m),
                            "plan": plan(cands[s]["candles"], m)})
        if len(leaders) >= LEADERS_MAX:
            break
    lead_set = {x["symbol"] for x in leaders}

    growing = [(s, m) for s, m in old.items() if s not in lead_set and s not in skip and m["uptrend"] and (m["ch30"] or 0) > 0]
    growing.sort(key=lambda x: x[1]["ch30"], reverse=True)
    growing = [{"symbol": s, "trend": trend_word(m), "price": m["price"], "ch7": m["ch7"], "ch30": m["ch30"],
                "from_high_pct": m["from_high_pct"], "note": growing_note(s, m),
                "plan": plan(cands[s]["candles"], m)} for s, m in growing[:GROWING_MAX]]

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

    bots = bottoms(cands, skip)
    for b in bots:
        b["plan"] = plan(cands[b["symbol"]]["candles"], metrics(cands[b["symbol"]]["candles"]))
    return {"leaders": leaders, "growing": growing, "new_listings": new, "trending": trend_rows,
            "bottoms": bots, "bottoms_tested": BOTTOM_TESTED,
            "news": (news or [])[:NEWS_MAX], "_btc": ms.get(btc_sym), "_all": list(old.values())}


# ---------------------------------------------------------------- trade plan
def atr(c, n=14):
    tr = [max(x["h"] - x["l"], abs(x["h"] - p["c"]), abs(x["l"] - p["c"])) for p, x in zip(c[-n - 1:-1], c[-n:])]
    return sum(tr) / len(tr) if tr else None


def pivots(c, side, k=3, lookback=180):
    """Swing highs (side='h') or lows (side='l'): a candle that beats k candles on each side."""
    w = c[-lookback:]
    out = []
    for i in range(k, len(w) - k):
        v = w[i][side]
        nb = [w[j][side] for j in range(i - k, i + k + 1) if j != i]
        if (side == "h" and v > max(nb)) or (side == "l" and v < min(nb)):
            out.append(v)
    return out


def _merge(levels, tol=0.02):
    """Collapse levels closer than tol into one, keeping the first."""
    out = []
    for v in levels:
        if all(abs(v / o - 1) > tol for o in out):
            out.append(v)
    return out


def plan(c, m, sig=None):
    """Price levels for one coin, spot only. Levels are where price turned before; not predictions."""
    px = m["price"]
    a = atr(c) or px * 0.04
    res = _merge(sorted(v for v in pivots(c, "h") if v > px * 1.02))[:3]
    sup = _merge(sorted((v for v in pivots(c, "l") if v < px * 0.98), reverse=True))[:3]
    hi42 = max(x["h"] for x in c[-43:-1]) if len(c) > 43 else max(x["h"] for x in c)
    p = {"atr_pct": round(a / px * 100, 1), "resistance": res, "support": sup, "trigger": hi42,
         "ma20": m["ma20"], "ma50": m["ma50"], "ma200": m["ma200"]}

    def targets(entry, stop):
        r = entry - stop
        t = [v for v in res if v > entry * 1.03]
        for mult in (1.5, 2.5, 4, 5.5, 7, 9):  # fill with risk multiples when there is no overhead level
            if len(t) >= 3:
                break
            v = entry + mult * r
            if all(abs(v / x - 1) > 0.03 for x in t):
                t.append(v)
        return sorted(t)[:3]

    if sig:
        entry, stop = sig["price"], sig["stop"]
        p.update(status="Signal active", entry_lo=entry, entry_hi=entry * 1.02, stop=stop,
                 why="Breakout signal today. Entry is near the signal price; do not chase more than about 2% above it.",
                 tested=("Tested on the last 2.7 years of these coins: target 1 was reached 61% of the time and the stop was hit first 37% of the time."
                         " Following this plan, the average trade made about +2.5% after fees. A small edge, not a sure thing."))
    elif m["uptrend"] and m["ma20"]:
        lo = max(m["ma50"], m["ma20"] - a)
        hi = m["ma20"]
        stop = min(lo - a, (sup[0] if sup and sup[0] < lo else lo - a))
        inzone = lo <= px <= hi * 1.01
        p.update(status="In buy zone" if inzone else "Wait for a dip", entry_lo=lo, entry_hi=hi, stop=stop,
                 why=("Uptrend, and price has pulled back to its 20 day average. This is where trend buyers usually step in."
                      if inzone else "Uptrend, but price is stretched above its 20 day average. Buying the dip to the zone gives a closer stop than buying now."),
                 tested=("Tested on the last 2.7 years of these coins: dip buys like this won 60% of the time but broke even on average,"
                         " because the losses were bigger than the wins. Treat the zone as a better price, not an edge. Breakout signals tested better."))
        entry = (lo + hi) / 2
    else:
        cond = m["ma50"] if m["ma50"] else hi42
        p.update(status="No buy", entry_lo=None, entry_hi=None, stop=None,
                 why=(f"Downtrend. No buy zone until price closes back above the 50 day average ({cond:.6g}) or breaks the 42 day high ({hi42:.6g})."
                      if m["downtrend"] else f"No clear trend. A daily close above {hi42:.6g} (the 42 day high) on strong volume would make it a breakout signal."))
        return p
    if p["atr_pct"] >= 10:
        p["why"] += (f" Warning: this coin moves about {p['atr_pct']:.0f}% a day, so the stop is far away and the position must be very small."
                     " Many traders simply skip coins this wild.")
    p["targets"] = targets(entry, p["stop"])
    risk = (entry - p["stop"]) / entry
    p["risk_pct"] = round(risk * 100, 1)
    p["size_for_1pct_loss"] = round(min(1 / risk, 100), 1) if risk > 0 else None
    p["profit_plan"] = ("Sell about a third at each target. After target 1, move your stop to your entry price so the rest cannot turn into a loss."
                        " If price closes a day below the 20 day average before the targets, sell the rest: that exit beat fixed holding in the backtest.")
    p["cancel"] = f"Plan is wrong if price closes below {p['stop']:.6g}. Sell there, no exceptions."
    return p


# ---------------------------------------------------------------- bottoming candidates
def rsi(closes, n=14):
    """Wilder RSI for every candle (None until enough data)."""
    out = [None] * len(closes)
    if len(closes) <= n:
        return out
    gains = [max(closes[i] - closes[i - 1], 0) for i in range(1, len(closes))]
    losses = [max(closes[i - 1] - closes[i], 0) for i in range(1, len(closes))]
    ag, al = sum(gains[:n]) / n, sum(losses[:n]) / n
    for i in range(n, len(closes)):
        if i > n:
            ag = (ag * (n - 1) + gains[i - 1]) / n
            al = (al * (n - 1) + losses[i - 1]) / n
        out[i] = 100 if al == 0 else 100 - 100 / (1 + ag / al)
    return out


def divergence(c, k=3, window=60):
    """Bullish divergence: price made a lower low but RSI made a higher low, from oversold.
    Returns (found, rsi_first, rsi_second, days_since_second_low)."""
    closes = [x["c"] for x in c]
    r = rsi(closes)
    start = max(k, len(c) - window)
    lows = [i for i in range(start, len(c) - k)
            if c[i]["l"] < min(c[j]["l"] for j in range(i - k, i + k + 1) if j != i) and r[i] is not None]
    if len(lows) < 2:
        return False, None, None, None
    a, b = lows[-2], lows[-1]
    found = c[b]["l"] < c[a]["l"] and r[b] > r[a] + 2 and r[a] < 35 and closes[-1] > c[b]["l"]
    return found, round(r[a]), round(r[b]), len(c) - 1 - b


def bottom_score(c):
    """Measured bottoming picture for one coin, or None if it is not beaten down."""
    if len(c) < 120:
        return None
    px = c[-1]["c"]
    hi = max(x["h"] for x in c[-180:])
    dd = 1 - px / hi
    if dd < 0.5:
        return None
    base = c[-30:]
    blo, bhi = min(x["l"] for x in base), max(x["h"] for x in base)
    base_range = (bhi - blo) / blo
    div, r1, r2, ago = divergence(c)
    v5 = sum(x["v"] for x in c[-5:]) / 5
    v30 = sum(x["v"] for x in c[-35:-5]) / 30 or 1
    closes = [x["c"] for x in c]
    ma20 = sma(closes, 20)
    score = (3 if div else 0) + max(0, 2 - base_range * 4) + min(dd * 2, 2) + min(max(v5 / v30 - 1, 0), 1.5) + (1 if px > ma20 else 0)
    return {"drawdown_pct": round(dd * 100), "base_range_pct": round(base_range * 100), "divergence": div,
            "rsi_lows": [r1, r2] if div else None, "div_days_ago": ago if div else None,
            "vol_pickup": round(v5 / v30, 1), "above20": px > ma20, "base_low": blo, "base_high": bhi,
            "score": round(score, 2)}


BOTTOM_TESTED = ("Tested on 2.7 years of these coins, 30 days later: the classic pattern (bullish divergence plus a tight base)"
                 " averaged 5% down and rose only 32% of the time, worse than a random coin (up 44% of the time)."
                 " Buying after the break above the base was worse still. Catching bottoms has no edge in this data.")


def bottom_note(sym, b):
    s = f"{sym} is {b['drawdown_pct']}% below its 6 month high and has moved in a {b['base_range_pct']}% range for 30 days."
    if b["divergence"]:
        s += (f" Bullish divergence: price made a lower low but RSI made a higher low ({b['rsi_lows'][0]} then {b['rsi_lows'][1]}),"
              " which means selling pressure is weakening.")
    else:
        s += " No bullish divergence yet."
    if b["vol_pickup"] >= 1.5:
        s += f" Volume is picking up ({b['vol_pickup']}x its recent average)."
    s += (f" A bottom is only confirmed once price breaks above the base ({b['base_high']:.6g}) on a daily close."
          f" Below the base low ({b['base_low']:.6g}) the idea is wrong.")
    return s


def bottoms(cands, skip=(), n=5):
    rows = []
    for s, v in cands.items():
        if s in skip:
            continue
        b = bottom_score(v["candles"])
        if b:
            b["symbol"] = s
            b["price"] = v["candles"][-1]["c"]
            rows.append(b)
    rows.sort(key=lambda x: x["score"], reverse=True)
    for b in rows[:n]:
        b["note"] = bottom_note(b["symbol"], b)
        b["label"] = "Bottoming pattern" if b["divergence"] and b["base_range_pct"] <= 40 else (
            "Basing, no divergence" if b["base_range_pct"] <= 40 else "Still swinging, no base yet")
    return rows[:n]
