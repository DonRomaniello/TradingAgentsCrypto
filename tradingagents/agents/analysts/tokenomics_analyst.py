from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.agents.utils.agent_utils import build_instrument_context, get_language_instruction
from tradingagents.agents.utils.tokenomics_data_tools import get_tokenomics, get_protocol_metrics


def create_tokenomics_analyst(llm):
    def tokenomics_analyst_node(state):
        current_date = state["trade_date"]
        instrument_context = build_instrument_context(state["instrument"])

        tools = [get_tokenomics, get_protocol_metrics]

        system_message = (
            "You analyze token supply dynamics (inflation schedule, unlocks, FDV vs MCAP), "
            "protocol fundamentals (TVL, revenue, fees), and on-chain holder distribution. "
            "You do NOT analyze traditional financial statements — these don't exist for crypto. "
            "Key metrics to examine: circulating vs total vs max supply, FDV/MCAP ratio "
            "(high FDV vs MCAP = large future inflation risk), protocol TVL trends, "
            "revenue vs token incentives (sustainable vs mercenary liquidity). "
            "Use get_tokenomics for supply data and get_protocol_metrics for DeFi protocol TVL/revenue."
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
            "tokenomics_report": report,
        }

    return tokenomics_analyst_node
