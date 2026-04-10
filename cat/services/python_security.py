import ast
from pathlib import Path


FORBIDDEN_MODULES = {
    "ctypes", "cffi", "pty", "termios",
    "socket",  # direct networking
    "pickle", "shelve",  # arbitrary deserialization
    "importlib",  # dynamic import
    "zipimport", "pkgutil",
}

FORBIDDEN_BUILTINS = {
    "__import__", "exec", "eval", "compile",
    "open",  # use pathlib or a safe wrapper, instead
    "breakpoint",  # access to the debugger
    "globals", "locals", "vars",  # access to the environment
    "memoryview",  # access to raw memory
}


class ASTSecurityVisitor(ast.NodeVisitor):
    def __init__(self, filepath: str):
        self.filepath = filepath
        self._depth = 0

    def _fail(self, node: ast.AST, reason: str):
        raise SecurityError(f"{self.filepath}:{node.lineno}: {reason}")

    def generic_visit(self, node: ast.AST):
        self._depth += 1
        if self._depth > 200:
            raise SecurityError(f"{self.filepath}: AST too complex")
        super().generic_visit(node)
        self._depth -= 1

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            root = alias.name.split(".")[0]
            if root in FORBIDDEN_MODULES:
                self._fail(node, f"import forbidden: {alias.name}")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        if node.module:
            root = node.module.split(".")[0]
            if root in FORBIDDEN_MODULES:
                self._fail(node, f"import forbidden: {node.module}")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call):
        # Case: direct name (exec, eval, open, ...)
        if isinstance(node.func, ast.Name):
            if node.func.id in FORBIDDEN_BUILTINS:
                self._fail(node, f"builtin forbidden: {node.func.id}")

        # Case: attribute (os.system, subprocess.Popen, ...)
        if isinstance(node.func, ast.Attribute):
            full = _reconstruct_attr(node.func)
            if full:
                # Block __dunder__ on whaetever object
                if any(part.startswith("__") for part in full.split(".")):
                    self._fail(node, f"dunder access forbidden: {full}")

        # # Block getattr(x, "something") — classic bypass mean
        # if isinstance(node.func, ast.Name) and node.func.id == "getattr":
        #     self._fail(node, "getattr() forbidden (mean for bypass)")

        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute):
        # Block the access to __class__, __bases__, __subclasses__, etc.
        if node.attr.startswith("__") and node.attr.endswith("__"):
            dunder_whitelist = {
                "__init__", "__str__", "__repr__", "__len__", "__iter__", "__next__", "__enter__", "__exit__",
            }
            if node.attr not in dunder_whitelist:
                self._fail(node, f"dunder access forbidden: {node.attr}")
        self.generic_visit(node)


def _reconstruct_attr(node: ast.Attribute) -> str | None:
    parts = []
    current = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
        return ".".join(reversed(parts))
    return None


class SecurityError(Exception):
    pass


def ast_scan(filepath: Path) -> None:
    """Raise SecurityError if the file contains forbidden patterns."""
    source = filepath.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source, filename=str(filepath))
    except SyntaxError as exc:
        raise SecurityError(f"Syntax error in {filepath}: {exc}") from exc
    ASTSecurityVisitor(str(filepath)).visit(tree)
