from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

from dotenv import load_dotenv

load_dotenv()

config = DEFAULT_CONFIG.copy()
config["deep_think_llm"] = "gpt-5.4-mini"
config["quick_think_llm"] = "gpt-5.4-mini"
config["max_debate_rounds"] = 1

ta = TradingAgentsGraph(debug=True, config=config)

_, decision = ta.propagate("BTC/USDT", "2026-05-02")
print(decision)
