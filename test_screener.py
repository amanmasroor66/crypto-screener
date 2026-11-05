"""Offline test with synthetic candles. Run: python3 test_screener.py"""
import random
import screener

random.seed(1)


def candle(c, v=1e6):
    return {"o": c, "h": c * 1.01, "l": c * 0.99, "c": c, "v": v}


def breakout_series():
    s = [candle(1.0 + random.uniform(-0.03, 0.03)) for _ in range(80)]
    s.append(candle(1.25, 6e6))  # breakout on big volume
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
print("OK")
