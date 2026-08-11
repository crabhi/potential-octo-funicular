"""One condition grammar, two backends (runtime evaluation and Z3).

A condition is a Python-syntax boolean expression over a fixed, *typed*
vocabulary of situation variables. The same parsed tree is

  (a) evaluated against concrete situations by the server on every request,
  (b) compiled to a Z3 formula by the analyzer,

so what the running service enforces and what the solver reasons about
cannot drift — there is exactly one semantics, checked exhaustively by
`tests/test_engine.py` (every situation, both backends, same verdict).

Supported syntax:

    a and b, a or b, not a, implies(a, b)
    <enum-var> == "value", <enum-var> != "value"
    <enum-var> in ["v1", "v2"], <enum-var> not in [...]
    <bool-var>                                          (bare boolean)

Variables and enum constants are validated against the vocabulary at load
time: a typo in a rule is a load error, never a silently-false condition.
"""

import ast


class ConditionError(Exception):
    pass


class Vocabulary:
    """Typed situation variables: enums over finite domains, and booleans."""

    def __init__(self, enums, bools):
        self.enums = {name: tuple(dom) for name, dom in enums.items()}
        self.bools = tuple(bools)
        overlap = set(self.enums) & set(self.bools)
        if overlap:
            raise ConditionError(f"variables declared twice: {sorted(overlap)}")

    @property
    def variables(self):
        return set(self.enums) | set(self.bools)


def parse(source, vocab):
    """Parse and type-check a condition; returns a Condition."""
    try:
        tree = ast.parse(source, mode="eval").body
    except SyntaxError as e:
        raise ConditionError(f"syntax error in condition {source!r}: {e}") from e
    return Condition(source, _lower(tree, vocab), vocab)


# --- internal form ---------------------------------------------------------
# ('and'|'or', [nodes]) ('not', node) ('implies', a, b)
# ('eq'|'ne', var, value) ('in'|'notin', var, (values,)) ('var', name)


def _dotted_name(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
        return f"{node.value.id}.{node.attr}"
    return None


def _lower(node, vocab):
    if isinstance(node, ast.BoolOp):
        op = "and" if isinstance(node.op, ast.And) else "or"
        return (op, [_lower(v, vocab) for v in node.values])
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return ("not", _lower(node.operand, vocab))
    if isinstance(node, ast.Call):
        if _dotted_name(node.func) != "implies" or len(node.args) != 2 or node.keywords:
            raise ConditionError("only implies(a, b) calls are allowed")
        return ("implies", _lower(node.args[0], vocab), _lower(node.args[1], vocab))
    if isinstance(node, ast.Compare):
        if len(node.ops) != 1:
            raise ConditionError("chained comparisons are not allowed")
        var = _dotted_name(node.left)
        if var not in vocab.enums:
            raise ConditionError(f"left side of comparison must be an enum variable, got {ast.dump(node.left)}")
        op, right = node.ops[0], node.comparators[0]
        if isinstance(op, (ast.Eq, ast.NotEq)):
            value = _enum_const(right, var, vocab)
            return ("eq" if isinstance(op, ast.Eq) else "ne", var, value)
        if isinstance(op, (ast.In, ast.NotIn)):
            if not isinstance(right, ast.List):
                raise ConditionError(f"right side of 'in' must be a list literal ({var})")
            values = tuple(_enum_const(e, var, vocab) for e in right.elts)
            return ("in" if isinstance(op, ast.In) else "notin", var, values)
        raise ConditionError("only ==, !=, in, not in comparisons are allowed")
    var = _dotted_name(node)
    if var is not None:
        if var in vocab.bools:
            return ("var", var)
        if var in vocab.enums:
            raise ConditionError(f"enum variable {var} cannot be used as a bare boolean")
        raise ConditionError(f"unknown variable {var!r}")
    raise ConditionError(f"unsupported syntax: {ast.dump(node)}")


def _enum_const(node, var, vocab):
    if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
        raise ConditionError(f"comparisons with {var} must use string literals")
    if node.value not in vocab.enums[var]:
        raise ConditionError(
            f"{node.value!r} is not a value of {var} (domain: {list(vocab.enums[var])})")
    return node.value


class Condition:
    def __init__(self, source, tree, vocab):
        self.source = source
        self._tree = tree
        self._vocab = vocab

    def __repr__(self):
        return f"Condition({self.source!r})"

    # -- backend (a): concrete evaluation ------------------------------------
    def evaluate(self, situation):
        return self._eval(self._tree, situation)

    def _eval(self, t, s):
        kind = t[0]
        if kind == "and":
            return all(self._eval(x, s) for x in t[1])
        if kind == "or":
            return any(self._eval(x, s) for x in t[1])
        if kind == "not":
            return not self._eval(t[1], s)
        if kind == "implies":
            return (not self._eval(t[1], s)) or self._eval(t[2], s)
        if kind == "eq":
            return s[t[1]] == t[2]
        if kind == "ne":
            return s[t[1]] != t[2]
        if kind == "in":
            return s[t[1]] in t[2]
        if kind == "notin":
            return s[t[1]] not in t[2]
        if kind == "var":
            return bool(s[t[1]])
        raise AssertionError(kind)

    # -- backend (b): Z3 compilation ------------------------------------------
    def to_z3(self, symbols):
        """symbols: SymbolTable mapping variables to Z3 constants/literals."""
        import z3

        def go(t):
            kind = t[0]
            if kind == "and":
                return z3.And(*[go(x) for x in t[1]])
            if kind == "or":
                return z3.Or(*[go(x) for x in t[1]])
            if kind == "not":
                return z3.Not(go(t[1]))
            if kind == "implies":
                return z3.Implies(go(t[1]), go(t[2]))
            if kind == "eq":
                return symbols.const(t[1]) == symbols.literal(t[1], t[2])
            if kind == "ne":
                return symbols.const(t[1]) != symbols.literal(t[1], t[2])
            if kind == "in":
                return z3.Or(*[symbols.const(t[1]) == symbols.literal(t[1], v) for v in t[2]])
            if kind == "notin":
                return z3.And(*[symbols.const(t[1]) != symbols.literal(t[1], v) for v in t[2]])
            if kind == "var":
                return symbols.const(t[1])
            raise AssertionError(kind)

        return go(self._tree)
