import os
import time
import asyncio
import aiohttp
from bs4 import BeautifulSoup
import re
from urllib.parse import urljoin
from typing import List, Dict, Optional
import logging

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
                                posts.append({
                                    'title': title,
                                    'url': full_link
                                })
                                logger.info(f"Found post: {title}")
                except Exception as e:
                    logger.error(f"Error parsing post row: {str(e)}")
                    continue
        else:
            logger.warning("Table with class 'board-list' not found!")
        
        return posts

    async def parse_detail_page(self, session: aiohttp.ClientSession, url: str) -> Optional[str]:
        """解析详情页"""
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
                        content_text = cells[1].get_text(strip=True)
                        if len(content_text.strip()) > 50:
                            full_text = cells[1].get_text(separator='\n', strip=True)
                            cleaned_content = '\n'.join(line.strip() for line in full_text.split('\n') if line.strip())
                            return cleaned_content
            
            logger.warning("No suitable content found in any table!")
            return None
            
        except Exception as e:
            logger.error(f"Error parsing article content: {str(e)}")
            return None

    async def save_to_file(self, title: str, content: str):
        """保存内容到文件"""
        # 清理文件名中的非法字符
        title = re.sub(r'[\\/*?:"<>|]', '_', title)
        filename = os.path.join(self.save_dir, f"{title}.txt")
        
        try:
            # 使用GBK编码保存文件
            async with asyncio.Lock():  # 使用锁来保护文件写入
                with open(filename, 'w', encoding='gbk', errors='ignore') as f:
                    f.write(content)
                logger.info(f"Saved: {filename}")
            
            # 验证文件是否正确保存
            try:
                with open(filename, 'r', encoding='gbk') as f:
                    test_content = f.read()
                if not test_content:
                    logger.warning(f"Warning: File {filename} appears to be empty")
            except Exception as e:
                logger.warning(f"Warning: Unable to verify file content: {str(e)}")
                
        except Exception as e:
            logger.error(f"Error saving {filename}: {str(e)}")

    async def process_post(self, session: aiohttp.ClientSession, post: Dict):
        """处理单个帖子"""
        content = await self.parse_detail_page(session, post['url'])
        if content:
            await self.save_to_file(post['title'], content)

    async def crawl_page(self, session: aiohttp.ClientSession, page_num: int):
        """爬取单个页面的所有帖子"""
        posts = await self.parse_list_page(session, page_num)
        tasks = [self.process_post(session, post) for post in posts]
        await asyncio.gather(*tasks)

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
    asyncio.run(crawler.crawl(start_page=1, end_page=3))  # 爬取1-3页进行测试

if __name__ == '__main__':
    main()