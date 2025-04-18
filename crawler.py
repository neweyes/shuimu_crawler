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

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class ShuimuCrawler:
    def __init__(self, save_dir='./data', max_concurrency=5):
        self.base_url = 'https://www.newsmth.net'
        self.board_url = 'https://www.newsmth.net/nForum/board/OurEstate'
        self.save_dir = save_dir
        self.max_concurrency = max_concurrency
        self.semaphore = asyncio.Semaphore(max_concurrency)
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2',
            'Accept-Encoding': 'gzip, deflate, br',
            'Referer': 'https://www.newsmth.net/'
        }
        
        # 创建保存目录
        if not os.path.exists(save_dir):
            os.makedirs(save_dir)
            
        # 创建图片保存目录
        self.images_dir = os.path.join(save_dir, 'images')
        if not os.path.exists(self.images_dir):
            os.makedirs(self.images_dir)
            
        # 初始化已下载文件集合
        self.downloaded_files = self._load_downloaded_files()
        logger.info(f"Found {len(self.downloaded_files)} previously downloaded files")

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

    def _get_safe_filename(self, title: str) -> str:
        """获取安全的文件名"""
        return re.sub(r'[\\/*?:"<>|]', '_', title)

    async def _init_session(self, session: aiohttp.ClientSession):
        """初始化会话，访问主页获取必要的cookies"""
        try:
            async with session.get(self.base_url, headers=self.headers) as response:
                await response.text()
            async with session.get(self.board_url, headers=self.headers) as response:
                await response.text()
        except Exception as e:
            logger.error(f"Error initializing session: {str(e)}")

    async def get_page_content(self, session: aiohttp.ClientSession, url: str) -> Optional[str]:
        """获取页面内容"""
        try:
            async with self.semaphore:  # 使用信号量限制并发
                async with session.get(url, headers=self.headers) as response:
                    content = await response.text(encoding='gbk', errors='ignore')
                    return content
        except Exception as e:
            logger.error(f"Error fetching {url}: {str(e)}")
            return None

    async def download_image(self, session: aiohttp.ClientSession, image_url: str, post_id: str) -> Optional[str]:
        """下载图片"""
        try:
            # 确保图片URL是完整的
            if not image_url.startswith(('http://', 'https://')):
                image_url = urljoin(self.base_url, image_url)

            # 创建帖子专属的图片目录
            post_images_dir = os.path.join(self.images_dir, post_id)
            if not os.path.exists(post_images_dir):
                os.makedirs(post_images_dir)

            # 生成图片文件名
            image_filename = os.path.basename(image_url)
            if not image_filename or '.' not in image_filename:
                image_filename = f"image_{int(time.time() * 1000)}.jpg"
            
            image_path = os.path.join(post_images_dir, image_filename)
            
            # 检查图片是否已下载
            if os.path.exists(image_path):
                return os.path.relpath(image_path, self.save_dir)

            async with self.semaphore:
                async with session.get(image_url, headers=self.headers) as response:
                    if response.status == 200:
                        image_data = await response.read()
                        # 保存图片
                        with open(image_path, 'wb') as f:
                            f.write(image_data)
                        logger.info(f"Downloaded image: {image_filename}")
                        return os.path.relpath(image_path, self.save_dir)
                    else:
                        logger.warning(f"Failed to download image {image_url}, status: {response.status}")
                        return None
        except Exception as e:
            logger.error(f"Error downloading image {image_url}: {str(e)}")
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
                                    images.append(img_url)
                                    # 使用特殊标记替换图片标签，这个标记后面会被替换为真实的markdown图片
                                    img.replace_with(f'__IMG_PLACEHOLDER_{i}__')
                            
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
            # 构建Markdown内容
            markdown_content = f"# {title}\n\n"
            
            # 替换内容中的图片占位符为实际的Markdown图片
            processed_content = content
            for i, image_path in enumerate(image_paths):
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
                logger.info(f"Saved: {filename}")
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
        safe_title = self._get_safe_filename(post['title'])
        if safe_title not in self.downloaded_files:
            result = await self.parse_detail_page(session, post['url'], post['post_id'])
            if result:
                content, image_urls = result
                # 下载所有图片
                image_paths = []
                for image_url in image_urls:
                    image_path = await self.download_image(session, image_url, post['post_id'])
                    if image_path:
                        image_paths.append(image_path)
                
                # 保存内容和图片路径到文件
                await self.save_to_file(post['title'], content, image_paths)
        else:
            logger.debug(f"Skip processing downloaded post: {post['title']}")

    async def crawl_page(self, session: aiohttp.ClientSession, page_num: int):
        """爬取单个页面的所有帖子"""
        posts = await self.parse_list_page(session, page_num)
        if posts:
            tasks = [self.process_post(session, post) for post in posts]
            await asyncio.gather(*tasks)
        else:
            logger.info(f"No new posts found on page {page_num}")

    async def crawl(self, start_page=1, end_page=1):
        """异步爬取指定页数的内容"""
        async with aiohttp.ClientSession() as session:
            # 初始化session
            await self._init_session(session)
            
            # 创建每个页面的任务
            tasks = []
            for page_num in range(start_page, end_page + 1):
                logger.info(f"Creating task for page {page_num}")
                tasks.append(self.crawl_page(session, page_num))
            
            # 并发执行所有任务
            await asyncio.gather(*tasks)

def main():
    # 使用示例
    save_dir = './shuimu_data'  # 可以修改保存目录
    max_concurrency = 5  # 最大并发数
    crawler = ShuimuCrawler(save_dir=save_dir, max_concurrency=max_concurrency)
    
    # 运行异步爬虫
    asyncio.run(crawler.crawl(start_page=1, end_page=2))  # 爬取1-2页

if __name__ == '__main__':
    main()