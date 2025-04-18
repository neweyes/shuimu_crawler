import os
import json
import asyncio
from typing import List, Dict, Set
from datetime import datetime
from pathlib import Path

from .config import BASE_DIR, IMAGES_DIR, STATE_DIR, logger
from .utils import get_safe_filename

class StorageManager:
    def __init__(self):
        self.base_dir = BASE_DIR
        self.images_dir = IMAGES_DIR
        self.state_dir = STATE_DIR
        self.downloaded_files = self._load_downloaded_files()
        self.failed_posts = self._load_failed_items('failed_posts.json')
        self.failed_images = self._load_failed_items('failed_images.json')
        
        logger.info(f"Found {len(self.downloaded_files)} downloaded files")
        logger.info(f"Found {len(self.failed_posts)} failed posts")
        logger.info(f"Found {len(self.failed_images)} failed images")

    def _load_downloaded_files(self) -> Set[str]:
        """加载已下载的文件列表"""
        downloaded = set()
        if self.base_dir.exists():
            for filename in self.base_dir.glob('*.md'):
                title = filename.stem
                downloaded.add(title)
        return downloaded

    def _load_failed_items(self, filename: str) -> Dict:
        """加载失败的项目记录"""
        filepath = self.state_dir / filename
        if filepath.exists():
            try:
                return json.loads(filepath.read_text(encoding='utf-8'))
            except Exception as e:
                logger.error(f"Error loading {filename}: {str(e)}")
                return {}
        return {}

    def _save_failed_items(self, items: Dict, filename: str):
        """保存失败的项目记录"""
        filepath = self.state_dir / filename
        try:
            filepath.write_text(
                json.dumps(items, ensure_ascii=False, indent=2),
                encoding='utf-8'
            )
        except Exception as e:
            logger.error(f"Error saving {filename}: {str(e)}")

    def add_failed_post(self, post: Dict, error: str):
        """添加失败的帖子记录"""
        self.failed_posts[post['url']] = {
            'post': post,
            'error': error,
            'timestamp': datetime.now().isoformat()
        }
        self._save_failed_items(self.failed_posts, 'failed_posts.json')

    def add_failed_image(self, image_url: str, post_id: str, error: str):
        """添加失败的图片记录"""
        self.failed_images[image_url] = {
            'url': image_url,
            'post_id': post_id,
            'error': error,
            'timestamp': datetime.now().isoformat()
        }
        self._save_failed_items(self.failed_images, 'failed_images.json')

    def remove_failed_post(self, url: str):
        """移除已成功的帖子记录"""
        if url in self.failed_posts:
            del self.failed_posts[url]
            self._save_failed_items(self.failed_posts, 'failed_posts.json')

    def remove_failed_image(self, url: str):
        """移除已成功的图片记录"""
        if url in self.failed_images:
            del self.failed_images[url]
            self._save_failed_items(self.failed_images, 'failed_images.json')

    def get_image_path(self, post_id: str, image_url: str) -> Path:
        """获取图片保存路径"""
        post_images_dir = self.images_dir / post_id
        post_images_dir.mkdir(parents=True, exist_ok=True)
        
        image_filename = os.path.basename(image_url)
        if not image_filename or '.' not in image_filename:
            image_filename = f"image_{int(datetime.now().timestamp() * 1000)}.jpg"
            
        return post_images_dir / image_filename

    async def save_image(self, image_data: bytes, image_path: Path) -> bool:
        """保存图片文件"""
        try:
            image_path.write_bytes(image_data)
            logger.info(f"Downloaded image: {image_path.name}")
            return True
        except Exception as e:
            logger.error(f"Error saving image {image_path}: {str(e)}")
            return False

    async def save_to_file(self, title: str, content: str, image_paths: List[str]):
        """保存内容到Markdown文件"""
        safe_title = get_safe_filename(title)
        filename = self.base_dir / f"{safe_title}.md"
        
        try:
            # 检查图片是否真的存在
            valid_image_paths = []
            for image_path in image_paths:
                if image_path and (self.base_dir / image_path).exists():
                    valid_image_paths.append(image_path)
                else:
                    logger.warning(f"Image file not found: {image_path}")
            
            # 构建Markdown内容
            markdown_content = f"# {title}\n\n"
            
            # 替换图片占位符
            processed_content = content
            for i, image_path in enumerate(valid_image_paths):
                if image_path:
                    placeholder = f'__IMG_PLACEHOLDER_{i}__'
                    markdown_image = f'\n![图片{i+1}]({image_path})\n'
                    processed_content = processed_content.replace(placeholder, markdown_image)
            
            markdown_content += processed_content
            
            # 保存文件
            async with asyncio.Lock():
                filename.write_text(markdown_content, encoding='utf-8')
                logger.info(f"Saved: {filename} with {len(valid_image_paths)} images")
                self.downloaded_files.add(safe_title)
            
            # 验证文件
            if not filename.exists() or filename.stat().st_size == 0:
                logger.warning(f"Warning: File {filename} appears to be empty or not saved properly")
                
        except Exception as e:
            logger.error(f"Error saving {filename}: {str(e)}")

    def is_downloaded(self, title: str) -> bool:
        """检查文件是否已下载"""
        return get_safe_filename(title) in self.downloaded_files