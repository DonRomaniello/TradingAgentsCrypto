from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.agents.utils.agent_utils import build_instrument_context, get_language_instruction
from tradingagents.agents.utils.derivatives_data_tools import (
    get_funding_rate,
    get_open_interest,
    get_long_short_ratio,
    get_liquidations,
)


def create_derivatives_analyst(llm):
    def derivatives_analyst_node(state):
        current_date = state["trade_date"]
        instrument_context = build_instrument_context(state["instrument"])

        tools = [get_funding_rate, get_open_interest, get_long_short_ratio, get_liquidations]

        system_message = (
            "You analyze derivatives market structure: funding rates (positive = longs paying = crowded long), "
            "open interest trends, long/short imbalance, and recent liquidation cascades. "
            "Flag funding > 0.1% per 8h or < -0.05% per 8h as extreme positioning. "
            "OI rising with price = healthy trend confirming buyers in control; "
            "OI rising with price falling = bearish divergence (shorts piling in). "
            "Large liquidation spikes often precede or accompany sharp reversals. "
            "Use all four tools to build a complete picture of derivatives positioning."
            + " Make sure to append a Markdown table at the end of the report to organize key points, organized and easy to read."
            + get_language_instruction()
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a helpful AI assistant, collaborating with other assistants."
                    " Use the provided tools to progress towards answering the question."
                    " If you are unable to fully answer, that's OK; another assistant with different tools"
                    " will help where you left off. Execute what you can to make progress."
                    " If you or any other assistant has the FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** or deliverable,"
                    " prefix your response with FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** so the team knows to stop."
                    " You have access to the following tools: {tool_names}.\n{system_message}"
                    "For your reference, the current date is {current_date}. {instrument_context}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(tool_names=", ".join([t.name for t in tools]))
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(instrument_context=instrument_context)

        chain = prompt | llm.bind_tools(tools)
        result = chain.invoke(state["messages"])

        report = ""
        if len(result.tool_calls) == 0:
            report = result.content

        return {
            "messages": [result],
            "derivatives_report": report,
        }

    return derivatives_analyst_node
