"""backend/src 代码库架构分层与依赖单向性静态检查脚本。

系统架构硬性规定了各层的单向依赖流：
Web API、CLI 与 Worker 边缘层调用 Application，Application 调用 Domain 及其端口契约，
由 Infrastructure 负责实现端口契约。

允许的内部依赖流向（包仅允许导入以下集合中的模块）：

    domain          -> domain
    application     -> domain, application
    infrastructure  -> domain, application, infrastructure
    api             -> domain, application, api, agent_runtime
    agent_runtime   -> domain, application, agent_runtime
    worker          -> domain, application, worker
    cli             -> domain, application, infrastructure, agent_runtime, cli, composition
    composition     -> 全部（依赖装配根）

显式设计约束：
* composition 作为进程依赖注入组装根，可组装任何组件；
* 进程主入口 (main.py / __main__.py) 负责初始化，放开顶层导入；
* CLI、API 与 agent_runtime 严禁直接导入 infrastructure.db 持久层，必须经由用例层；
* 严禁无清晰边界的垃圾模块名（utils, helpers, common, misc, manager）；
* 严禁跨模块导入私有符号（以单下划线 _ 开头的符号）。

执行方式：
    uv run python scripts/check-architecture.py
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parent.parent / "backend" / "src"

if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ALLOWED: dict[str, frozenset[str]] = {
    "domain": frozenset({"domain"}),
    "application": frozenset({"domain", "application"}),
    "infrastructure": frozenset({"domain", "application", "infrastructure"}),
    "api": frozenset({"domain", "application", "api", "agent_runtime"}),
    "agent_runtime": frozenset({"domain", "application", "agent_runtime"}),
    "worker": frozenset({"domain", "application", "worker"}),
    "cli": frozenset(
        {"domain", "application", "infrastructure", "agent_runtime", "cli", "composition"}
    ),
    "composition": frozenset(
        {
            "domain",
            "application",
            "infrastructure",
            "api",
            "agent_runtime",
            "worker",
            "cli",
            "composition",
        }
    ),
}

# Edges that are allowed in general but denied for one package. The command line is a mixed edge:
# most of its commands drive an application use case, and three are administration that has no use
# case behind it — creating the bucket, printing the compiled graph, configuring the tracer. That is
# why it may reach infrastructure at all, and exactly why it may not reach the persistence layer:
# an operator command that wrote rows directly would bypass the fencing every stage depends on.
DENIED: dict[str, frozenset[str]] = {
    "cli": frozenset({"infrastructure.db"}),
    "api": frozenset({"infrastructure.db"}),
    "agent_runtime": frozenset({"infrastructure.db"}),
}

PACKAGES = tuple(ALLOWED)
ENTRYPOINTS = frozenset({"main.py", "__main__.py"})
RULE = (
    "domain->domain; application->domain,application; "
    "infrastructure->domain,application,infrastructure; "
    "api->+api,agent_runtime; agent_runtime->+agent_runtime; worker->+worker; "
    "cli->+cli,composition,infrastructure,agent_runtime; composition->all; "
    "cli/api/agent_runtime may not import infrastructure.db; "
    "no utils/helpers/common/misc/manager module; no private name imported across modules"
)


class Violation:
    """One rule this file breaks: where it imports from, or what it is called."""

    def __init__(self, path: Path, line: int, reason: str) -> None:
        self.path = path
        self.line = line
        self.reason = reason

    def __str__(self) -> str:
        relative = self.path.relative_to(SOURCE_ROOT.parent.parent)
        return f"{relative}:{self.line}: {self.reason}"


# A module name that says nothing about what the module is for. The architecture document forbids
# them by name, and they are the first thing a new file falls back to when its purpose is unclear —
# which is exactly the moment to name the purpose instead. ``base.py`` is deliberately not in this
# list: a declarative base is a real thing with a real name.
VAGUE_MODULE_NAMES = frozenset({"utils.py", "helpers.py", "common.py", "misc.py", "manager.py"})


def vague_name(path: Path) -> str | None:
    """检查模块名是否过于模糊，若违规返回原因。"""
    if path.name in VAGUE_MODULE_NAMES:
        return f"{path.name} 属于无语义命名，架构禁止使用此类无边界模块名"
    return None


def private_names(tree: ast.Module) -> list[tuple[str, int]]:
    """提取跨模块导入的私有符号。"""
    found: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            found.extend(
                (f"{node.module}.{alias.name}", node.lineno)
                for alias in node.names
                if alias.name.startswith("_") and not alias.name.startswith("__")
            )
    return found


def module_names(tree: ast.Module) -> list[tuple[str, int]]:
    """提取所有导入的模块名与所在行号。"""
    found: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend((alias.name, node.lineno) for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            found.append((node.module, node.lineno))
    return found


def package_of(path: Path) -> str | None:
    """获取文件所属的一级内部包名。"""
    head = path.relative_to(SOURCE_ROOT).parts[0]
    return head if head in PACKAGES else None


def main() -> int:
    violations: list[Violation] = []
    for path in sorted(SOURCE_ROOT.rglob("*.py")):
        package = package_of(path)
        if package is None or path.name in ENTRYPOINTS:
            continue
        vague = vague_name(path)
        if vague is not None:
            violations.append(Violation(path, 1, vague))
        allowed = ALLOWED[package]
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for imported, line in module_names(tree):
            target = imported.split(".")[0]
            denied = DENIED.get(package, frozenset())
            against_direction = target in PACKAGES and target not in allowed
            against_denial = any(
                imported == prefix or imported.startswith(prefix + ".") for prefix in denied
            )
            if against_direction or against_denial:
                violations.append(Violation(path, line, f"{package} 禁止导入 {imported}"))
        for imported, line in private_names(tree):
            violations.append(
                Violation(path, line, f"{imported} — 禁止跨模块导入私有符号")
            )

    if not violations:
        print("架构门禁检查通过：所有内部模块导入均符合单向依赖规则")
        return 0

    print(
        f"架构门禁检查失败：发现 {len(violations)} 处违反单向依赖的模块导入"
    )
    for violation in violations:
        print(f"  {violation}")
    print(f"\n允许的依赖规则: {RULE}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
