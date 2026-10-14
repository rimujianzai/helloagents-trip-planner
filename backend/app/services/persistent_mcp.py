"""常驻会话版 MCP 工具。

## 为什么要这个模块

hello_agents 的 ``MCPTool.run()`` 每次调用都会 ``async with MCPClient(...)``,
也就是**每次工具调用都重新拉起一个 uvx 子进程**。2026-10-14 对 amap-mcp-server
的实测数据:

    纯握手(子进程启动 + list_tools)   2.35 / 2.38 / 2.37 s
    单次 search_poi 总耗时            2.7  - 3.0  s
    其中真实搜索                      约 0.5 s

即每次调用约 80% 的时间花在重开子进程上。本模块把它降为"整个进程只启动一次"。

## 原理

一个后台线程跑一个专属事件循环,循环里维持一个长期存活的 ``MCPClient`` 会话;
工具调用通过 ``asyncio.run_coroutine_threadsafe`` 投递到那个循环里执行。

## 为什么是子类而不是改框架

``MCPTool.get_expanded_tools()`` 会把每个 MCP 工具包装成 ``MCPWrappedTool``,
而 ``MCPWrappedTool.run()`` 会回调 ``self.mcp_tool.run(...)``
(见 mcp_wrapper_tool.py:118)。所以只要重写 ``run()`` 与 ``_discover_tools()``,
**整条 Agent 工具调用链都会自动走常驻会话**,无需改动 hello_agents 源码。
"""

import asyncio
import threading
from typing import Any, Dict, List, Optional

from hello_agents.protocols.mcp.client import MCPClient
from hello_agents.tools import MCPTool

# 同一份启动命令 + 环境变量在进程内只保留一个会话(避免多个子进程)
_SESSIONS: Dict[tuple, "_MCPSession"] = {}
_SESSIONS_LOCK = threading.Lock()


class _MCPSession:
    """在后台线程里维持一个长期存活的 MCP 会话。

    线程模型:
        调用方线程 --run_coroutine_threadsafe--> 后台事件循环 --stdio--> MCP 子进程

    ``call_tool`` 可以从任意线程并发调用,互不阻塞(不持锁等待结果)。
    """

    def __init__(
        self,
        server_command: Optional[List[str]],
        server_args: Optional[List[str]],
        env: Optional[Dict[str, str]],
        connect_timeout: float = 60.0,
        call_timeout: float = 60.0,
    ):
        self.server_command = server_command
        self.server_args = server_args or []
        self.env = env or {}
        self.connect_timeout = connect_timeout
        self.call_timeout = call_timeout

        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._client: Optional[MCPClient] = None
        # 两把锁分开, 不能合并:
        #   _loop_lock 只保护"后台事件循环的启动", 会被 _connect() 间接获取;
        #   _conn_lock 保护连接的建立/重连, 持有期间会调用 _connect()。
        # 若共用一把 threading.Lock(不可重入), 连接建立路径会自我死锁。
        self._loop_lock = threading.Lock()
        self._conn_lock = threading.Lock()

    # ---------------- 后台事件循环 ----------------

    def _ensure_loop(self) -> None:
        """启动后台事件循环(幂等)"""
        if self._loop is not None:
            return
        with self._loop_lock:
            if self._loop is not None:
                return
            ready = threading.Event()

            def runner() -> None:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                self._loop = loop
                ready.set()
                loop.run_forever()
                # run_forever 返回后收尾
                try:
                    pending = asyncio.all_tasks(loop)
                    for task in pending:
                        task.cancel()
                    if pending:
                        loop.run_until_complete(
                            asyncio.gather(*pending, return_exceptions=True)
                        )
                finally:
                    loop.close()

            thread = threading.Thread(
                target=runner, name="amap-mcp-session", daemon=True
            )
            thread.start()
            self._thread = thread
            if not ready.wait(timeout=10):
                raise RuntimeError("MCP 会话后台事件循环启动超时")

    def _submit(self, coro, timeout: float) -> Any:
        """把协程投递到后台循环并等待结果"""
        self._ensure_loop()
        # _ensure_loop() 已保证非 None;显式取出并校验,便于类型检查器收窄
        loop = self._loop
        if loop is None:
            raise RuntimeError("MCP 会话后台事件循环未就绪")
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result(timeout=timeout)

    # ---------------- 连接管理 ----------------

    async def _connect_async(self) -> MCPClient:
        client = MCPClient(
            self.server_command,
            self.server_args,
            env=self.env if self.env else None,
        )
        await client.__aenter__()
        return client

    def _connect(self) -> MCPClient:
        """建立连接(调用方需持有 self._conn_lock)"""
        self._ensure_loop()
        client: MCPClient = self._submit(
            self._connect_async(), self.connect_timeout
        )
        self._client = client
        return client

    def _disconnect(self) -> None:
        """关闭连接(调用方需持有 self._conn_lock),失败不抛"""
        client, self._client = self._client, None
        if client is None or self._loop is None:
            return

        async def close() -> None:
            try:
                await client.__aexit__(None, None, None)
            except Exception:
                pass

        try:
            self._submit(close(), timeout=10)
        except Exception:
            pass

    def _ensure_client(self) -> MCPClient:
        """取到可用连接;不存在则建立。**不长期持锁**,以允许并发调用。"""
        client = self._client
        if client is not None:
            return client
        with self._conn_lock:
            if self._client is None:
                self._connect()
            client = self._client
            if client is None:
                raise RuntimeError("MCP 会话建立失败")
            return client

    def _reconnect(self, failed_client: Optional[MCPClient] = None) -> MCPClient:
        """重建会话。

        传入出故障的那个 client 实例: 若期间已有别的线程重建过(当前实例已不是它),
        就直接复用新会话 —— 否则多个并发调用同时失败时, 会排队做 N 次无谓的
        断开+重连(每次约 2.4s), 形成"重连风暴"。
        """
        with self._conn_lock:
            if failed_client is not None and self._client is not failed_client:
                current = self._client
                if current is not None:
                    return current
            self._disconnect()
            return self._connect()

    # ---------------- 对外接口 ----------------

    def list_tools(self) -> List[Dict[str, Any]]:
        client = self._ensure_client()
        try:
            return self._submit(client.list_tools(), self.call_timeout)
        except Exception:
            client = self._reconnect(client)
            return self._submit(client.list_tools(), self.call_timeout)

    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        client = self._ensure_client()
        try:
            return self._submit(
                client.call_tool(tool_name, arguments), self.call_timeout
            )
        except Exception:
            # 会话可能已失效(子进程崩溃 / 管道断开),重连一次再试
            client = self._reconnect(client)
            return self._submit(
                client.call_tool(tool_name, arguments), self.call_timeout
            )

    def shutdown(self) -> None:
        with self._conn_lock:
            self._disconnect()
        loop = self._loop
        if loop is not None:
            loop.call_soon_threadsafe(loop.stop)
            self._loop = None


def get_shared_session(
    server_command: Optional[List[str]],
    server_args: Optional[List[str]],
    env: Optional[Dict[str, str]],
) -> _MCPSession:
    """按 (启动命令, 环境变量) 复用同一个常驻会话,避免重复起子进程"""
    key = (
        tuple(server_command or []),
        tuple(server_args or []),
        tuple(sorted((env or {}).items())),
    )
    with _SESSIONS_LOCK:
        session = _SESSIONS.get(key)
        if session is None:
            session = _MCPSession(server_command, server_args, env)
            _SESSIONS[key] = session
        return session


def shutdown_all_sessions() -> None:
    """关闭进程内所有常驻会话(供应用关闭时调用,避免留下孤立的 uvx 子进程)"""
    with _SESSIONS_LOCK:
        sessions = list(_SESSIONS.values())
        _SESSIONS.clear()
    for session in sessions:
        try:
            session.shutdown()
        except Exception:
            pass


class PersistentMCPTool(MCPTool):
    """用常驻会话执行 MCP 调用的 ``MCPTool``。

    接口与父类完全一致(``run`` 返回字符串、``_available_tools`` 为工具字典列表),
    因此可以直接替换 ``MCPTool`` 使用,Agent 侧无需任何改动。
    """

    def __init__(self, *args, **kwargs):
        # 必须早于 super().__init__ —— 因为父类构造里会调用 _discover_tools()
        self._session: Optional[_MCPSession] = None
        super().__init__(*args, **kwargs)

    def _get_session(self) -> _MCPSession:
        if self._session is None:
            self._session = get_shared_session(
                self.server_command, self.server_args, self.env
            )
        return self._session

    def _discover_tools(self) -> None:
        """覆盖父类:用常驻会话发现工具,而不是每次新建子进程"""
        try:
            self._available_tools = self._get_session().list_tools()
        except Exception as e:
            # 与父类保持一致:发现失败不阻断初始化,但**不静默**——留痕便于排查
            print(f"⚠️ MCP 工具发现失败: {type(e).__name__}: {e}")
            print(f"   启动命令: {' '.join(self.server_command or [])}")
            self._available_tools = []

    def run(self, parameters: Dict[str, Any]) -> str:
        """覆盖父类:call_tool / list_tools 走常驻会话,其余动作回退父类"""
        action = (parameters.get("action") or "").lower()
        if not action and "tool_name" in parameters:
            action = "call_tool"

        if action == "list_tools":
            try:
                tools = self._get_session().list_tools()
            except Exception as e:
                return f"MCP 操作失败: {str(e)}"
            if not tools:
                return "没有找到可用的工具"
            result = f"找到 {len(tools)} 个工具:\n"
            for tool in tools:
                result += f"- {tool['name']}: {tool['description']}\n"
            return result

        if action == "call_tool":
            tool_name = parameters.get("tool_name")
            if not tool_name:
                return "错误：必须指定 tool_name 参数"
            try:
                result = self._get_session().call_tool(
                    tool_name, parameters.get("arguments", {})
                )
            except Exception as e:
                return f"MCP 操作失败: {str(e)}"
            # 保持与父类一致的文本格式:调用方(amap_service / LLM)依赖它做解析
            return f"工具 '{tool_name}' 执行结果:\n{result}"

        # list_resources / read_resource / list_prompts / get_prompt 等低频动作,
        # 仍走父类实现(它们不在热路径上,单独重开连接可以接受)
        return super().run(parameters)
