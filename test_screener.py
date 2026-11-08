"""Offline test with synthetic candles. Run: python3 test_screener.py"""
import random
import screener

random.seed(1)


def candle(c, v=1e6):
    return {"o": c, "h": c * 1.01, "l": c * 0.99, "c": c, "v": v}


def breakout_series():
    s = [candle(1.0 + random.uniform(-0.03, 0.03)) for _ in range(80)]
    s.append(candle(1.12, 6e6))  # breakout on big volume
    return s


def reversal_series():
    s = [candle(10 - i * 0.12) for i in range(70)]            # long fall to ~1.6
    s += [candle(1.6) for _ in range(10)]
    s += [candle(1.66 + i * 0.03, 1.2e6) for i in range(9)]
    s.append(candle(1.95, 4e6))  # higher lows, rising, volume
    return s


def flat_series():
    return [candle(1.0 + random.uniform(-0.02, 0.02)) for _ in range(100)]


b = screener.analyse(breakout_series())
r = screener.analyse(reversal_series())
f = screener.analyse(flat_series())
print("breakout:", b)
print("reversal:", r)
print("flat:", f)
assert b and b["type"] == "Breakout"
assert r and r["type"] == "Reversal"
assert f is None
def near_series():
    s = [candle(1.0 + random.uniform(-0.06, 0.06)) for _ in range(80)]
    hi = max(x["h"] for x in s[-42:])
    s.append(candle(hi * 0.985))
    return s
n = screener.near_miss(near_series())
print("near:", n)
assert n and n["gap_pct"] <= 3
assert screener.near_miss(flat_series()) is None  # pegged/flat coins are skipped
# over-extended breakout is skipped
ext = [candle(1.0 + random.uniform(-0.03, 0.03)) for _ in range(80)] + [candle(1.4, 6e6)]
assert screener.analyse(ext) is None
# cooldown: a second breakout candle right after the first is not a new signal
first = breakout_series()
assert screener.analyse(first)
assert screener.analyse(first + [candle(1.14, 6e6)]) is None
# signal carries a sell level and a stop that is not absurdly far
assert b["exit_below"] > 0 and b["stop"] < b["price"] and b["risk_pct"] <= 25
# gold, tokenized stocks and stablecoins are excluded
tk = [{"symbol": x + "USDT", "quoteVolume": "9e9", "priceChangePercent": "0"} for x in ("PAXG", "TSLAB", "RWUSD", "USDC", "BTC")]
assert [c[1] for c in screener.candidates(tk)] == ["BTC"]
# research layer, offline with fake data
import research
row = {"symbol": "ABC", "price": 1.0}
good = {"symbol": "abc", "name": "Alpha Beta Coin", "current_price": 1.02, "market_cap": 20e6, "market_cap_rank": 900,
        "circulating_supply": 30, "max_supply": 100, "fully_diluted_valuation": 70e6, "ath_change_percentage": -85,
        "price_change_percentage_30d_in_currency": 150}
news = research.match_news("ABC", "Alpha Beta Coin", [{"source": "x", "title": "ABC hit by exploit", "link": "u"},
                                                       {"source": "x", "title": "Nothing about it", "link": "u"},
                                                       {"source": "x", "title": "ABCD rallies", "link": "u"}])
assert len(news) == 1
ctx = research.context(row, good, news)
assert ctx["verdict"] == "Caution" and len(ctx["flags"]) == 4 and ctx["verified"]
wrong = dict(good, current_price=40.0)  # same ticker, different coin
assert research.context(row, wrong, [])["verified"] is False
assert research.context(row, None, [])["flags"]
clean = dict(good, market_cap=900e6, circulating_supply=95, price_change_percentage_30d_in_currency=5)
assert research.context(row, clean, [])["verdict"] == "No red flags found"
out = {"signals": [dict(row)], "watchlist": []}


def boom(*a):
    raise RuntimeError("down")


research.enrich(out, boom, boom)  # both sources down: must not crash
assert out["signals"][0]["research"]["verdict"] == "Caution"
# market overview, offline
import market


def series(start, step, n, v=1e6):
    return [{"o": start + i * step, "h": (start + i * step) * 1.01, "l": (start + i * step) * 0.99,
             "c": start + i * step, "v": v, "wd": i % 7} for i in range(n)]


cands = {"BTC": {"candles": series(50, 0.2, 220), "qv": 9e9}, "UPC": {"candles": series(1, 0.01, 150), "qv": 5e7},
         "DWN": {"candles": series(5, -0.02, 150), "qv": 6e7}, "NEWC": {"candles": series(2, -0.01, 30), "qv": 2e7}}
ov = market.build(cands, gecko_top=[{"symbol": "btc", "market_cap_rank": 1}, {"symbol": "dwn", "market_cap_rank": 9}],
                  trending=[{"item": {"symbol": "upc", "name": "Up", "market_cap_rank": 400, "data": {"price_change_percentage_24h": {"usd": 12}}}}])
assert [x["symbol"] for x in ov["leaders"]] == ["BTC", "DWN"]
assert ov["leaders"][0]["trend"] == "Uptrend" and ov["leaders"][1]["trend"] == "Downtrend"
assert [x["symbol"] for x in ov["growing"]] == ["UPC"]
assert [x["symbol"] for x in ov["new_listings"]] == ["NEWC"] and "riskiest" in ov["new_listings"][0]["note"]
assert ov["trending"][0]["on_binance"] and "attention" in ov["trending"][0]["note"]
rg = market.regime(ov["_btc"], ov["_all"], 0)
assert rg["mood"] in ("Uptrend", "Mixed", "Downtrend") and "nothing to buy" in rg["summary"]
weak = market.regime({"price": 1, "ma50": 2, "ma200": 3}, [{"ma50": 1, "above50": False}] * 9 + [{"ma50": 1, "above50": True}], 0)
assert weak["mood"] == "Downtrend"
texts = [rg["summary"], weak["summary"]] + [x["note"] for k in ("leaders", "growing", "new_listings", "trending") for x in ov[k]]
assert not any("\u2014" in x or "\u2013" in x for x in texts)  # house style: no dashes
stock = [dict(x, v=(1e5 if x["wd"] >= 5 else 1e6)) for x in series(1, 0, 60)]
assert screener.likely_stock_token("TSLAB", stock) and not screener.likely_stock_token("BTC", stock)
assert not screener.likely_stock_token("ARB", series(1, 0, 60))  # crypto trades the same at weekends
assert not screener.likely_stock_token("BNB", series(1, 0, 60))
print("OK")
