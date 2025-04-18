import asyncio
import aiohttp
import random
import json
from pathlib import Path
from typing import Optional, List, Dict, Set
from bs4 import BeautifulSoup
import logging
from datetime import datetime
import re
import os
from src.config import CrawlerConfig, BoardConfig
from src.utils import get_safe_filename, save_json_file
from src.state import StateManager, PostState
import aiofiles
from urllib.parse import urljoin, urlparse

logger = logging.getLogger(__name__)

class Crawler:
    """异步网络爬虫"""
    
    def __init__(self, config: CrawlerConfig):
        """初始化爬虫
        
        Args:
            config: 爬虫配置对象
        """
        self.config = config
        self.session: Optional[aiohttp.ClientSession] = None
        self.semaphore: Optional[asyncio.Semaphore] = None
        self.crawled_urls: Set[str] = set()
        self.board_posts: Dict[str, int] = {board.name: 0 for board in config.boards}
        
        # 创建状态管理器
        self.state_manager = StateManager(config.output_dir / '.state')
        
        # 创建输出目录
        self.config.output_dir.mkdir(parents=True, exist_ok=True)
        if self.config.save_images:
            self.config.image_dir.mkdir(parents=True, exist_ok=True)
            
        # 设置日志
        self._setup_logging()
        
        # 加载所有版面的状态
        for board in config.boards:
            self.state_manager.load_board_state(board.name)
    
    def _setup_logging(self):
        """配置日志"""
        # 创建logger
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.INFO)
        
        # 如果logger已经有处理器，就不再添加
        if not self.logger.handlers:
            # 创建文件处理器，明确指定UTF-8编码
            file_handler = logging.FileHandler(self.config.output_dir / 'crawler.log', encoding='utf-8')
            file_handler.setLevel(logging.INFO)
            
            # 创建控制台处理器
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.INFO)
            
            # 创建格式器
            formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
            file_handler.setFormatter(formatter)
            console_handler.setFormatter(formatter)
            
            # 添加处理器到logger
            self.logger.addHandler(file_handler)
            self.logger.addHandler(console_handler)
    
    async def __aenter__(self):
        """异步上下文管理器入口"""
        self.session = aiohttp.ClientSession()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        if self.session:
            await self.session.close()
            
    async def start(self):
        """启动爬虫"""
        self.semaphore = asyncio.Semaphore(self.config.max_concurrent_tasks)
        
        try:
            # 为每个版面创建一个任务
            tasks = [self.crawl_board(board) for board in self.config.boards]
            await asyncio.gather(*tasks)
        finally:
            await self.close()
    
    async def close(self):
        """关闭爬虫，释放资源"""
        if self.session:
            await self.session.close()
    
    def _get_headers(self) -> Dict[str, str]:
        """获取随机User-Agent的请求头"""
        return {
            'User-Agent': random.choice(self.config.user_agents),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2',
        }
    
    async def _fetch_page(self, url: str) -> Optional[str]:
        """获取页面内容
        
        Args:
            url: 要获取的页面URL
            
        Returns:
            页面HTML内容，失败返回None
        """
        for attempt in range(self.config.max_retries):
            try:
                async with self.semaphore:
                    async with self.session.get(
                        url,
                        headers=self._get_headers(),
                        proxy=random.choice(self.config.proxies) if self.config.proxies else None,
                        timeout=self.config.timeout
                    ) as response:
                        if response.status == 200:
                            # 获取原始字节数据
                            content = await response.read()
                            
                            # 尝试不同的编码
                            encodings = ['utf-8', 'gbk', 'gb2312', 'gb18030', 'big5']
                            for encoding in encodings:
                                try:
                                    return content.decode(encoding)
                                except UnicodeDecodeError:
                                    continue
                            
                            # 如果所有编码都失败，使用chardet检测
                            try:
                                import chardet
                                detected = chardet.detect(content)
                                if detected and detected['encoding']:
                                    return content.decode(detected['encoding'])
                            except ImportError:
                                self.logger.warning("chardet未安装，无法自动检测编码")
                            except Exception as e:
                                self.logger.error(f"编码检测失败: {e}")
                            
                            # 最后尝试使用errors='ignore'
                            return content.decode('utf-8', errors='ignore')
                        else:
                            self.logger.warning(f"获取页面失败: {url}, 状态码: {response.status}")
                            
            except asyncio.TimeoutError:
                self.logger.warning(f"请求超时: {url}, 尝试次数: {attempt + 1}")
            except Exception as e:
                self.logger.error(f"请求异常: {url}, 错误: {e}, 尝试次数: {attempt + 1}")
            
            if attempt < self.config.max_retries - 1:
                await asyncio.sleep(self.config.retry_delay)
        
        return None
    
    async def crawl_board(self, board: BoardConfig):
        """爬取版面
        
        Args:
            board: 版面配置
        """
        self.logger.info(f"开始爬取版面: {board.name}")
        page = 1
        
        while True:
            # 检查是否达到最大页数限制
            if board.max_pages and page > board.max_pages:
                self.logger.info(f"版面 {board.name} 达到最大页数限制: {board.max_pages}")
                break
                
            # 检查是否达到最大帖子数限制
            if board.max_posts and self.board_posts[board.name] >= board.max_posts:
                self.logger.info(f"版面 {board.name} 达到最大帖子数限制: {board.max_posts}")
                break
                
            url = f"{board.url}?p={page}"
            self.logger.info(f"爬取页面: {url}")
            
            html = await self._fetch_page(url)
            if not html:
                self.logger.error(f"获取页面失败: {url}")
                break
                
            soup = BeautifulSoup(html, 'html.parser')
            posts = self._parse_list_page(soup)
            
            if not posts:
                self.logger.info(f"版面 {board.name} 页面 {page} 没有找到帖子，可能是最后一页")
                break
                
            self.logger.info(f"找到 {len(posts)} 个帖子")
            
            # 处理每个帖子
            tasks = []
            for post in posts:
                # 检查是否达到最大帖子数限制
                if board.max_posts and self.board_posts[board.name] >= board.max_posts:
                    break
                    
                # 获取帖子ID
                post_id = self._extract_post_id(post['url'])
                if not post_id:
                    self.logger.warning(f"无法提取帖子ID: {post['url']}")
                    continue
                    
                # 检查帖子状态
                state = self.state_manager.get_post_state(board.name, post_id)
                if state == PostState.COMPLETED:
                    self.logger.debug(f"帖子已爬取: {post['url']}")
                    continue
                    
                # 创建处理帖子的任务
                task = asyncio.create_task(self._process_post(board.name, post_id, post))
                tasks.append(task)
                
                # 更新已爬取的帖子数
                self.board_posts[board.name] += 1
            
            if tasks:
                # 等待所有任务完成
                await asyncio.gather(*tasks)
            
            # 如果没有找到新的帖子，说明已经爬取完成
            if not tasks:
                self.logger.info(f"版面 {board.name} 页面 {page} 没有新帖子需要爬取")
                break
                
            page += 1
            
            # 在页面之间添加延迟
            await asyncio.sleep(self.config.retry_delay)
    
    def _parse_list_page(self, soup: BeautifulSoup) -> List[Dict]:
        """解析列表页
        
        Args:
            soup: BeautifulSoup对象
            
        Returns:
            帖子信息列表
        """
        posts = []
        try:
            # 获取所有帖子行
            rows = soup.select('table.board-list tr')
            
            for row in rows:
                # 跳过表头和置顶帖
                if not row.select_one('td.title') or 'top' in row.get('class', []):
                    continue
                    
                try:
                    # 获取标题和链接
                    title_elem = row.select_one('td.title a')
                    if not title_elem:
                        continue
                        
                    title = title_elem.get_text(strip=True)
                    url = title_elem['href']
                    if url.startswith('/'):
                        url = urljoin(self.config.base_url, url)
                    
                    # 获取作者
                    author_elem = row.select_one('td.author')
                    author = author_elem.get_text(strip=True) if author_elem else '匿名'
                    
                    # 获取发布时间
                    time_elem = row.select_one('td.time')
                    post_time = time_elem.get_text(strip=True) if time_elem else ''
                    
                    posts.append({
                        'title': title,
                        'url': url,
                        'author': author,
                        'time': post_time
                    })
                    
                except Exception as e:
                    self.logger.error(f"解析帖子行失败: {e}", exc_info=True)
                    continue
                    
        except Exception as e:
            self.logger.error(f"解析列表页失败: {e}", exc_info=True)
            
        return posts
    
    def _parse_detail_page(self, soup: BeautifulSoup) -> Dict:
        """解析详情页
        
        Args:
            soup: BeautifulSoup对象
            
        Returns:
            帖子详情信息
        """
        try:
            # 获取帖子标题
            title_elem = soup.select_one('h3.post-title')
            title = title_elem.get_text(strip=True) if title_elem else '无标题'
            self.logger.info(f"找到帖子标题: {title}")
            
            # 获取帖子内容
            content_elem = soup.select_one('div.post-content')
            if not content_elem:
                self.logger.error("未找到帖子内容元素")
                return {}
                
            # 获取所有图片链接
            images = []
            img_elems = content_elem.select('img')
            for img in img_elems:
                src = img.get('src', '')
                if src:
                    if src.startswith('//'):
                        src = 'https:' + src
                    elif src.startswith('/'):
                        src = self.config.base_url + src
                    images.append(src)
                    
            self.logger.info(f"找到 {len(images)} 张图片")
            
            # 获取纯文本内容
            content = content_elem.get_text(strip=True)
            
            # 获取作者信息
            author_elem = soup.select_one('div.post-meta span.author')
            author = author_elem.get_text(strip=True) if author_elem else '匿名'
            
            # 获取发布时间
            time_elem = soup.select_one('div.post-meta span.time')
            post_time = time_elem.get_text(strip=True) if time_elem else ''
            
            return {
                'title': title,
                'content': content,
                'author': author,
                'date': post_time,
                'images': images
            }
            
        except Exception as e:
            self.logger.error(f"解析详情页失败: {e}", exc_info=True)
            return {}
    
    async def _save_post(self, board_name: str, post: Dict, content: Dict):
        """保存帖子内容
        
        Args:
            board_name: 版面名称
            post: 帖子基本信息
            content: 帖子详细内容
        """
        try:
            # 创建版面目录
            board_dir = self.config.output_dir / board_name / 'posts'
            board_dir.mkdir(parents=True, exist_ok=True)
            
            # 生成安全的文件名
            filename = self._get_safe_filename(content.get('title', post.get('title', 'untitled')))
            
            # 保存元数据
            post_data = {
                'url': post['url'],
                'title': content.get('title', post.get('title', '')),
                'author': content.get('author', post.get('author', '')),
                'date': content.get('date', post.get('time', '')),
                'crawl_time': datetime.now().isoformat(),
            }
            
            json_path = board_dir / f"{filename}.json"
            await save_json_file(json_path, post_data)
            
            # 准备Markdown内容
            md_content = [
                f"# {post_data['title']}",
                "",
                f"作者: {post_data['author']}",
                f"发布时间: {post_data['date']}",
                f"原文链接: {post['url']}",
                "",
                "---",
                "",
                content.get('content', ''),
                "",
            ]
            
            # 如果有图片，创建图片目录并下载
            if content.get('images') and self.config.save_images:
                image_dir = self.config.image_dir / filename
                image_dir.mkdir(parents=True, exist_ok=True)
                
                for i, img_url in enumerate(content['images'], 1):
                    try:
                        # 下载图片
                        async with self.session.get(img_url, headers=self._get_headers()) as response:
                            if response.status == 200:
                                # 获取文件扩展名
                                ext = os.path.splitext(urlparse(img_url).path)[1] or '.jpg'
                                if not ext.startswith('.'):
                                    ext = '.' + ext
                                    
                                # 保存图片
                                image_path = image_dir / f"image_{i}{ext}"
                                async with aiofiles.open(image_path, 'wb') as f:
                                    await f.write(await response.read())
                                    
                                # 添加图片链接到Markdown
                                relative_path = os.path.relpath(image_path, board_dir)
                                md_content.append(f"![图片{i}]({relative_path})")
                                md_content.append("")
                                
                    except Exception as e:
                        self.logger.error(f"下载图片失败 {img_url}: {e}")
            
            # 保存Markdown文件
            md_path = board_dir / f"{filename}.md"
            async with aiofiles.open(md_path, 'w', encoding='utf-8') as f:
                await f.write('\n'.join(md_content))
                
            self.logger.info(f"保存帖子成功: {md_path}")
            
        except Exception as e:
            self.logger.error(f"保存帖子失败: {e}", exc_info=True)
    
    @staticmethod
    def _get_safe_filename(filename: str) -> str:
        """生成安全的文件名
        
        Args:
            filename: 原始文件名
            
        Returns:
            安全的文件名
        """
        # 移除非法字符
        filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
        # 限制长度
        return filename[:100]
    
    async def _process_post(self, board_name: str, post_id: str, post_info: Dict):
        """处理单个帖子
        
        Args:
            board_name: 版面名称
            post_id: 帖子ID
            post_info: 帖子基本信息
        """
        try:
            # 更新帖子状态为处理中
            self.state_manager.set_post_state(board_name, post_id, PostState.PROCESSING)
            
            # 获取帖子详情页
            html = await self._fetch_page(post_info['url'])
            if not html:
                self.logger.error(f"获取帖子详情页失败: {post_info['url']}")
                self.state_manager.set_post_state(board_name, post_id, PostState.FAILED)
                return
                
            # 解析详情页
            soup = BeautifulSoup(html, 'html.parser')
            content = self._parse_detail_page(soup)
            
            if not content:
                self.logger.error(f"解析帖子详情页失败: {post_info['url']}")
                self.state_manager.set_post_state(board_name, post_id, PostState.FAILED)
                return
                
            # 保存帖子
            await self._save_post(board_name, post_info, content)
            
            # 更新帖子状态为完成
            self.state_manager.set_post_state(board_name, post_id, PostState.COMPLETED)
            self.logger.info(f"帖子处理完成: {post_info['url']}")
            
        except Exception as e:
            self.logger.error(f"处理帖子失败: {post_info['url']}, 错误: {e}", exc_info=True)
            self.state_manager.set_post_state(board_name, post_id, PostState.FAILED)
    
    def _extract_post_id(self, url: str) -> str:
        """从URL中提取帖子ID
        
        Args:
            url: 帖子URL
            
        Returns:
            帖子ID
        """
        try:
            # 尝试从URL中提取帖子ID
            match = re.search(r'/article/(\w+)/?', url)
            if match:
                return match.group(1)
        except Exception as e:
            self.logger.error(f"提取帖子ID失败: {url}, 错误: {e}")
        return ''
    
    def _extract_board_name(self, url: str) -> str:
        """从URL中提取版面名称
        
        Args:
            url: 帖子URL
            
        Returns:
            版面名称
        """
        try:
            # 尝试从URL中提取版面名称
            match = re.search(r'/board/(\w+)/?', url)
            if match:
                return match.group(1)
        except Exception as e:
            self.logger.error(f"提取版面名称失败: {url}, 错误: {e}")
        return ''