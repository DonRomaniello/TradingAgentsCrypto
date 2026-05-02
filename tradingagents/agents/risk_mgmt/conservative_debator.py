

def create_conservative_debator(llm):
    def conservative_node(state) -> dict:
        risk_debate_state = state["risk_debate_state"]
        history = risk_debate_state.get("history", "")
        conservative_history = risk_debate_state.get("conservative_history", "")

        current_aggressive_response = risk_debate_state.get("current_aggressive_response", "")
        current_neutral_response = risk_debate_state.get("current_neutral_response", "")

        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        tokenomics_report = state["tokenomics_report"]

        trader_decision = state["trader_investment_plan"]

        prompt = f"""As the Conservative Risk Analyst for a crypto trading desk, your primary objective is to protect capital in an asset class that is 5–10× more volatile than equities and where catastrophic tail risks are real and recurring. Your mandate is spot-only exposure — no leverage — with strict position limits: no single altcoin position exceeds 2–5% of the portfolio, and the bulk of crypto exposure stays in BTC and ETH where liquidity and institutional custody options are most mature.

You take crypto-specific risks seriously in a way the aggressive analyst often glosses over:
- **Smart contract exploits**: protocols lose hundreds of millions in hours; TVL is not safety.
- **Exchange insolvency**: FTX-style collapses can freeze withdrawals overnight; always prefer self-custody.
- **Regulatory action**: a single adverse ruling can gap a token down 40% before anyone can react.
- **Stablecoin depegs**: yield earned in depeg-prone stables evaporates in seconds.
- **Validator slashing**: staking rewards come with slashing risk that's hard to quantify.
- **Funding rate extremes**: when funding is persistently above 0.1%/8h, the market is overleveraged and prone to violent unwinds.

You watch these signals constantly. When funding rates are extreme, when on-chain leverage is elevated, or when social sentiment is euphoric, you argue for reducing exposure rather than pressing it. Here is the trader's decision:

{trader_decision}

Counter the aggressive and neutral analysts by grounding your argument in the downside scenarios they underweight. Use the data below to build a case for preserving capital.

Market Research Report: {market_research_report}
Social Media Sentiment Report: {sentiment_report}
Latest World Affairs Report: {news_report}
Tokenomics Report: {tokenomics_report}
Current conversation history: {history}
Last argument from the aggressive analyst: {current_aggressive_response}
Last argument from the neutral analyst: {current_neutral_response}

If there are no responses yet, open with the strongest bear case or risk-reduction argument. Speak directly and conversationally — no headers, no bullet lists, just persuasive debate."""

        response = llm.invoke(prompt)

        argument = f"Conservative Analyst: {response.content}"

        new_risk_debate_state = {
            "history": history + "\n" + argument,
            "aggressive_history": risk_debate_state.get("aggressive_history", ""),
            "conservative_history": conservative_history + "\n" + argument,
            "neutral_history": risk_debate_state.get("neutral_history", ""),
            "latest_speaker": "Conservative",
            "current_aggressive_response": risk_debate_state.get(
                "current_aggressive_response", ""
            ),
            "current_conservative_response": argument,
            "current_neutral_response": risk_debate_state.get(
                "current_neutral_response", ""
            ),
            "count": risk_debate_state["count"] + 1,
        }

        return {"risk_debate_state": new_risk_debate_state}

    return conservative_node
