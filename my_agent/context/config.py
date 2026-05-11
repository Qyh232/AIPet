from dataclasses import dataclass


@dataclass
class ContextConfig:
    """
    上下文工程配置。

    注意：
    这里的 token 统计是粗估，不追求和模型 tokenizer 完全一致。
    目标是让上下文不会无限膨胀。
    """

    # 总上下文预算，给 DeepSeek / OpenAI 这类 chat 模型留一点余量
    max_context_tokens: int = 3500

    # 各模块预算
    system_token_budget: int = 500
    memory_token_budget: int = 800
    rag_token_budget: int = 1600
    history_token_budget: int = 700
    user_input_token_budget: int = 400

    # 历史消息最多保留几条，注意是一条 Message，不是一轮
    max_history_messages: int = 8

    # 是否启用模块
    enable_memory: bool = True
    enable_rag: bool = True
    enable_history: bool = True

    # RAG 检索配置
    rag_limit: int = 5
    rag_min_score: float | None = None
    rag_enable_mqe: bool | None = None
    rag_enable_hyde: bool | None = None

    # 调试
    debug: bool = False