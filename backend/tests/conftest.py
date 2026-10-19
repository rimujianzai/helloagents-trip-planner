"""pytest 共享夹具。

让测试既能从 backend/ 目录跑（`pytest`），也能从仓库根目录跑
（`pytest backend/tests`）：把 backend 加进 sys.path，`import app` 才能解析。
"""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
