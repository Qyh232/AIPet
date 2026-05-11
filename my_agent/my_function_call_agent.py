import json
import logging

from .agent import Agent

logger = logging.getLogger(__name__)


class MyFunctionCallAgent(Agent):
    def __init__(
        self,
        name: str,
        llm,
        system_prompt: str = "你是一个有用的AI助手",
        tool_choice: str = "auto",
        show_trace: bool = True,
        memory_manager=None,
        context_config=None,
    ):
        super().__init__(
            name=name,
            llm=llm,
            system_prompt=system_prompt,
            memory_manager=memory_manager,
            context_config=context_config,
        )

        self.tool_choice = tool_choice
        self.show_trace = show_trace

    def _build_tool_schemas(self):
        schemas = []

        for tool in self.tool_registry.get_all_tools():
            schemas.append(tool.get_schema())

        return schemas

    def run(self, input_text: str, **kwargs) -> str:
        # 如果没有注册任何工具，就退化成普通聊天
        if not self.tool_registry.tools:
            return self.run_basic_chat(input_text, **kwargs)

        # 第一步：准备消息（含记忆上下文）和工具 schema
        context_result = self.build_context_messages(
            input_text,
            user_id=kwargs.get("user_id", "default"),
            session_id=kwargs.get("session_id", "default"),
            namespace=kwargs.get("namespace", None),
        )
        messages = context_result.messages

        tools = self._build_tool_schemas()

        # 第二步：先问模型，要不要调用工具
        response = self.invoke_llm_with_tools(
            messages=messages,
            tools=tools,
            tool_choice=self.tool_choice,
            **kwargs,
        )

        assistant_message = response.choices[0].message

        if self.show_trace:
            logger.debug("=== 第一轮模型响应 ===")
            logger.debug("content: %s", assistant_message.content)
            if assistant_message.tool_calls:
                for tool_call in assistant_message.tool_calls:
                    logger.debug("tool_call.name: %s", tool_call.function.name)
                    logger.debug("tool_call.arguments: %s", tool_call.function.arguments)

        # 如果模型没有调用工具，直接返回普通回答
        if not assistant_message.tool_calls:
            final_response = assistant_message.content or ""
            self.save_interaction(input_text, final_response, **kwargs)
            return final_response

        # 第三步：执行工具
        messages.append(assistant_message.model_dump(exclude_none=True))

        for tool_call in assistant_message.tool_calls:
            tool_name = tool_call.function.name
            tool_arguments_str = tool_call.function.arguments

            try:
                tool_arguments = json.loads(tool_arguments_str)
            except Exception:
                tool_arguments = {}

            tool = self.tool_registry.get_tool(tool_name)

            if not tool:
                tool_result = f"工具不存在: {tool_name}"
            else:
                try:
                    tool_result = tool.execute(tool_arguments)
                except Exception as e:
                    tool_result = f"工具执行失败: {type(e).__name__}: {e}"

            if self.show_trace:
                logger.debug("[TOOL] %s -> %s", tool_name, tool_result)

            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": tool_result,
            })

        # 第四步：再问模型，生成最终自然语言答案
        final_response_obj = self.invoke_llm_with_tools(
            messages=messages,
            tools=tools,
            tool_choice="none",
            **kwargs,
        )

        final_message = final_response_obj.choices[0].message
        final_response = final_message.content or ""

        if self.show_trace:
            logger.debug("=== 第二轮模型响应（最终答案） ===\n%s", final_response)

        self.save_interaction(input_text, final_response, **kwargs)

        return final_response

    def run_stream(self, input_text: str, **kwargs):
        """流式版本：工具调用走非流式，最终文字回答走流式。返回 generator。"""
        context_result = self.build_context_messages(
            input_text,
            user_id=kwargs.get("user_id", "default"),
            session_id=kwargs.get("session_id", "default"),
            namespace=kwargs.get("namespace", None),
        )
        messages = context_result.messages
        tools = self._build_tool_schemas()

        # 第一轮：判断是否需要工具（非流式，工具调用需要完整 JSON）
        response = self.invoke_llm_with_tools(
            messages=messages, tools=tools, tool_choice=self.tool_choice, **kwargs,
        )
        assistant_message = response.choices[0].message

        if not assistant_message.tool_calls:
            # 无工具调用：重新用流式获取回答
            llm_kwargs = {k: kwargs[k] for k in ["temperature", "max_tokens", "top_p"] if k in kwargs}
            full_text = ""
            for chunk in self.llm.stream_invoke(messages, **llm_kwargs):
                full_text += chunk
                yield chunk
            self.save_interaction(input_text, full_text, **kwargs)
            return

        # 有工具调用：执行工具，再流式生成最终回答
        messages.append(assistant_message.model_dump(exclude_none=True))
        for tool_call in assistant_message.tool_calls:
            tool_name = tool_call.function.name
            try:
                import json as _json
                tool_arguments = _json.loads(tool_call.function.arguments)
            except Exception:
                tool_arguments = {}
            tool = self.tool_registry.get_tool(tool_name)
            tool_result = tool.execute(tool_arguments) if tool else f"工具不存在: {tool_name}"
            messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": tool_result})

        llm_kwargs = {k: kwargs[k] for k in ["temperature", "max_tokens", "top_p"] if k in kwargs}
        full_text = ""
        for chunk in self.llm.stream_invoke(messages, **llm_kwargs):
            full_text += chunk
            yield chunk
        self.save_interaction(input_text, full_text, **kwargs)