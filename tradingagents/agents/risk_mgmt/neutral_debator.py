

def create_neutral_debator(llm):
    def neutral_node(state) -> dict:
        risk_debate_state = state["risk_debate_state"]
        history = risk_debate_state.get("history", "")
        neutral_history = risk_debate_state.get("neutral_history", "")

        current_aggressive_response = risk_debate_state.get("current_aggressive_response", "")
        current_conservative_response = risk_debate_state.get("current_conservative_response", "")

        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        tokenomics_report = state["tokenomics_report"]

        trader_decision = state["trader_investment_plan"]

        prompt = f"""As the Neutral Risk Analyst for a crypto trading desk, your role is to find the calibrated middle ground between aggressive opportunity-seeking and conservative capital preservation — recognising that both extremes carry their own risks in crypto.

You accept that crypto volatility (5–10× equities) is a feature of the asset class, not a reason to avoid it entirely, but you also refuse to pretend that leverage and overleveraged alts are free money. Your framework:
- **Position sizing by conviction and liquidity**: BTC/ETH up to 10–15% of portfolio at 1× spot; high-conviction liquid alts 3–8%; speculative micro-caps 1–2% max.
- **Selective leverage**: 1.5–2× on BTC/ETH only, never on alts, never when funding rate exceeds 0.05%/8h for multiple consecutive days.
- **Risk guardrails that matter in crypto**: smart contract exposure diversified across audited protocols; no single stablecoin position > 20% of stable allocation; exchange counterparty risk managed via multi-venue withdrawal.
- **Macro awareness**: regulatory calendars, Fed rate cycles, and Bitcoin halving cycles all shift the optimal position size over weeks/months.

You challenge the aggressive analyst when leverage is being justified by momentum alone, and you challenge the conservative analyst when excessive caution means missing validated breakouts with strong on-chain confirmation. Here is the trader's decision:

{trader_decision}

Find the realistic, evidence-supported middle path using the data below. Show why balance beats both extremes.

Market Research Report: {market_research_report}
Social Media Sentiment Report: {sentiment_report}
Latest World Affairs Report: {news_report}
Tokenomics Report: {tokenomics_report}
Current conversation history: {history}
Last argument from the aggressive analyst: {current_aggressive_response}
Last argument from the conservative analyst: {current_conservative_response}

If there are no responses yet, open with a balanced assessment. Speak directly and conversationally — no headers, no bullet lists, just persuasive debate."""

        response = llm.invoke(prompt)

        argument = f"Neutral Analyst: {response.content}"

        new_risk_debate_state = {
            "history": history + "\n" + argument,
            "aggressive_history": risk_debate_state.get("aggressive_history", ""),
            "conservative_history": risk_debate_state.get("conservative_history", ""),
            "neutral_history": neutral_history + "\n" + argument,
            "latest_speaker": "Neutral",
            "current_aggressive_response": risk_debate_state.get(
                "current_aggressive_response", ""
            ),
            "current_conservative_response": risk_debate_state.get("current_conservative_response", ""),
            "current_neutral_response": argument,
            "count": risk_debate_state["count"] + 1,
        }

        return {"risk_debate_state": new_risk_debate_state}

    return neutral_node
