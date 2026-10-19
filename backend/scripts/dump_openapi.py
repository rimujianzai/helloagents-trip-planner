"""把 FastAPI 应用的 OpenAPI schema 导出为 JSON。

用法（在 backend/ 目录下，用项目 venv 运行）:
    python scripts/dump_openapi.py

产出: 项目根目录的 openapi.json，供前端 `npm run gen:types`
(openapi-typescript) 生成 TypeScript 类型定义，替代前后端手工同步类型。
"""

import json
import sys
from pathlib import Path

# 让 `import app` 在任意工作目录下都能解析到 backend/
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.api.main import app  # noqa: E402


def main() -> None:
    schema = app.openapi()
    out_path = BACKEND_DIR.parent / "openapi.json"
    out_path.write_text(
        json.dumps(schema, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"✅ OpenAPI schema 已导出: {out_path}")
    print(f"   路径数: {len(schema.get('paths', {}))}")
    print(f"   Schema 数: {len(schema.get('components', {}).get('schemas', {}))}")
    print("   下一步: cd frontend && npm run gen:types")


if __name__ == "__main__":
    main()
