import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Dict, Any

from src.config import CrawlerConfig
from src.crawler import Crawler

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('crawler.log')
    ]
)

logger = logging.getLogger(__name__)

def load_config(config_path: str) -> CrawlerConfig:
    """从 JSON 文件加载配置并创建 CrawlerConfig 实例"""
    try:
        return CrawlerConfig.from_json(config_path)
    except FileNotFoundError:
        logger.error(f"配置文件未找到: {config_path}")
        raise
    except json.JSONDecodeError as e:
        logger.error(f"配置文件 JSON 格式错误: {e}")
        raise
    except ValueError as e:
        logger.error(f"配置值无效: {e}")
        raise
    except Exception as e:
        logger.error(f"加载配置时发生未知错误: {e}")
        raise

async def main():
    """爬虫程序入口"""
    try:
        config = load_config('config.json')
        logger.info("配置加载成功")
        
        # 确保输出目录存在
        config.output_dir.mkdir(parents=True, exist_ok=True)
        config.image_dir.mkdir(parents=True, exist_ok=True)
        
        async with Crawler(config) as crawler:
            logger.info("开始爬取...")
            await crawler.start()  # 使用 start() 方法来启动爬虫
            logger.info("所有板块爬取完成")
            
    except Exception as e:
        logger.error(f"爬虫运行失败: {e}", exc_info=True)
        sys.exit(1)

if __name__ == '__main__':
    if sys.platform == 'win32':
        # 设置 Windows 的事件循环策略
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("用户中断爬虫运行")
        sys.exit(0)
    except Exception as e:
        logger.error(f"发生致命错误: {e}", exc_info=True)
        sys.exit(1)