from abc import ABC, abstractmethod
from typing import Any

from .message import Message
from .llm import MyLLM
from .tools import ToolRegistry
from .memory.manager import MemoryManager
from .context import ContextBuilder, ContextConfig


class Agent(ABC):
    def __init__(
        self,
        name: str,
        llm: MyLLM,
        system_prompt: str = "你是一个有用的AI助手",
        memory_manager: MemoryManager | None = None,
        context_config: ContextConfig | None = None,
    ):
        self.name = name
        self.llm = llm
        self.system_prompt = system_prompt
        self._history: list[Message] = []
        self.tool_registry = ToolRegistry()
        self.memory_manager = memory_manager

        self.context_builder = ContextBuilder(context_config or ContextConfig())
        self.last_context_result = None

    @abstractmethod
    def run(self, input_text: str, **kwargs) -> str:
        pass

    def add_message(self, message: Message):
        self._history.append(message)

    def get_history(self):
        return self._history.copy()

    def clear_history(self):
        self._history.clear()

    def add_tool(self, tool):
        self.tool_registry.register_tool(tool)

    def build_context_messages(
        self,
        input_text: str,
        *,
        user_id: str = "default",
        session_id: str = "default",
        namespace: str | None = None,
    ):
        result = self.context_builder.build(
            input_text=input_text,
            system_prompt=self.system_prompt,
            memory_manager=self.memory_manager,
            history=self._history,
            user_id=user_id,
            session_id=session_id,
            namespace=namespace,
        )

        self.last_context_result = result
        return result

    def build_basic_messages(
        self,
        input_text: str,
        *,
        include_system: bool = True,
        include_history: bool = True,
    ) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = []

        if include_system and self.system_prompt:
            messages.append({
                "role": "system",
                "content": self.system_prompt,
            })

        if include_history:
            for msg in self._history:
                messages.append(msg.to_dict())

        messages.append({
            "role": "user",
            "content": input_text,
        })

        return messages

    def build_prompt_messages(
        self,
        prompt_text: str,
        *,
        include_system: bool = True,
        include_history: bool = False,
    ) -> list[dict[str, Any]]:
        return self.build_basic_messages(
            prompt_text,
            include_system=include_system,
            include_history=include_history,
        )

    def build_memory_text(self, query: str, **kwargs) -> str:
        """获取记忆上下文文本，供各模式注入 prompt。"""
        if not self.memory_manager:
            return ""
        try:
            return self.memory_manager.get_context(
                query,
                user_id=kwargs.get("user_id", "default"),
                session_id=kwargs.get("session_id", "default"),
            )
        except Exception:
            return ""

    def invoke_llm(
        self,
        messages: list[dict[str, Any]],
        **kwargs: Any,
    ) -> str:
        # 只保留 LLM 相关参数，不传入 user_id / session_id / namespace
        llm_kwargs = {k: kwargs[k] for k in ["temperature", "max_tokens", "top_p"] if k in kwargs}
        return self.llm.invoke(messages, **llm_kwargs)

    def invoke_llm_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        tool_choice: str = "auto",
        **kwargs: Any,
    ):
        # 只保留 LLM 相关参数，过滤掉业务参数
        _LLM_KEYS = {"temperature", "max_tokens", "top_p", "model", "stop"}
        llm_kwargs = {k: v for k, v in kwargs.items() if k in _LLM_KEYS}
        return self.llm.invoke_with_tools(
            messages=messages,
            tools=tools,
            tool_choice=tool_choice,
            **llm_kwargs,
        )

    def save_history(
        self,
        input_text: str,
        output_text: str,
    ) -> None:
        self.add_message(Message(role="user", content=input_text))
        self.add_message(Message(role="assistant", content=output_text))

    def save_memory(
        self,
        input_text: str,
        output_text: str,
        **kwargs: Any,
    ) -> None:
        if not self.memory_manager:
            return

        self.memory_manager.add_interaction(
            input_text,
            output_text,
            user_id=kwargs.get("user_id", "default"),
            session_id=kwargs.get("session_id", "default"),
        )

    def save_interaction(
        self,
        input_text: str,
        output_text: str,
        **kwargs: Any,
    ) -> None:
        self.save_history(input_text, output_text)
        self.save_memory(input_text, output_text, **kwargs)

    def run_basic_chat(self, input_text: str, **kwargs: Any) -> str:
        context_result = self.build_context_messages(
            input_text,
            user_id=kwargs.get("user_id", "default"),
            session_id=kwargs.get("session_id", "default"),
            namespace=kwargs.get("namespace", None),
        )

        response = self.invoke_llm(context_result.messages, **kwargs)
        self.save_interaction(input_text, response, **kwargs)

        return response