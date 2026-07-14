"""阶段 5：LangGraph 对话引擎（步骤 5.1 起逐步落地）。

不在包初始化时 import graph：否则 ``from app.engine.nodes.load_context import ...``
会先执行本包 ``__init__``，graph 再 import load_context，形成循环依赖。
请使用 ``from app.engine.graph import build_compiled_graph`` 等显式子模块导入。
"""

__all__: list[str] = []
