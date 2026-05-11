from typing import Literal

from .llm import MyLLM
from .tools import ToolRegistry
from .simple_agent import SimpleAgent
from .my_function_call_agent import MyFunctionCallAgent
from .context import ContextConfig


AgentMode = Literal["simple", "function_call"]


def create_agent(
    *,
    mode: AgentMode,
    llm: MyLLM,
    name: str = "AI助手",
    system_prompt: str = "你是一个有用的AI助手",
    tools: list | None = None,
    tool_registry: ToolRegistry | None = None,
    memory_manager=None,
    context_config: ContextConfig | None = None,
    show_trace: bool = True,
    tool_choice: str = "auto",
):
    tools = tools or []

    if tool_registry is None:
        tool_registry = ToolRegistry()
        for tool in tools:
            tool_registry.register_tool(tool)

    if mode == "simple":
        agent = SimpleAgent(
            name=name,
            llm=llm,
            system_prompt=system_prompt,
            memory_manager=memory_manager,
            context_config=context_config,
        )
        for tool in tools:
            agent.add_tool(tool)
        return agent

    if mode == "function_call":
        agent = MyFunctionCallAgent(
            name=name,
            llm=llm,
            system_prompt=system_prompt,
            tool_choice=tool_choice,
            show_trace=show_trace,
            memory_manager=memory_manager,
            context_config=context_config,
        )
        for tool in tools:
            agent.add_tool(tool)
        return agent

    raise ValueError(f"未知 Agent mode: {mode}")
