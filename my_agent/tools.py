from abc import ABC, abstractmethod
import ast
import math
import operator


class BaseTool(ABC):
    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description

    @abstractmethod
    def execute(self, tool_input) -> str:
        pass


class ToolRegistry:
    def __init__(self):
        self.tools = {}

    def register_tool(self, tool: BaseTool):
        self.tools[tool.name] = tool

    def get_tool(self, tool_name: str):
        return self.tools.get(tool_name)

    def get_all_tools(self):
        return list(self.tools.values())

    def execute_tool(self, tool_name: str, tool_input) -> str:
        tool = self.get_tool(tool_name)
        if not tool:
            return f"工具不存在：{tool_name}"

        try:
            return tool.execute(tool_input)
        except Exception as e:
            return f"工具执行失败: {type(e).__name__}: {e}"

    def get_tools_description(self) -> str:
        if not self.tools:
            return "当前没有工具"

        descriptions = []
        for tool in self.tools.values():
            descriptions.append(f"- {tool.name}: {tool.description}")
        return "\n".join(descriptions)


class CalculatorTool(BaseTool):
    """AST-based safe calculator. No eval()."""

    # Supported binary operators
    _BIN_OPS = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv,
        ast.Mod: operator.mod,
        ast.Pow: operator.pow,
    }

    # Supported unary operators
    _UNARY_OPS = {
        ast.UAdd: operator.pos,
        ast.USub: operator.neg,
    }

    # Safe functions and constants
    _SAFE_NAMES = {
        "sqrt": math.sqrt,
        "sin": math.sin,
        "cos": math.cos,
        "tan": math.tan,
        "abs": abs,
        "round": round,
        "pow": pow,
        "pi": math.pi,
        "e": math.e,
    }

    def __init__(self):
        super().__init__(
            name="calculator",
            description="数字计算工具，可计算表达式（支持 +, -, *, /, **, sqrt, sin, cos, tan, log, abs, round, pi, e）",
        )

    def get_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": "calculator",
                "description": "计算数学表达式，例如 2 + 3 * 4",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "expression": {
                            "type": "string",
                            "description": "要计算的表达式，例如 2 + 3 * 4",
                        }
                    },
                    "required": ["expression"],
                },
            },
        }

    def execute(self, tool_input) -> str:
        if isinstance(tool_input, dict):
            expression = str(tool_input.get("expression", "")).strip()
        else:
            expression = str(tool_input).strip()

        if not expression:
            return "表达式为空"

        try:
            tree = ast.parse(expression, mode="eval")
            result = self._eval_node(tree.body)
            # Format: drop trailing .0 for integers
            if isinstance(result, float) and result == int(result) and abs(result) < 1e15:
                return str(int(result))
            return str(result)
        except (ValueError, TypeError, ZeroDivisionError) as e:
            return f"计算错误: {e}"
        except Exception as e:
            return f"不支持的表达式: {e}"

    def _eval_node(self, node):
        """Recursively evaluate an AST node."""
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)):
                return node.value
            raise ValueError(f"不支持的常量类型: {type(node.value).__name__}")

        if isinstance(node, ast.BinOp):
            op_func = self._BIN_OPS.get(type(node.op))
            if op_func is None:
                raise ValueError(f"不支持的运算符: {type(node.op).__name__}")
            left = self._eval_node(node.left)
            right = self._eval_node(node.right)
            return op_func(left, right)

        if isinstance(node, ast.UnaryOp):
            op_func = self._UNARY_OPS.get(type(node.op))
            if op_func is None:
                raise ValueError(f"不支持的一元运算符: {type(node.op).__name__}")
            return op_func(self._eval_node(node.operand))

        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name):
                raise ValueError("只支持简单函数调用")
            func_name = node.func.id
            func = self._SAFE_NAMES.get(func_name)
            if func is None or not callable(func):
                raise ValueError(f"不支持的函数: {func_name}")
            args = [self._eval_node(arg) for arg in node.args]
            return func(*args)

        if isinstance(node, ast.Name):
            val = self._SAFE_NAMES.get(node.id)
            if val is None:
                raise ValueError(f"未知变量: {node.id}")
            if callable(val):
                raise ValueError(f"'{node.id}' 是函数，需要加括号调用")
            return val

        raise ValueError(f"不支持的表达式节点: {type(node).__name__}")