import logging
import os
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict
import json

# 基础配置
BASE_URL = 'https://www.newsmth.net'
BOARD_URL = 'https://www.newsmth.net/nForum/board/OurEstate'

# 路径配置
BASE_DIR = Path('./shuimu_data')
IMAGES_DIR = BASE_DIR / 'images'
STATE_DIR = BASE_DIR / '.state'

# 创建必要的目录
for directory in [BASE_DIR, IMAGES_DIR, STATE_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

# 爬虫配置
MAX_CONCURRENCY = 50
MAX_RETRIES = 2
RETRY_DELAY = 0.5
CHUNK_SIZE = 16384
TIMEOUT = 10

# 网络请求配置
USER_AGENTS = [
    # Googlebot
    'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)',
    'Mozilla/5.0 (Linux; Android 6.0.1; Nexus 5X Build/MMB29P) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Mobile Safari/537.36 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)',
    # Bingbot
    'Mozilla/5.0 (compatible; bingbot/2.0; +http://www.bing.com/bingbot.htm)',
    # Baiduspider
    'Mozilla/5.0 (compatible; Baiduspider/2.0; +http://www.baidu.com/search/spider.html)',
    # Sogou Spider
    'Sogou web spider/4.0(+http://www.sogou.com/docs/help/webmasters.htm#07)',
    # 360Spider
    'Mozilla/5.0 (compatible; 360Spider/1.0; +http://www.so.com/help/help_3_2.html)'
]

# 日志配置
LOG_FORMAT = '%(asctime)s - %(levelname)s - %(message)s'
LOG_LEVEL = logging.INFO

# 初始化日志
logging.basicConfig(
    level=LOG_LEVEL,
    format=LOG_FORMAT
)
logger = logging.getLogger(__name__)

@dataclass
class BoardConfig:
    """版面配置"""
    name: str  # 版面名称
    url: str   # 版面URL
    max_pages: Optional[int] = None  # 最大爬取页数
    max_posts: Optional[int] = None  # 最大爬取帖子数

    def __post_init__(self):
        if not self.url.startswith(('http://', 'https://')):
            raise ValueError(f"Invalid board URL for {self.name}: {self.url}")
        if self.max_pages is not None and self.max_pages < 1:
            raise ValueError(f"max_pages must be at least 1 for board {self.name}")
        if self.max_posts is not None and self.max_posts < 1:
            raise ValueError(f"max_posts must be at least 1 for board {self.name}")

@dataclass
class CrawlerConfig:
    """爬虫配置"""
    base_url: str
    output_dir: Path
    image_dir: Path
    boards: List[BoardConfig]
    max_concurrent_tasks: int = 5
    max_retries: int = 3
    retry_delay: float = 1.0
    timeout: float = 30.0
    save_images: bool = True  # 是否保存图片
    user_agents: List[str] = field(default_factory=lambda: [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    ])
    proxies: Optional[Dict[str, str]] = None

    def __post_init__(self):
        # 确保路径是 Path 对象
        if isinstance(self.output_dir, str):
            self.output_dir = Path(self.output_dir)
        if isinstance(self.image_dir, str):
            self.image_dir = Path(self.image_dir)

        # 验证 URL
        if not self.base_url.startswith(('http://', 'https://')):
            raise ValueError("base_url must start with http:// or https://")

        # 验证数值
        if self.max_concurrent_tasks < 1:
            raise ValueError("max_concurrent_tasks must be at least 1")
        if self.max_retries < 0:
            raise ValueError("max_retries must be non-negative")
        if self.retry_delay < 0:
            raise ValueError("retry_delay must be non-negative")
        if self.timeout <= 0:
            raise ValueError("timeout must be positive")

        # 创建每个板块的输出目录
        for board in self.boards:
            board_dir = self.output_dir / board.name
            board_dir.mkdir(parents=True, exist_ok=True)
            board_image_dir = self.image_dir / board.name
            board_image_dir.mkdir(parents=True, exist_ok=True)

    @classmethod
    def from_json(cls, json_path: str) -> 'CrawlerConfig':
        """从 JSON 文件加载配置"""
        with open(json_path, 'r', encoding='utf-8') as f:
            config_dict = json.load(f)
            
        # 处理板块配置
        boards = [BoardConfig(**board_data) for board_data in config_dict.pop('boards', [])]
        config_dict['boards'] = boards
            
        return cls(**config_dict)

    def to_json(self, json_path: str) -> None:
        """将配置保存到 JSON 文件"""
        config_dict = {
            'base_url': self.base_url,
            'output_dir': str(self.output_dir),
            'image_dir': str(self.image_dir),
            'max_concurrent_tasks': self.max_concurrent_tasks,
            'max_retries': self.max_retries,
            'retry_delay': self.retry_delay,
            'timeout': self.timeout,
            'save_images': self.save_images,
            'user_agents': self.user_agents,
            'proxies': self.proxies,
            'boards': [
                {
                    'name': board.name,
                    'url': board.url,
                    'max_pages': board.max_pages,
                    'max_posts': board.max_posts
                }
                for board in self.boards
            ]
        }
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(config_dict, f, indent=2)