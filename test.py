import time
from tradingagents.dataflows.ccxt_market_data import get_ohlcv
from tradingagents.dataflows.symbols import parse_symbol
from tradingagents.dataflows.indicators import get_indicator_series
from datetime import datetime, timezone

print("Testing ccxt market data with BTC/USDT:")
start_time = time.time()
instrument = parse_symbol("BTC/USDT")
since = datetime(2026, 4, 1, tzinfo=timezone.utc)
until = datetime(2026, 5, 1, tzinfo=timezone.utc)
df = get_ohlcv(instrument, "1d", since, until)
end_time = time.time()

print(f"Execution time: {end_time - start_time:.2f} seconds")
print(f"Rows: {len(df)}")
print(df.head())

print("\nTesting RSI indicator:")
result = get_indicator_series("BTC/USDT", "rsi", "2026-05-02", 30)
print(result[:200])
