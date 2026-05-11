# llm.py
# 这个版本和上一版不同的地方在于：
# 1）不再只管理“怎么连接模型”
# 2）还会保存“默认生成参数”
# 3）支持每次调用时临时覆盖参数

from openai import OpenAI
from .config import LLMConfig


class MyLLM:
    def __init__(self, config: LLMConfig | None = None):
        """
        初始化 LLM

        参数：
        - config: 模型配置对象
          如果不传，就自动从 .env 读取
        """
        self.config = config or LLMConfig.from_env()

        # 创建 OpenAI 兼容客户端
        self.client = OpenAI(
            api_key=self.config.api_key,
            base_url=self.config.base_url,
        )

    def invoke(
        self,
        messages,
        temperature=None,
        max_tokens=None,
        top_p=None,
    ) -> str:
        """
        普通调用

        这里支持两层配置：
        1）默认值：来自 self.config
        2）临时覆盖：来自函数参数
        """

        # 如果这次调用没传，就用默认配置
        temperature = self.config.temperature if temperature is None else temperature
        max_tokens = self.config.max_tokens if max_tokens is None else max_tokens
        top_p = self.config.top_p if top_p is None else top_p

        response = self.client.chat.completions.create(
            model=self.config.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p,
        )

        # 兜底：如果 content 为空，就返回空字符串
        return response.choices[0].message.content or ""
    
    def invoke_with_tools(
            self,
            messages,
            tools,
            tool_choice="auto",
            temperature=None,
            max_tokens=None,
            top_p=None
        ):
            """
            原生 function calling 调用
            
            这里不直接返回字符串，而是返回完整 response
            因为我们要读取 tool_calls
            """
            temperature = self.config.temperature if temperature is None else temperature
            max_tokens = self.config.max_tokens if max_tokens is None else max_tokens
            top_p = self.config.top_p if top_p is None else top_p

            response = self.client.chat.completions.create(
                model=self.config.model,
                messages=messages,
                tools=tools,
                tool_choice=tool_choice,
                temperature=temperature,
                max_tokens=max_tokens,
                top_p=top_p,
            )

            return response
        

    def stream_invoke(
        self,
        messages,
        temperature=None,
        max_tokens=None,
        top_p=None,
    ):
        """
        流式调用版本
        """

        temperature = self.config.temperature if temperature is None else temperature
        max_tokens = self.config.max_tokens if max_tokens is None else max_tokens
        top_p = self.config.top_p if top_p is None else top_p

        stream = self.client.chat.completions.create(
            model=self.config.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p,
            stream=True,
        )

        for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta