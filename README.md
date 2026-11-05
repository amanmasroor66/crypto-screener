# crypto-screener

Daily spot screener for breakout and reversal setups on Binance USDT pairs.
Uses public data only. No exchange account or API keys.

- `screener.py` scans and writes `signals.json`
- `index.html` is the dashboard (light theme)
- `.github/workflows/daily.yml` runs it every day at 08:00 Dubai time

Filters only. Not advice. Check token unlock dates before buying.

Optional Telegram alerts: add repo secrets `TELEGRAM_TOKEN` and `TELEGRAM_CHAT_ID`.
