import os
import time
import asyncio
import aiohttp
from bs4 import BeautifulSoup
import re
from urllib.parse import urljoin
from typing import List, Dict, Optional, Set, Tuple
import logging
import json
from pathlib import Path
import random
from datetime import datetime

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class ShuimuCrawler:
    # 搜索引擎爬虫的User-Agent列表
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

    def __init__(self, save_dir='./data', max_concurrency=20):
        self.base_url = 'https://www.newsmth.net'
        self.board_url = 'https://www.newsmth.net/nForum/board/OurEstate'
        self.save_dir = save_dir
        self.max_concurrency = max_concurrency
        self.semaphore = asyncio.Semaphore(max_concurrency)
        self.cookies = {}  # 存储cookies
        
        # 创建robots.txt解析器
        self.robots_parser = None
        
        # 创建保存目录
        if not os.path.exists(save_dir):
            os.makedirs(save_dir)
            
        # 创建图片保存目录
        self.images_dir = os.path.join(save_dir, 'images')
        if not os.path.exists(self.images_dir):
            os.makedirs(self.images_dir)
            
        # 创建状态目录
        self.state_dir = os.path.join(save_dir, '.state')
        if not os.path.exists(self.state_dir):
            os.makedirs(self.state_dir)
            
        # 初始化已下载和失败的记录
        self.downloaded_files = self._load_downloaded_files()
        self.failed_posts = self._load_failed_items('failed_posts.json')
        self.failed_images = self._load_failed_items('failed_images.json')
        
        logger.info(f"Found {len(self.downloaded_files)} downloaded files")
        logger.info(f"Found {len(self.failed_posts)} failed posts")
        logger.info(f"Found {len(self.failed_images)} failed images")

    def _load_downloaded_files(self) -> Set[str]:
        """加载已下载的文件列表"""
        downloaded = set()
        if os.path.exists(self.save_dir):
            for filename in os.listdir(self.save_dir):
                if filename.endswith('.md'):
                    # 去掉.md后缀，获取原始标题
                    title = filename[:-3]
                    downloaded.add(title)
        return downloaded

    def _load_failed_items(self, filename: str) -> Dict:
        """加载失败的项目记录"""
        filepath = os.path.join(self.state_dir, filename)
        if os.path.exists(filepath):
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading {filename}: {str(e)}")
                return {}
        return {}

    def _save_failed_items(self, items: Dict, filename: str):
        """保存失败的项目记录"""
        filepath = os.path.join(self.state_dir, filename)
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(items, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Error saving {filename}: {str(e)}")

    def _add_failed_post(self, post: Dict, error: str):
        """添加失败的帖子记录"""
        self.failed_posts[post['url']] = {
            'post': post,
            'error': error,
            'timestamp': datetime.now().isoformat()
        }
        self._save_failed_items(self.failed_posts, 'failed_posts.json')

    def _add_failed_image(self, image_url: str, post_id: str, error: str):
        """添加失败的图片记录"""
        self.failed_images[image_url] = {
            'url': image_url,
            'post_id': post_id,
            'error': error,
            'timestamp': datetime.now().isoformat()
        }
        self._save_failed_items(self.failed_images, 'failed_images.json')

    def _remove_failed_post(self, url: str):
        """移除已成功的帖子记录"""
        if url in self.failed_posts:
            del self.failed_posts[url]
            self._save_failed_items(self.failed_posts, 'failed_posts.json')

    def _remove_failed_image(self, url: str):
        """移除已成功的图片记录"""
        if url in self.failed_images:
            del self.failed_images[url]
            self._save_failed_items(self.failed_images, 'failed_images.json')

    def _get_random_headers(self) -> Dict[str, str]:
        """获取随机的搜索引擎爬虫请求头"""
        # 获取随机User-Agent
        user_agent = random.choice(self.USER_AGENTS)
        
        # 搜索引擎爬虫的特殊请求头
        headers = {
            'User-Agent': user_agent,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5,zh-CN;q=0.3',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'From': 'googlebot(at)googlebot.com',  # 搜索引擎联系方式
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache'
        }
        
        # 如果是Googlebot，添加特殊的Chrome请求头
        if 'Googlebot' in user_agent:
            headers.update({
                'X-Robots-Tag': 'noarchive',  # 表明遵守robots规则
                'AdsBot-Google': '(+http://www.google.com/adsbot.html)'
            })
        
        # 添加cookies如果有的话
        if self.cookies:
            headers['Cookie'] = '; '.join([f'{k}={v}' for k, v in self.cookies.items()])
            
        return headers

    async def _init_session(self, session: aiohttp.ClientSession):
        """初始化会话，访问主页获取必要的cookies和robots.txt"""
        try:
            # 首先获取robots.txt
            robots_url = urljoin(self.base_url, '/robots.txt')
            async with session.get(robots_url, headers=self._get_random_headers()) as response:
                if response.status == 200:
                    logger.info("Successfully fetched robots.txt")
                else:
                    logger.warning("Could not fetch robots.txt")
            
            # 访问主页获取初始cookies
            async with session.get(self.base_url, headers=self._get_random_headers()) as response:
                self.cookies.update(response.cookies)
                await response.text()
            
            # 访问版面获取额外cookies
            async with session.get(self.board_url, headers=self._get_random_headers()) as response:
                self.cookies.update(response.cookies)
                await response.text()
                
        except Exception as e:
            logger.error(f"Error initializing session: {str(e)}")

    async def get_page_content(self, session: aiohttp.ClientSession, url: str) -> Optional[str]:
        """获取页面内容"""
        try:
            async with self.semaphore:  # 使用信号量限制并发
                headers = self._get_random_headers()
                timeout = aiohttp.ClientTimeout(total=10)  # 减少超时时间到10秒
                async with session.get(url, headers=headers, timeout=timeout) as response:
                    self.cookies.update(response.cookies)
                    content = await response.text(encoding='gbk', errors='ignore')
                    return content
        except Exception as e:
            logger.error(f"Error fetching {url}: {str(e)}")
            return None

    async def download_image(self, session: aiohttp.ClientSession, image_url: str, post_id: str) -> Optional[str]:
        """下载图片"""
        max_retries = 2  # 减少重试次数
        retry_delay = 0.5  # 减少重试延迟
        
        try:
            for attempt in range(max_retries):
                try:
                    if not image_url.startswith(('http://', 'https://')):
                        image_url = urljoin(self.base_url, image_url)

                    post_images_dir = os.path.join(self.images_dir, post_id)
                    if not os.path.exists(post_images_dir):
                        os.makedirs(post_images_dir)

                    image_filename = os.path.basename(image_url)
                    if not image_filename or '.' not in image_filename:
                        image_filename = f"image_{int(time.time() * 1000)}.jpg"
                    
                    image_path = os.path.join(post_images_dir, image_filename)
                    
                    if os.path.exists(image_path):
                        self._remove_failed_image(image_url)
                        return os.path.relpath(image_path, self.save_dir)

                    async with self.semaphore:
                        timeout = aiohttp.ClientTimeout(total=10)  # 减少超时时间到10秒
                        headers = self._get_random_headers()
                        headers['Accept'] = 'image/webp,image/apng,image/*,*/*;q=0.8'
                        
                        async with session.get(image_url, headers=headers, timeout=timeout) as response:
                            if response.status == 200:
                                image_data = bytearray()
                                chunk_size = 16384  # 增加到16KB chunks
                                
                                async for chunk in response.content.iter_chunked(chunk_size):
                                    image_data.extend(chunk)
                                
                                content_length = response.headers.get('Content-Length')
                                if content_length and len(image_data) != int(content_length):
                                    raise aiohttp.ClientError("Incomplete download: size mismatch")
                                
                                with open(image_path, 'wb') as f:
                                    f.write(image_data)
                                logger.info(f"Downloaded image: {image_filename}")
                                self._remove_failed_image(image_url)
                                return os.path.relpath(image_path, self.save_dir)
                            else:
                                if attempt < max_retries - 1:
                                    continue
                                error_msg = f"Failed to download image, status: {response.status}"
                                self._add_failed_image(image_url, post_id, error_msg)
                                return None

                except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                    if attempt < max_retries - 1:
                        await asyncio.sleep(retry_delay)
                        continue
                    error_msg = f"Failed after {max_retries} attempts: {str(e)}"
                    self._add_failed_image(image_url, post_id, error_msg)
                    return None

        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            self._add_failed_image(image_url, post_id, error_msg)
            return None
        
        return None

    async def parse_list_page(self, session: aiohttp.ClientSession, page_num: int) -> List[Dict]:
        """解析列表页"""
        url = f'{self.board_url}?p={page_num}'
        content = await self.get_page_content(session, url)
        if not content:
            return []

        posts = []
        soup = BeautifulSoup(content, 'lxml')
        
        # 查找所有帖子行
        table = soup.find('table', class_='board-list')
        if table:
            for tr in table.find_all('tr'):
                try:
                    # 查找标题单元格（第2个td）
                    tds = tr.find_all('td')
                    if len(tds) >= 3:
                        title_td = tds[1]  # 第2个td是标题
                        if title_td and title_td.a:
                            title = title_td.a.text.strip()
                            link = title_td.a['href']
                            if title and link:
                                # 构建完整的帖子URL
                                full_link = urljoin(self.base_url, link)
                                # 提取帖子ID
                                post_id = link.split('/')[-1]
                                # 检查是否已下载
                                safe_title = self._get_safe_filename(title)
                                if safe_title not in self.downloaded_files:
                                    posts.append({
                                        'title': title,
                                        'url': full_link,
                                        'post_id': post_id
                                    })
                                    logger.info(f"Found new post: {title}")
                                else:
                                    logger.debug(f"Skip downloaded post: {title}")
                except Exception as e:
                    logger.error(f"Error parsing post row: {str(e)}")
                    continue
        else:
            logger.warning("Table with class 'board-list' not found!")
        
        return posts

    async def parse_detail_page(self, session: aiohttp.ClientSession, url: str, post_id: str) -> Optional[Tuple[str, List[str]]]:
        """解析详情页，返回内容和图片URL列表"""
        content = await self.get_page_content(session, url)
        if not content:
            return None

        try:
            soup = BeautifulSoup(content, 'lxml')
            tables = soup.find_all('table')
            
            for table in tables:
                rows = table.find_all('tr')
                if len(rows) >= 2:
                    cells = rows[1].find_all('td')
                    if len(cells) >= 2:
                        content_cell = cells[1]
                        if content_cell:
                            # 提取图片URL并保存位置信息
                            images = []
                            img_tags = content_cell.find_all('img')
                            for i, img in enumerate(img_tags):
                                img_url = img.get('src')
                                if img_url:
                                    # 确保图片URL是完整的
                                    if not img_url.startswith(('http://', 'https://')):
                                        img_url = urljoin(self.base_url, img_url)

                                    images.append(img_url)
                                    # 使用特殊标记替换图片标签
                                    img.replace_with(f'__IMG_PLACEHOLDER_{i}__')
                            
                            if not images:
                                logger.info(f"No valid images found in post {post_id}")
                            
                            # 获取文本内容，保持原始格式
                            text_parts = []
                            for element in content_cell.descendants:
                                if isinstance(element, str) and element.strip():
                                    text_parts.append(element.strip())
                                elif element.name == 'br' or element.name == 'p':
                                    text_parts.append('\n')
                            
                            # 合并文本，保持段落格式
                            content_text = ' '.join(text_parts)
                            # 规范化段落（删除多余空行，但保留段落间的空行）
                            paragraphs = [p.strip() for p in content_text.split('\n')]
                            cleaned_paragraphs = []
                            for p in paragraphs:
                                if p:  # 如果段落不为空
                                    cleaned_paragraphs.append(p)
                                elif cleaned_paragraphs and cleaned_paragraphs[-1] != '':
                                    # 在非空段落之间添加空行
                                    cleaned_paragraphs.append('')
                            
                            cleaned_content = '\n\n'.join(p for p in cleaned_paragraphs if p or cleaned_paragraphs[-1] != '')
                            return cleaned_content, images
            
            logger.warning("No suitable content found in any table!")
            return None
            
        except Exception as e:
            logger.error(f"Error parsing article content: {str(e)}")
            return None

    async def save_to_file(self, title: str, content: str, image_paths: List[str]):
        """保存内容到Markdown文件"""
        safe_title = self._get_safe_filename(title)
        filename = os.path.join(self.save_dir, f"{safe_title}.md")
        
        try:
            # 检查图片是否真的存在
            valid_image_paths = []
            for image_path in image_paths:
                if image_path and os.path.exists(os.path.join(self.save_dir, image_path)):
                    valid_image_paths.append(image_path)
                else:
                    logger.warning(f"Image file not found: {image_path}")
            
            # 构建Markdown内容
            markdown_content = f"# {title}\n\n"
            
            # 替换内容中的图片占位符为实际的Markdown图片
            processed_content = content
            for i, image_path in enumerate(valid_image_paths):
                if image_path:
                    # 替换占位符为markdown格式的图片
                    placeholder = f'__IMG_PLACEHOLDER_{i}__'
                    markdown_image = f'\n![图片{i+1}]({image_path})\n'
                    processed_content = processed_content.replace(placeholder, markdown_image)
            
            # 添加处理后的内容
            markdown_content += processed_content
            
            # 保存文件
            async with asyncio.Lock():  # 使用锁来保护文件写入
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(markdown_content)
                logger.info(f"Saved: {filename} with {len(valid_image_paths)} images")
                # 添加到已下载集合
                self.downloaded_files.add(safe_title)
            
            # 验证文件是否正确保存
            try:
                with open(filename, 'r', encoding='utf-8') as f:
                    test_content = f.read()
                if not test_content:
                    logger.warning(f"Warning: File {filename} appears to be empty")
            except Exception as e:
                logger.warning(f"Warning: Unable to verify file content: {str(e)}")
                
        except Exception as e:
            logger.error(f"Error saving {filename}: {str(e)}")

    async def process_post(self, session: aiohttp.ClientSession, post: Dict):
        """处理单个帖子"""
        try:
            safe_title = self._get_safe_filename(post['title'])
            if safe_title not in self.downloaded_files:
                result = await self.parse_detail_page(session, post['url'], post['post_id'])
                if result:
                    content, image_urls = result
                    if image_urls:
                        logger.info(f"Found {len(image_urls)} images in post: {post['title']}")
                        # 并发下载所有图片
                        download_tasks = [
                            self.download_image(session, image_url, post['post_id'])
                            for image_url in image_urls
                        ]
                        image_paths = await asyncio.gather(*download_tasks)
                        # 过滤掉下载失败的图片（返回None的结果）
                        image_paths = [path for path in image_paths if path]
                        logger.info(f"Successfully downloaded {len(image_paths)}/{len(image_urls)} images for post: {post['title']}")
                    else:
                        image_paths = []
                        logger.info(f"No images found in post: {post['title']}")
                    
                    await self.save_to_file(post['title'], content, image_paths)
                    self._remove_failed_post(post['url'])  # 处理成功，移除失败记录
                else:
                    self._add_failed_post(post, "Failed to parse detail page")
        except Exception as e:
            self._add_failed_post(post, str(e))

    async def crawl_page(self, session: aiohttp.ClientSession, page_num: int):
        """爬取单个页面的所有帖子"""
        try:
            posts = await self.parse_list_page(session, page_num)
            if posts:
                # 并发处理所有帖子
                tasks = [self.process_post(session, post) for post in posts]
                await asyncio.gather(*tasks, return_exceptions=True)  # 添加return_exceptions=True以防止单个任务失败影响其他任务
            else:
                logger.info(f"No new posts found on page {page_num}")
        except Exception as e:
            logger.error(f"Error processing page {page_num}: {str(e)}")

    async def retry_failed_items(self, session: aiohttp.ClientSession):
        """重试失败的帖子和图片"""
        # 重试失败的帖子
        failed_posts = list(self.failed_posts.values())
        if failed_posts:
            logger.info(f"Retrying {len(failed_posts)} failed posts...")
            tasks = [self.process_post(session, failed_post['post']) for failed_post in failed_posts]
            await asyncio.gather(*tasks)

        # 重试失败的图片
        failed_images = list(self.failed_images.values())
        if failed_images:
            logger.info(f"Retrying {len(failed_images)} failed images...")
            tasks = [self.download_image(session, failed_image['url'], failed_image['post_id']) 
                    for failed_image in failed_images]
            await asyncio.gather(*tasks)

    async def crawl(self, start_page=1, end_page=1):
        """爬取指定页面范围的帖子"""
        connector = aiohttp.TCPConnector(limit=None, force_close=True)  # 移除连接数限制
        timeout = aiohttp.ClientTimeout(total=30, connect=10, sock_connect=10, sock_read=10)
        
        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            # 初始化会话
            await self._init_session(session)
            
            # 首先重试之前失败的项目
            await self.retry_failed_items(session)
            
            # 并发爬取所有页面
            tasks = []
            for page_num in range(start_page, end_page + 1):
                logger.info(f"Creating task for page {page_num}")
                tasks.append(self.crawl_page(session, page_num))
            
            # 使用gather并发执行所有任务，允许单个任务失败
            await asyncio.gather(*tasks, return_exceptions=True)

    def _get_safe_filename(self, title: str) -> str:
        """获取安全的文件名"""
        return re.sub(r'[\\/*?:"<>|]', '_', title)

def main():
    # 使用示例
    save_dir = './shuimu_data'  # 可以修改保存目录
    max_concurrency = 50  # 增加并发数以支持更多图片同时下载
    
    crawler = ShuimuCrawler(
        save_dir=save_dir,
        max_concurrency=max_concurrency
    )
    
    # 运行异步爬虫
    asyncio.run(crawler.crawl(start_page=1, end_page=2))  # 爬取1-2000页

if __name__ == '__main__':
    main() 
