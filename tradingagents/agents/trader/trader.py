"""Trader: turns the Research Manager's investment plan into a concrete transaction proposal."""

from __future__ import annotations

import functools

from langchain_core.messages import AIMessage

from tradingagents.agents.schemas import TraderProposal, render_trader_proposal
from tradingagents.agents.utils.agent_utils import build_instrument_context
from tradingagents.agents.utils.structured import (
    bind_structured,
    invoke_structured_or_freetext,
)


def create_trader(llm):
    structured_llm = bind_structured(llm, TraderProposal, "Trader")

    def trader_node(state, name):
        company_name = state["instrument"]
        instrument_context = build_instrument_context(company_name)
        investment_plan = state["investment_plan"]

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a crypto trading agent. Crypto assets trade in fractional units — "
                    "you can buy 0.0023 BTC, 1.47 ETH, or 312.5 SOL. Always express position "
                    "sizing as a percentage of the total portfolio (e.g. '5% of portfolio'), "
                    "never as a share count. Suggest stop-loss levels as a percentage below entry "
                    "price. Base your recommendation on the analysts' reports and the research plan."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Based on a comprehensive analysis by a team of crypto analysts, here is an "
                    f"investment plan for {company_name}. {instrument_context} The plan incorporates "
                    f"technical market trends, on-chain data, tokenomics, derivatives signals, and "
                    f"social media sentiment.\n\nProposed Investment Plan: {investment_plan}\n\n"
                    f"Translate this plan into a concrete transaction proposal. Include: the action "
                    f"(Buy/Hold/Sell), your reasoning, an optional entry price, an optional stop-loss "
                    f"price, and position sizing expressed as % of portfolio."
                ),
            },
        ]

        trader_plan = invoke_structured_or_freetext(
            structured_llm,
            llm,
            messages,
            render_trader_proposal,
            "Trader",
        )

        return {
            "messages": [AIMessage(content=trader_plan)],
            "trader_investment_plan": trader_plan,
            "sender": name,
        }

    return functools.partial(trader_node, name="Trader")
