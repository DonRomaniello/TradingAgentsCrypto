

def create_aggressive_debator(llm):
    def aggressive_node(state) -> dict:
        risk_debate_state = state["risk_debate_state"]
        history = risk_debate_state.get("history", "")
        aggressive_history = risk_debate_state.get("aggressive_history", "")

        current_conservative_response = risk_debate_state.get("current_conservative_response", "")
        current_neutral_response = risk_debate_state.get("current_neutral_response", "")

        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        tokenomics_report = state["tokenomics_report"]

        trader_decision = state["trader_investment_plan"]

        prompt = f"""As the Aggressive Risk Analyst for a crypto trading desk, your role is to champion high-reward opportunities with conviction. Crypto assets routinely move 5–10× more than equities in a single session — that volatility is the opportunity, not the threat. When evaluating the trader's decision, focus on upside catalysts: momentum, network adoption, token supply dynamics, and sentiment inflection points.

You are comfortable recommending 2–5× leverage on liquid majors (BTC, ETH) when the setup is strong, and willing to size up on high-conviction alts where the risk/reward is asymmetric. You believe that excessive caution in crypto leads to chronic underperformance because the compounding gains of the bull phases dwarf the drawdowns for traders who manage entries well.

When crypto-specific risks come up — smart contract exploits, exchange insolvency, regulatory action, stablecoin depegs, validator slashing — acknowledge them briefly, then explain why proper position sizing and stop-losses already account for them, and why they shouldn't paralyze action. Here is the trader's decision:

{trader_decision}

Argue forcefully for the best-case path using evidence from the data below. Counter the conservative and neutral analysts point by point. Show where their caution leaves alpha on the table.

Market Research Report: {market_research_report}
Social Media Sentiment Report: {sentiment_report}
Latest World Affairs Report: {news_report}
Tokenomics Report: {tokenomics_report}
Current conversation history: {history}
Last argument from the conservative analyst: {current_conservative_response}
Last argument from the neutral analyst: {current_neutral_response}

If there are no responses from the other viewpoints yet, open with your strongest bull case. Speak directly and conversationally — no headers, no bullet lists, just persuasive debate."""

        response = llm.invoke(prompt)

        argument = f"Aggressive Analyst: {response.content}"

        new_risk_debate_state = {
            "history": history + "\n" + argument,
            "aggressive_history": aggressive_history + "\n" + argument,
            "conservative_history": risk_debate_state.get("conservative_history", ""),
            "neutral_history": risk_debate_state.get("neutral_history", ""),
            "latest_speaker": "Aggressive",
            "current_aggressive_response": argument,
            "current_conservative_response": risk_debate_state.get("current_conservative_response", ""),
            "current_neutral_response": risk_debate_state.get(
                "current_neutral_response", ""
            ),
            "count": risk_debate_state["count"] + 1,
        }

        return {"risk_debate_state": new_risk_debate_state}

    return aggressive_node
