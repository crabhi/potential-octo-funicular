"""A tiny, safe expression language compiled to Z3 terms.

Grammar (Python-expression syntax, parsed via `ast` and whitelisted node by
node -- nothing outside this list is ever evaluated):

    formula := boolexpr
    boolexpr := boolexpr ("and" | "or") boolexpr
              | "not" boolexpr
              | "implies" "(" boolexpr "," boolexpr ")"
              | compare
    compare := arith (("==" | "!=" | "<" | "<=" | ">" | ">=") arith)+
    arith := arith ("+" | "-" | "*" | "/") arith | "-" arith | NAME | INT | BOOL | STRING

STRING literals are only meaningful as one side of a comparison against an
enum-typed variable (they denote that enum's constant, e.g. `phase == "expand"`).

There is exactly one whitelisted function call: `implies(a, b)`.
Anything else (attribute access, subscripting, other calls, comprehensions,
lambdas, ...) raises ExprError -- the whitelist is closed, not a blocklist.
"""

from __future__ import annotations

import ast
from typing import Any, Dict

import z3


class ExprError(Exception):
    """Raised for anything outside the mini expression language."""


_COMPARE_OPS = {
    ast.Eq: lambda a, b: a == b,
    ast.NotEq: lambda a, b: a != b,
    ast.Lt: lambda a, b: a < b,
    ast.LtE: lambda a, b: a <= b,
    ast.Gt: lambda a, b: a > b,
    ast.GtE: lambda a, b: a >= b,
}


class ExprCompiler:
    """Compiles a formula string into a Z3 BoolRef, given a variable schema."""

    def __init__(self, variables: Dict[str, Any], z3vars: Dict[str, Any]):
        self.variables = variables
        self.z3vars = z3vars

    def compile(self, formula: str):
        try:
            tree = ast.parse(formula, mode="eval")
        except SyntaxError as e:
            raise ExprError(f"syntax error in formula {formula!r}: {e}") from e
        return self._eval(tree.body)

    # -- dispatcher -----------------------------------------------------

    def _eval(self, node: ast.AST):
        if isinstance(node, ast.BoolOp):
            values = [self._eval(v) for v in node.values]
            if isinstance(node.op, ast.And):
                return z3.And(*values)
            if isinstance(node.op, ast.Or):
                return z3.Or(*values)
            raise ExprError(f"unsupported boolean operator: {node.op}")

        if isinstance(node, ast.UnaryOp):
            if isinstance(node.op, ast.Not):
                return z3.Not(self._eval(node.operand))
            if isinstance(node.op, ast.USub):
                return -self._eval(node.operand)
            raise ExprError(f"unsupported unary operator: {node.op}")

        if isinstance(node, ast.Compare):
            terms = []
            left_node = node.left
            for op, comparator in zip(node.ops, node.comparators):
                terms.append(self._eval_compare(left_node, op, comparator))
                left_node = comparator
            return z3.And(*terms) if len(terms) > 1 else terms[0]

        if isinstance(node, ast.BinOp):
            left, right = self._eval(node.left), self._eval(node.right)
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            if isinstance(node.op, ast.Div):
                return left / right
            raise ExprError(f"unsupported arithmetic operator: {node.op}")

        if isinstance(node, ast.Call):
            fname = getattr(node.func, "id", None)
            if fname == "implies" and len(node.args) == 2 and not node.keywords:
                return z3.Implies(self._eval(node.args[0]), self._eval(node.args[1]))
            raise ExprError(
                "the only allowed function call is implies(a, b); "
                f"got {ast.dump(node)}"
            )

        if isinstance(node, ast.Name):
            if node.id in self.z3vars:
                return self.z3vars[node.id]
            raise ExprError(f"unknown variable: {node.id!r}")

        if isinstance(node, ast.Constant):
            if isinstance(node.value, bool):
                return z3.BoolVal(node.value)
            if isinstance(node.value, int):
                return z3.IntVal(node.value)
            if isinstance(node.value, str):
                raise ExprError(
                    f"string literal {node.value!r} may only appear directly "
                    "next to an enum variable in a comparison, e.g. phase == "
                    f"{node.value!r}"
                )
            raise ExprError(f"unsupported literal: {node.value!r}")

        raise ExprError(f"disallowed syntax node: {type(node).__name__}")

    # -- comparisons, with enum-literal resolution -----------------------

    def _eval_compare(self, left_node: ast.AST, op: ast.cmpop, right_node: ast.AST):
        op_fn = _COMPARE_OPS.get(type(op))
        if op_fn is None:
            raise ExprError(f"unsupported comparison operator: {op}")
        left = self._eval_side(left_node, right_node)
        right = self._eval_side(right_node, left_node)
        return op_fn(left, right)

    def _eval_side(self, node: ast.AST, other_node: ast.AST):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            varname = self._varname_of(other_node)
            spec = self.variables[varname]
            if spec.type != "enum":
                raise ExprError(
                    f"string literal {node.value!r} compared against "
                    f"non-enum variable {varname!r}"
                )
            if node.value not in spec.consts:
                raise ExprError(
                    f"{node.value!r} is not a value of enum {varname!r} "
                    f"(allowed: {list(spec.consts)})"
                )
            return spec.consts[node.value]
        return self._eval(node)

    def _varname_of(self, node: ast.AST) -> str:
        if isinstance(node, ast.Name) and node.id in self.z3vars:
            return node.id
        raise ExprError(
            "an enum string literal must be compared directly against a "
            "variable name, e.g. phase == \"expand\""
        )
