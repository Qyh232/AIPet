import os 
from dataclasses import dataclass
from dotenv import load_dotenv
from typing import Literal

# Provider = Literal["oepnai_compatible", "ollama_native"]

@dataclass 
class LLMConfig:
    
    #=========== 连接参数 ===============
    base_url: str
    api_key: str
    model: str

    # ========== 生成成参数 ==============
    temperature: float = 0.7
    max_tokens: int = 1024
    top_p: float = 1.0

    @classmethod
    def from_env(cls):

        load_dotenv()

        base_url = os.getenv("LLM_BASE_URL")
        api_key = os.getenv("LLM_API_KEY")
        model = os.getenv("LLM_MODEL_ID")

        if not base_url:
            raise ValueError("缺少 LLM_BASE_URL")
        if not api_key:
            raise ValueError("缺少 LLM_API_KEY")
        if not model:
            raise ValueError("缺少 LLM_MODEL_ID")

        # 注意：环境变量读出来默认都是字符串
        # 所以 temperature / max_tokens / top_p 需要自己转类型
        temperature = float(os.getenv("LLM_TEMPERATURE", "0.7"))
        max_tokens = int(os.getenv("LLM_MAX_TOKENS", "1024"))
        top_p = float(os.getenv("LLM_TOP_P", "1.0"))

        return cls(
            base_url=base_url,
            api_key=api_key,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p,
        )