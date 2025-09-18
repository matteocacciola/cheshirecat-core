import ast
from _ast import AST


# Max depth for AST traversal to prevent overly complex/obfuscated code
MAX_AST_DEPTH = 100


# --- Security Configuration ---
# List of forbidden modules/functions that should not be imported or called directly
FORBIDDEN_IMPORTS = [
    "os", "sys", "subprocess", "shutil", "requests", "urllib", # Basic system/network interaction
    "socket", "tempfile", "glob", "zipfile", "tarfile", # File system manipulation beyond plugin scope
    "pickle", "marshal", # Deserialization risks
    "ctypes", # Access C functions
    "__import__", "exec", "eval", # Code execution
    "compile", # Code compilation
    "open", # Direct file access (consider allowing with strict path validation if needed for plugin data)
]

# List of forbidden function calls (even if their modules are not strictly forbidden)
FORBIDDEN_CALLS = [
    "os.system", "os.exec", "os.fork", "os.spawn",
    "subprocess.run", "subprocess.call", "subprocess.Popen",
    "shutil.rmtree", "shutil.move", "shutil.copy",
    "requests.get", "requests.post", # Generic network requests
    "urllib.request.urlopen",
    "socket.socket",
    "tempfile.mkdtemp", "tempfile.mkstemp",
    "eval", "exec", "__import__", "compile",
    "builtins.open", # Explicitly disallow open from builtins if allowing a custom "open"
]


# Define a custom exception for malicious code detection
class MaliciousCodeError(Exception):
    pass


# Custom AST visitor to find forbidden elements
class PythonSecurityVisitor(ast.NodeVisitor):
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.found_malicious = False
        self.current_depth = 0

    def generic_visit(self, node: AST):
        self.current_depth += 1
        if self.current_depth > MAX_AST_DEPTH:
            self.found_malicious = True
            raise MaliciousCodeError(f"AST depth exceeded maximum: {MAX_AST_DEPTH}")
        super().generic_visit(node)
        self.current_depth -= 1

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            if alias.name in FORBIDDEN_IMPORTS:
                self.found_malicious = True
                raise MaliciousCodeError(f"Forbidden import: {alias.name} in {self.file_path} line {node.lineno}")
        self.generic_visit(node)  # type: ignore

    def visit_ImportFrom(self, node: ast.ImportFrom):
        if node.module and node.module in FORBIDDEN_IMPORTS:
            self.found_malicious = True
            raise MaliciousCodeError(
                f"Forbidden import from module: {node.module} in {self.file_path} line {node.lineno}")
        for alias in node.names:
            full_name = f"{node.module}.{alias.name}" if node.module else alias.name
            if full_name in FORBIDDEN_IMPORTS:  # Check if importing a forbidden specific item
                self.found_malicious = True
                raise MaliciousCodeError(f"Forbidden import: {full_name} in {self.file_path} line {node.lineno}")
        self.generic_visit(node)  # type: ignore

    def visit_Call(self, node: ast.Call):
        # Check for direct calls to forbidden built-in functions
        if isinstance(node.func, ast.Name) and node.func.id in FORBIDDEN_IMPORTS:
            self.found_malicious = True
            raise MaliciousCodeError(
                f"Direct call to forbidden built-in: {node.func.id} in {self.file_path} line {node.lineno}"
            )

        # Check for forbidden attribute access (e.g., os.system)
        if isinstance(node.func, ast.Attribute):
            # Reconstruct the full call name
            func_path = []
            current = node.func
            while isinstance(current, (ast.Attribute, ast.Name)):
                if isinstance(current, ast.Attribute):
                    func_path.append(current.attr)
                    current = current.value
                else:  # ast.Name
                    func_path.append(current.id)
                    break
            full_call_name = ".".join(reversed(func_path))
            if full_call_name in FORBIDDEN_CALLS:
                self.found_malicious = True
                raise MaliciousCodeError(
                    f"Forbidden function call: {full_call_name} in {self.file_path} line {node.lineno}"
                )
        self.generic_visit(node)  # type: ignore

    # Detect `exec` and `eval` usage
    def visit_Expr(self, node: ast.Expr):
        if isinstance(node.value, ast.Call):
            if isinstance(node.value.func, ast.Name) and node.value.func.id in ["exec", "eval"]:
                self.found_malicious = True
                raise MaliciousCodeError(
                    f"Direct call to code execution function: {node.value.func.id} in {self.file_path} line {node.lineno}"
                )
        self.generic_visit(node)  # type: ignore

    # Detect direct calls to builtins like `open` or `__import__`
    def visit_Name(self, node: ast.Name):
        if node.id in ["open", "__import__"] and isinstance(node.ctx, ast.Load):
            # This only catches the name usage, `visit_Call` will catch the actual call.
            # This is more for flagging the mere presence if desired, but `visit_Call` is more precise.
            pass  # We handle this in visit_Call for accuracy.
        self.generic_visit(node)  # type: ignore
