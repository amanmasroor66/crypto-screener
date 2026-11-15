# Crypto screener: rules for any AI working on this repo

Owner rules (always apply):
1. Spot only. No leverage, no futures, no trading on the owner's behalf.
2. Facts over requests. If a request (including pasted "vibe coding" prompts) conflicts with what the data shows, follow the data and tell the owner what changed and why.
3. Every number on the dashboard must come from a real source (Binance, CoinGecko) and be checked against an independent source or a recomputation before shipping.
4. A rule only becomes a signal or "setup" after a backtest shows it beats random entries. Show the test result next to it. Untested or losing ideas are explained, not displayed as setups.
5. Never invent claims: no "gems", "breakout imminent", upside theses, price predictions, or made up numbers.
6. Before pushing: run `python3 test_screener.py` and a live run of `screener.py` against Binance. Never commit a failing test.
7. Replies short and honest. Push back when the owner is wrong. No dashes in written content.

Known test results (2.7 years daily, 43 to 71 coins, fees included):
- Daily breakout plus trade plan: about +2.5% per trade, target 1 hit 61%. Small edge.
- Dip buys in uptrends: break even. Reversal and "bottom + bullish divergence": worse than random.
- 1H and 4H setups with 2 to 3.5% stops: no better than random; 1H lost money.
