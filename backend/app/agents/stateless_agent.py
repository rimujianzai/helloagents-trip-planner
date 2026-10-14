"""无跨请求历史累积的 SimpleAgent。

## 问题

hello_agents 的 ``SimpleAgent.run()`` 会把本轮 user/assistant 消息追加进
``self._history``(simple_agent.py:275-276 与 320-321),并在**下一次**构造
messages 时把整份历史带上(simple_agent.py:265-267)。

对多轮聊天这是正确行为。但本项目的 4 个 Agent 都是**进程级单例**
(``get_trip_planner_agent()``),而每个 HTTP 请求都是一次独立的规划任务 ——
于是历史会跨请求无限累积:

    第 1 次请求后:每个 Agent 的 _history 有 2 条
    第 10 次请求后:每个 Agent 的 _history 有 20 条
    → 每次 LLM 调用的 prompt 里都塞着前面 9 位用户的目的地与偏好

后果有两个:token 成本随请求数线性上升;更麻烦的是**串味** —— 上一位用户问的是
上海,这一位问北京,模型可能被历史里的「上海」带偏。

## 解决

把「每次 run 都从零开始」固化成一个子类,而不是在业务代码里到处手动
``agent._history.clear()``。
"""

from typing import Iterator

from hello_agents import SimpleAgent


class StatelessSimpleAgent(SimpleAgent):
    """每次 ``run`` / ``stream_run`` 都从空白上下文开始的 SimpleAgent。

    单次调用内部的多轮工具迭代不受影响 —— 那些轮次共用的是 ``run()`` 里的
    局部 ``messages`` 列表,与 ``_history`` 无关。
    """

    def _reset_history(self) -> None:
        self._history.clear()

    def run(self, input_text: str, max_tool_iterations: int = 3, **kwargs) -> str:
        self._reset_history()
        try:
            return super().run(input_text, max_tool_iterations, **kwargs)
        finally:
            # 即便本次调用抛异常,也不把半截上下文留给下一个请求
            self._reset_history()

    def stream_run(self, input_text: str, **kwargs) -> Iterator[str]:
        self._reset_history()
        try:
            yield from super().stream_run(input_text, **kwargs)
        finally:
            self._reset_history()
