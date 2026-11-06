"""Safe arithmetic tool; evaluates a restricted expression AST, never Python eval."""
from __future__ import annotations

import ast
import operator
from typing import Any

OPS: dict[type[ast.operator], Any] = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
UNARY: dict[type[ast.unaryop], Any] = {ast.UAdd: operator.pos, ast.USub: operator.neg}


def calculate(expression: str) -> float | int:
    """Calculate a numeric expression with strict node and exponent limits."""
    try:
        node = ast.parse(expression, mode="eval").body
    except SyntaxError as exc:
        raise ValueError("Invalid arithmetic expression") from exc

    def visit(item: ast.AST) -> float | int:
        if isinstance(item, ast.Constant) and isinstance(item.value, (int, float)) and not isinstance(item.value, bool):
            return item.value
        if isinstance(item, ast.BinOp) and type(item.op) in OPS:
            left, right = visit(item.left), visit(item.right)
            if isinstance(item.op, ast.Pow) and abs(right) > 8:
                raise ValueError("Exponent magnitude is limited to 8")
            result = OPS[type(item.op)](left, right)
            if not isinstance(result, (int, float)):
                raise ValueError("Only real-number results are supported")
            if abs(result) > 1e100:
                raise ValueError("Result is too large")
            return result
        if isinstance(item, ast.UnaryOp) and type(item.op) in UNARY:
            return UNARY[type(item.op)](visit(item.operand))
        raise ValueError("Only basic arithmetic is supported")

    return visit(node)
