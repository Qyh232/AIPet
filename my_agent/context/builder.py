import re
from dataclasses import dataclass, field
from typing import Any

from .config import ContextConfig


@dataclass
class ContextBlock:
    """
    一个上下文块。

    例如：
    - system
    - memory
    - rag
    - history
    - user_input
    """

    name: str
    role: str
    content: str
    priority: int = 0
    token_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ContextBuildResult:
    messages: list[dict[str, str]]
    blocks: list[ContextBlock]
    total_tokens: int
    debug_report: str


class ContextBuilder:
    """
    上下文工程构建器。

    职责：
    1. 从 MemoryManager 获取记忆上下文
    2. 从 RAGPipeline 获取知识库上下文
    3. 选择最近历史消息
    4. 按预算裁剪上下文
    5. 生成最终 messages
    6. 输出 debug report
    """

    def __init__(self, config: ContextConfig | None = None):
        self.config = config or ContextConfig()

    # ------------------------------------------------------------------
    # 对外主入口
    # ------------------------------------------------------------------

    def build(
        self,
        *,
        input_text: str,
        system_prompt: str | None = None,
        memory_manager=None,
        history=None,
        user_id: str = "default",
        session_id: str = "default",
        namespace: str | None = None,
    ) -> ContextBuildResult:
        blocks: list[ContextBlock] = []

        # 1. system prompt
        if system_prompt:
            system_content = self._build_system_content(system_prompt)
            blocks.append(self._make_block(
                name="system",
                role="system",
                content=self._trim_to_budget(system_content, self.config.system_token_budget),
                priority=100,
            ))

        # 2. memory context
        if self.config.enable_memory and memory_manager:
            memory_block = self._build_memory_block(
                input_text=input_text,
                memory_manager=memory_manager,
                user_id=user_id,
                session_id=session_id,
            )
            if memory_block:
                blocks.append(memory_block)

        # 3. rag context
        if self.config.enable_rag and memory_manager and hasattr(memory_manager, "rag_pipeline"):
            rag_block = self._build_rag_block(
                input_text=input_text,
                memory_manager=memory_manager,
                user_id=user_id,
                session_id=session_id,
                namespace=namespace,
            )
            if rag_block:
                blocks.append(rag_block)

        # 4. history context
        if self.config.enable_history and history:
            history_blocks = self._build_history_blocks(history)
            blocks.extend(history_blocks)

        # 5. 当前用户输入
        user_content = self._trim_to_budget(input_text, self.config.user_input_token_budget, strategy="tail")
        blocks.append(self._make_block(
            name="user_input",
            role="user",
            content=user_content,
            priority=100,
        ))

        # 6. 总预算裁剪
        blocks = self._apply_total_budget(blocks)

        messages = [
            {
                "role": block.role,
                "content": block.content,
            }
            for block in blocks
            if block.content.strip()
        ]

        total_tokens = sum(block.token_count for block in blocks)

        return ContextBuildResult(
            messages=messages,
            blocks=blocks,
            total_tokens=total_tokens,
            debug_report=self._build_debug_report(blocks, total_tokens),
        )

    # ------------------------------------------------------------------
    # 各类上下文块构造
    # ------------------------------------------------------------------

    def _build_system_content(self, system_prompt: str) -> str:
        """
        系统提示词增强。

        这里加入上下文优先级规则，让模型知道不同来源怎么用。
        """
        return f"""{system_prompt}

【上下文使用规则】
1. 如果知识库资料与用户记忆冲突，优先相信当前知识库资料。
2. 如果用户最新输入与历史对话冲突，优先相信用户最新输入。
3. 如果知识库资料不足以回答，请明确说明“知识库中没有足够信息”，不要编造。
4. 用户记忆用于理解用户背景、偏好和历史，不等同于外部事实资料。
5. 回答时优先使用当前问题最相关的信息。""".strip()

    def _build_memory_block(
        self,
        *,
        input_text: str,
        memory_manager,
        user_id: str,
        session_id: str,
    ) -> ContextBlock | None:
        try:
            memory_context = memory_manager.get_context(
                input_text,
                user_id=user_id,
                session_id=session_id,
            )
        except TypeError:
            # 兼容旧版本 get_context(query)
            memory_context = memory_manager.get_context(input_text)
        except Exception as e:
            memory_context = f"[记忆检索失败: {type(e).__name__}: {e}]"

        memory_context = (memory_context or "").strip()
        if not memory_context:
            return None

        content = f"""【用户记忆上下文】
以下信息来自用户历史、偏好、事实或近期交互。
它可以帮助理解用户，但不一定是外部事实。

{memory_context}""".strip()

        content = self._trim_to_budget(content, self.config.memory_token_budget, strategy="middle")

        return self._make_block(
            name="memory",
            role="system",
            content=content,
            priority=80,
            metadata={"source": "memory_manager.get_context"},
        )

    def _build_rag_block(
        self,
        *,
        input_text: str,
        memory_manager,
        user_id: str,
        session_id: str,
        namespace: str | None,
    ) -> ContextBlock | None:
        try:
            rag_context = memory_manager.rag_pipeline.build_context(
                query=input_text,
                limit=self.config.rag_limit,
                min_score=self.config.rag_min_score,
                enable_mqe=self.config.rag_enable_mqe,
                enable_hyde=self.config.rag_enable_hyde,
                user_id=user_id,
                session_id=None,  # 知识库默认跨 session
                namespace=namespace,
            )
        except Exception as e:
            rag_context = f"[RAG 检索失败: {type(e).__name__}: {e}]"

        rag_context = (rag_context or "").strip()
        if not rag_context:
            return None

        content = f"""【知识库资料上下文】
以下内容来自 RAG 知识库检索结果。
回答涉及文档、资料、项目知识时，应优先依据这些资料。
如果资料不足，请说明不足，不要编造。

{rag_context}""".strip()

        content = self._trim_to_budget(content, self.config.rag_token_budget, strategy="middle")

        return self._make_block(
            name="rag",
            role="system",
            content=content,
            priority=90,
            metadata={"source": "rag_pipeline.build_context"},
        )

    def _build_history_blocks(self, history) -> list[ContextBlock]:
        """
        只保留最近若干条历史消息，并受 history_token_budget 限制。
        """
        recent = list(history)[-self.config.max_history_messages:]
        blocks: list[ContextBlock] = []

        used_tokens = 0

        for msg in recent:
            try:
                msg_dict = msg.to_dict()
            except AttributeError:
                msg_dict = dict(msg)

            role = msg_dict.get("role", "user")
            content = (msg_dict.get("content") or "").strip()

            if not content:
                continue

            token_count = self.estimate_tokens(content)

            if used_tokens + token_count > self.config.history_token_budget:
                remain = self.config.history_token_budget - used_tokens
                if remain <= 0:
                    break
                content = self._trim_to_budget(content, remain, strategy="tail")
                token_count = self.estimate_tokens(content)

            blocks.append(self._make_block(
                name="history",
                role=role,
                content=content,
                priority=60,
                metadata={"source": "agent_history"},
            ))

            used_tokens += token_count

        return blocks

    # ------------------------------------------------------------------
    # 预算控制
    # ------------------------------------------------------------------

    def _apply_total_budget(self, blocks: list[ContextBlock]) -> list[ContextBlock]:
        """
        总预算控制。

        保留策略：
        - system 和 user_input 必保
        - rag 优先级高于 memory
        - history 优先级最低
        """
        for block in blocks:
            block.token_count = self.estimate_tokens(block.content)

        total = sum(block.token_count for block in blocks)

        if total <= self.config.max_context_tokens:
            return blocks

        required_names = {"system", "user_input"}

        required = [b for b in blocks if b.name in required_names]
        optional = [b for b in blocks if b.name not in required_names]

        optional.sort(key=lambda b: b.priority, reverse=True)

        kept = list(required)
        used = sum(b.token_count for b in kept)

        for block in optional:
            if used + block.token_count <= self.config.max_context_tokens:
                kept.append(block)
                used += block.token_count
                continue

            remain = self.config.max_context_tokens - used
            if remain <= 80:
                continue

            trimmed = self._make_block(
                name=block.name,
                role=block.role,
                content=self._trim_to_budget(block.content, remain, strategy=self._trim_strategy_for_block(block.name)),
                priority=block.priority,
                metadata={**block.metadata, "trimmed_by_total_budget": True},
            )

            kept.append(trimmed)
            used += trimmed.token_count

        # 恢复合理顺序
        order = {
            "system": 0,
            "memory": 1,
            "rag": 2,
            "history": 3,
            "user_input": 4,
        }

        kept.sort(key=lambda b: order.get(b.name, 99))
        return kept

    def _trim_strategy_for_block(self, block_name: str) -> str:
        return {
            "system": "head",
            "user_input": "tail",
            "history": "tail",
            "memory": "middle",
            "rag": "middle",
        }.get(block_name, "head")

    def _trim_to_budget(self, text: str, max_tokens: int, strategy: str = "head") -> str:
        """
        按 token 预算截断。
        strategy: "head" 保留开头, "tail" 保留末尾, "middle" 保留首尾删中间。
        """
        text = text or ""
        token_count = self.estimate_tokens(text)

        if token_count <= max_tokens:
            return text

        if max_tokens <= 0:
            return ""

        ratio = max_tokens / max(token_count, 1)
        keep_chars = max(100, int(len(text) * ratio))

        if strategy == "tail":
            trimmed = text[-keep_chars:].lstrip()
            return "[上下文因预算限制已截断]\n\n" + trimmed
        elif strategy == "middle":
            half = keep_chars // 2
            trimmed = text[:half] + "\n\n[...中间内容已截断...]\n\n" + text[-half:]
            return trimmed
        else:  # "head"
            trimmed = text[:keep_chars].rstrip()
            return trimmed + "\n\n[上下文因预算限制已截断]"

    # ------------------------------------------------------------------
    # 工具方法
    # ------------------------------------------------------------------

    def _make_block(
        self,
        *,
        name: str,
        role: str,
        content: str,
        priority: int,
        metadata: dict[str, Any] | None = None,
    ) -> ContextBlock:
        content = content or ""
        return ContextBlock(
            name=name,
            role=role,
            content=content,
            priority=priority,
            token_count=self.estimate_tokens(content),
            metadata=metadata or {},
        )

    def estimate_tokens(self, text: str) -> int:
        """
        粗略估算 token：
        - CJK 字符约等于 1 token
        - 英文数字按词估算
        - 其他符号按 4 字符约 1 token
        """
        text = text or ""

        cjk = re.findall(r"[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]", text)
        non_cjk = re.sub(r"[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]", " ", text)
        words = re.findall(r"[A-Za-z0-9_]+", non_cjk)
        symbols = re.sub(r"[A-Za-z0-9_\s]", "", non_cjk)

        return len(cjk) + len(words) + max(1, len(symbols) // 4)

    def _build_debug_report(self, blocks: list[ContextBlock], total_tokens: int) -> str:
        lines = []
        lines.append("【Context Debug Report】")
        lines.append(f"total_tokens≈{total_tokens}")
        lines.append(f"max_context_tokens={self.config.max_context_tokens}")
        lines.append("")

        for i, block in enumerate(blocks, start=1):
            lines.append(
                f"{i}. name={block.name}, role={block.role}, "
                f"tokens≈{block.token_count}, priority={block.priority}, "
                f"metadata={block.metadata}"
            )

        return "\n".join(lines)