"""日志配置。

之前全项目只有 ``logging.getLogger(__name__)``，但没有任何地方调用
``basicConfig``，导致 ``logger.info`` 一条都出不来（根 logger 默认级别是
WARNING，且没有 handler）—— 路由里的 ``logger.warning/exception`` 能看到，
纯粹是因为 uvicorn 顺手配了 root handler。脱离 uvicorn 跑（pytest、脚本）
时就完全静默了。

集中在这里配一次，main.py 的 lifespan 与 run.py 启动时各调一次。
"""

import logging
import sys


def setup_logging(level: int = logging.INFO) -> None:
    """配置根 logger。幂等：重复调用不会叠加 handler。"""
    root = logging.getLogger()
    if root.handlers:
        # 已经配置过（例如 uvicorn 先跑了），不再叠加，只对齐级别
        root.setLevel(level)
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
            datefmt="%H:%M:%S",
        )
    )
    root.addHandler(handler)
    root.setLevel(level)

    # 第三方库的 DEBUG 噪音收一收
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
