"""
日志配置 - 使用 loguru
"""
import sys
from loguru import logger
from pathlib import Path

log_dir = Path("data/logs")
log_dir.mkdir(parents=True, exist_ok=True)

# 移除默认 handler
logger.remove()

# 控制台输出
logger.add(
    sys.stdout,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    level="INFO",
    colorize=True,
)

# 文件输出
logger.add(
    str(log_dir / "app_{time:YYYY-MM-DD}.log"),
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
    level="DEBUG",
    rotation="10 MB",
    retention="30 days",
    encoding="utf-8",
)


def get_logger():
    return logger
