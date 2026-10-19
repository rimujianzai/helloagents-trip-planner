"""配置管理模块"""

import os
from pathlib import Path
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv

# 加载环境变量
# 首先尝试加载当前目录的.env
load_dotenv()

# 然后尝试加载HelloAgents的.env(如果存在)
helloagents_env = Path(__file__).parent.parent.parent.parent / "HelloAgents" / ".env"
if helloagents_env.exists():
    load_dotenv(helloagents_env, override=False)  # 不覆盖已有的环境变量


class Settings(BaseSettings):
    """应用配置"""

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",  # 忽略额外的环境变量
    )

    # 应用基本配置
    app_name: str = "HelloAgents智能旅行助手"
    app_version: str = "1.0.0"
    debug: bool = False

    # 服务器配置
    host: str = "0.0.0.0"
    port: int = 8000

    # CORS配置 - 使用字符串,在代码中分割
    cors_origins: str = "http://localhost:5173,http://localhost:3000,http://127.0.0.1:5173,http://127.0.0.1:3000"

    # 高德地图API配置
    amap_api_key: str = ""

    # 高德地图MCP服务启动参数
    #
    # 为什么要锁 pydantic<2.12:
    # amap-mcp-server 依赖的 mcp SDK 会从 pydantic 内部导入 eval_type_backport,
    # 而 pydantic 2.12 起移除了这个符号。uvx 默认会解析到最新 pydantic,
    # 于是 MCP 子进程一启动就 ImportError 崩溃 —— 上层表现为 fastmcp 的
    # "Connection closed", 而 hello_agents 的 _discover_tools 会**静默**吞掉这个异常
    # 并把可用工具置空, 最终 Agent 报出「未找到工具 'amap_maps_text_search'」。
    # 不要把这里的约束去掉。
    amap_mcp_package: str = "amap-mcp-server"
    amap_mcp_pydantic_constraint: str = "pydantic<2.12"

    # Unsplash API配置
    # 注意: unsplash_service 只用到 access_key; secret_key 是 OAuth 流程才需要的,
    # 当前项目没有用到 —— 留在这里只是 Unsplash 控制台把两个 key 一起发了出来。
    # 不要误以为少配了它会导致图片功能不可用。
    unsplash_access_key: str = ""
    unsplash_secret_key: str = ""

    # LLM配置 (从环境变量读取,由HelloAgents管理)
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4"

    # 日志配置
    log_level: str = "INFO"

    def get_cors_origins_list(self) -> List[str]:
        """获取CORS origins列表"""
        return [origin.strip() for origin in self.cors_origins.split(',')]

    def get_amap_mcp_command(self) -> List[str]:
        """
        获取启动高德地图MCP服务的命令

        Returns:
            uvx 启动命令, 形如
            ["uvx", "--with", "pydantic<2.12", "amap-mcp-server"]
        """
        return [
            "uvx",
            "--with", self.amap_mcp_pydantic_constraint,
            self.amap_mcp_package,
        ]


# 创建全局配置实例
settings = Settings()


def get_settings() -> Settings:
    """获取配置实例"""
    return settings


# 验证必要的配置
def validate_config():
    """验证配置是否完整"""
    errors = []
    warnings = []

    if not settings.amap_api_key:
        errors.append("AMAP_API_KEY未配置")

    # HelloAgentsLLM会自动从LLM_API_KEY读取,不强制要求OPENAI_API_KEY
    llm_api_key = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not llm_api_key:
        warnings.append("LLM_API_KEY或OPENAI_API_KEY未配置,LLM功能可能无法使用")

    # 检测「机器级环境变量静默覆盖 .env」的经典陷阱。
    # hello_agents/core/llm.py 的解析顺序是:
    #   api_key or DEEPSEEK_API_KEY or LLM_API_KEY
    # 所以只要机器上残留一个 DEEPSEEK_API_KEY, .env 里的 LLM_API_KEY 就会被忽略,
    # 且没有任何提示 —— 表现为"服务正常、请求 200, 但用的是另一个 Key"。
    deepseek_key = os.getenv("DEEPSEEK_API_KEY")
    if deepseek_key and llm_api_key and deepseek_key != llm_api_key:
        warnings.append(
            "DEEPSEEK_API_KEY 与 LLM_API_KEY 同时存在且不同: "
            "HelloAgents 会优先使用 DEEPSEEK_API_KEY, .env 中的 LLM_API_KEY 实际被忽略。"
            "若非本意, 请清除机器级 DEEPSEEK_API_KEY 环境变量。"
        )

    if errors:
        error_msg = "配置错误:\n" + "\n".join(f"  - {e}" for e in errors)
        raise ValueError(error_msg)

    if warnings:
        print("\n⚠️  配置警告:")
        for w in warnings:
            print(f"  - {w}")

    return True


# 打印配置信息(用于调试)
def print_config():
    """打印当前配置(隐藏敏感信息)"""
    print(f"应用名称: {settings.app_name}")
    print(f"版本: {settings.app_version}")
    print(f"服务器: {settings.host}:{settings.port}")
    print(f"高德地图API Key: {'已配置' if settings.amap_api_key else '未配置'}")

    # 检查LLM配置
    llm_api_key = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
    llm_base_url = os.getenv("LLM_BASE_URL") or settings.openai_base_url
    llm_model = os.getenv("LLM_MODEL_ID") or settings.openai_model

    print(f"LLM API Key: {'已配置' if llm_api_key else '未配置'}")
    print(f"LLM Base URL: {llm_base_url}")
    print(f"LLM Model: {llm_model}")
    print(f"日志级别: {settings.log_level}")

