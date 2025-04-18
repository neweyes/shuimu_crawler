import json
from pathlib import Path
from typing import Dict, Set, Optional, List, Any
from dataclasses import dataclass, field, asdict
import logging
from enum import Enum
from datetime import datetime

logger = logging.getLogger(__name__)

class PostState(Enum):
    """帖子的状态枚举"""
    PENDING = "pending"      # 等待下载
    DOWNLOADING = "downloading"  # 正在下载
    COMPLETED = "completed"  # 下载完成
    FAILED = "failed"        # 下载失败
    RETRY = "retry"         # 需要重试

@dataclass
class PostInfo:
    """帖子信息"""
    url: str
    title: str
    state: PostState = PostState.PENDING
    retry_count: int = 0
    last_attempt: Optional[str] = None
    error_message: Optional[str] = None
    downloaded_images: List[str] = field(default_factory=list)
    failed_images: List[str] = field(default_factory=list)

@dataclass
class BoardState:
    """版面状态"""
    name: str
    last_page: int = 1
    posts: Dict[str, PostInfo] = field(default_factory=dict)

@dataclass
class PostState:
    """帖子状态"""
    url: str
    title: str
    downloaded: bool = False
    images_downloaded: bool = False
    last_attempt: str = field(default_factory=lambda: datetime.now().isoformat())
    retry_count: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'url': self.url,
            'title': self.title,
            'downloaded': self.downloaded,
            'images_downloaded': self.images_downloaded,
            'last_attempt': self.last_attempt,
            'retry_count': self.retry_count
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PostState':
        return cls(**data)

class StateManager:
    """状态管理器"""
    
    def __init__(self, state_dir: Path):
        """初始化状态管理器
        
        Args:
            state_dir: 状态文件保存目录
        """
        self.state_dir = state_dir
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.boards: Dict[str, BoardState] = {}
    
    def _get_board_file(self, board_name: str) -> Path:
        """获取版面状态文件路径"""
        return self.state_dir / f"{board_name}.json"
    
    def load_board_state(self, board_name: str) -> BoardState:
        """加载版面状态"""
        state_file = self._get_board_file(board_name)
        if state_file.exists():
            with state_file.open('r', encoding='utf-8') as f:
                data = json.load(f)
                board_state = BoardState(name=board_name)
                board_state.last_page = data.get('last_page', 1)
                
                for post_id, post_data in data.get('posts', {}).items():
                    board_state.posts[post_id] = PostInfo(
                        url=post_data['url'],
                        title=post_data['title'],
                        state=PostState(post_data['state']),
                        retry_count=post_data['retry_count'],
                        last_attempt=post_data.get('last_attempt'),
                        error_message=post_data.get('error_message'),
                        downloaded_images=post_data.get('downloaded_images', []),
                        failed_images=post_data.get('failed_images', [])
                    )
                return board_state
        return BoardState(name=board_name)
    
    def save_board_state(self, board_state: BoardState):
        """保存版面状态"""
        state_file = self._get_board_file(board_state.name)
        data = {
            'last_page': board_state.last_page,
            'posts': {
                post_id: {
                    'url': post.url,
                    'title': post.title,
                    'state': post.state.value,
                    'retry_count': post.retry_count,
                    'last_attempt': post.last_attempt,
                    'error_message': post.error_message,
                    'downloaded_images': post.downloaded_images,
                    'failed_images': post.failed_images
                }
                for post_id, post in board_state.posts.items()
            }
        }
        with state_file.open('w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def get_board_state(self, board_name: str) -> BoardState:
        """获取版面状态，如果不存在则加载"""
        if board_name not in self.boards:
            self.boards[board_name] = self.load_board_state(board_name)
        return self.boards[board_name]
    
    def update_post_state(self, board_name: str, post_id: str, 
                         state: PostState, error: str = None):
        """更新帖子状态"""
        board_state = self.get_board_state(board_name)
        if post_id in board_state.posts:
            post = board_state.posts[post_id]
            post.state = state
            post.last_attempt = datetime.now().isoformat()
            if error:
                post.error_message = error
                post.retry_count += 1
            self.save_board_state(board_state)
    
    def add_post(self, board_name: str, post_id: str, url: str, title: str):
        """添加新帖子"""
        board_state = self.get_board_state(board_name)
        if post_id not in board_state.posts:
            board_state.posts[post_id] = PostInfo(url=url, title=title)
            self.save_board_state(board_state)
    
    def should_process_post(self, board_name: str, post_id: str, 
                          max_retries: int) -> bool:
        """判断是否应该处理帖子"""
        board_state = self.get_board_state(board_name)
        if post_id not in board_state.posts:
            return True
            
        post = board_state.posts[post_id]
        if post.state in [PostState.COMPLETED]:
            return False
            
        if post.state in [PostState.FAILED, PostState.RETRY]:
            return post.retry_count < max_retries
            
        return True
    
    def add_downloaded_image(self, board_name: str, post_id: str, 
                           image_path: str):
        """记录已下载的图片"""
        board_state = self.get_board_state(board_name)
        if post_id in board_state.posts:
            post = board_state.posts[post_id]
            if image_path not in post.downloaded_images:
                post.downloaded_images.append(image_path)
                self.save_board_state(board_state)
    
    def add_failed_image(self, board_name: str, post_id: str, 
                        image_url: str):
        """记录下载失败的图片"""
        board_state = self.get_board_state(board_name)
        if post_id in board_state.posts:
            post = board_state.posts[post_id]
            if image_url not in post.failed_images:
                post.failed_images.append(image_url)
                self.save_board_state(board_state)
    
    def get_failed_images(self, board_name: str, post_id: str) -> List[str]:
        """获取下载失败的图片列表"""
        board_state = self.get_board_state(board_name)
        if post_id in board_state.posts:
            return board_state.posts[post_id].failed_images
        return []
    
    def get_downloaded_images(self, board_name: str, post_id: str) -> List[str]:
        """获取已下载的图片列表"""
        board_state = self.get_board_state(board_name)
        if post_id in board_state.posts:
            return board_state.posts[post_id].downloaded_images
        return []

    def load_state(self) -> None:
        """加载所有版面的状态"""
        for state_file in self.state_dir.glob('*.json'):
            board_name = state_file.stem
            self.boards[board_name] = self.load_board_state(board_name)

    def save_state(self) -> None:
        """保存所有版面的状态"""
        for board_state in self.boards.values():
            self.save_board_state(board_state)

    def add_post(self, url: str, title: str) -> None:
        """添加新帖子"""
        post_state = PostState(url=url, title=title)
        self.posts[url] = post_state

    def mark_post_downloaded(self, url: str) -> None:
        """标记帖子已下载"""
        if url in self.posts:
            self.posts[url].downloaded = True

    def mark_images_downloaded(self, url: str) -> None:
        """标记帖子图片已下载"""
        if url in self.posts:
            self.posts[url].images_downloaded = True

    def increment_retry_count(self, url: str) -> None:
        """增加重试次数"""
        if url in self.posts:
            self.posts[url].retry_count += 1

    def get_unfinished_posts(self) -> Set[str]:
        """获取未完成的帖子URL列表"""
        return {url for url, state in self.posts.items() 
                if not state.downloaded or not state.images_downloaded}

    def should_retry(self, url: str, max_retries: int) -> bool:
        """判断是否应该重试"""
        if url not in self.posts:
            return True
        return self.posts[url].retry_count < max_retries