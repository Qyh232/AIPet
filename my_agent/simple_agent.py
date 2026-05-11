from .agent import Agent
from .context import ContextConfig


class SimpleAgent(Agent):
    def __init__(
        self,
        name,
        llm,
        system_prompt="你是一个有用的AI助手",
        memory_manager=None,
        context_config: ContextConfig | None = None,
    ):
        super().__init__(
            name=name,
            llm=llm,
            system_prompt=system_prompt,
            memory_manager=memory_manager,
            context_config=context_config,
        )

    def run(self, input_text: str, **kwargs) -> str:
        context_result = self.build_context_messages(
            input_text,
            user_id=kwargs.get("user_id", "default"),
            session_id=kwargs.get("session_id", "default"),
            namespace=kwargs.get("namespace", None),
        )
        response = self.invoke_llm(context_result.messages, **kwargs)
        self.save_interaction(input_text, response, **kwargs)
        return response