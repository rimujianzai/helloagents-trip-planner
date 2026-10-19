"""启动脚本"""

import logging

import uvicorn
from app.config import get_settings
from app.logging_config import setup_logging

if __name__ == "__main__":
    settings = get_settings()
    setup_logging(getattr(logging, settings.log_level.upper(), logging.INFO))

    uvicorn.run(
        "app.api.main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
        log_level=settings.log_level.lower()
    )

