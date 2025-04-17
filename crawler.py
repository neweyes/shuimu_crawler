import os
import time
import requests
from bs4 import BeautifulSoup
import re
from urllib.parse import urljoin
from lxml import html

class ShuimuCrawler:
    def __init__(self, save_dir='./data'):
        self.base_url = 'https://www.newsmth.net'
        self.board_url = 'https://www.newsmth.net/nForum/board/OurEstate'
        self.save_dir = save_dir
        self.session = requests.Session()
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
            
        # 初始化session
        self._init_session()

    def _init_session(self):
        """初始化会话，访问主页获取必要的cookies"""
        try:
            # 先访问主页
            self.session.get(self.base_url, headers=self.headers)
            # 再访问版面
            self.session.get(self.board_url, headers=self.headers)
        except Exception as e:
            print(f"Error initializing session: {str(e)}")

    def get_page_content(self, url):
        """获取页面内容"""
        try:
            response = self.session.get(url, headers=self.headers)
            response.encoding = 'gbk'  # 设置GBK编码
            return response.text
        except Exception as e:
            print(f"Error fetching {url}: {str(e)}")
            return None

    def parse_list_page(self, page_num):
        """解析列表页"""
        url = f'{self.board_url}?p={page_num}'
        content = self.get_page_content(url)
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
                                print(f"Found post: {title} - {full_link}")  # 调试信息
                except Exception as e:
                    print(f"Error parsing post row: {str(e)}")
                    continue
        else:
            print("Table with class 'board-list' not found!")  # 调试信息
        
        return posts

    def parse_detail_page(self, url):
        """解析详情页"""
        content = self.get_page_content(url)
        if not content:
            return None

        try:
            # 使用BeautifulSoup解析页面
            soup = BeautifulSoup(content, 'lxml')
            
            # 打印HTML结构以便调试
            print("\nHTML Structure:")
            # 找到所有的table元素
            tables = soup.find_all('table')
            print(f"Found {len(tables)} tables")
            
            # 遍历每个table，查找可能的内容
            for i, table in enumerate(tables):
                print(f"\nChecking table {i+1}:")
                # 查找第二行的第二个单元格
                rows = table.find_all('tr')
                if len(rows) >= 2:
                    cells = rows[1].find_all('td')
                    if len(cells) >= 2:
                        print(f"Content in table {i+1}, row 2, cell 2:")
                        content_text = cells[1].get_text(strip=True)
                        print(content_text[:200] + "..." if len(content_text) > 200 else content_text)
                        
                        # 如果这个单元格包含实际内容，就使用它
                        if len(content_text.strip()) > 50:  # 假设真实内容长度会大于50个字符
                            # 获取完整内容
                            full_text = cells[1].get_text(separator='\n', strip=True)
                            # 清理文本（去除多余的空白行等）
                            cleaned_content = '\n'.join(line.strip() for line in full_text.split('\n') if line.strip())
                            return cleaned_content
            
            print("\nNo suitable content found in any table!")
            print("Page content preview:")
            print(content[:500])
            return None
            
        except Exception as e:
            print(f"Error parsing article content: {str(e)}")
            print("Page content preview:")
            print(content[:500])
        return None

    def save_to_file(self, title, content):
        """保存内容到文件"""
        # 清理文件名中的非法字符
        title = re.sub(r'[\\/*?:"<>|]', '_', title)
        filename = os.path.join(self.save_dir, f"{title}.txt")
        
        try:
            # 使用GBK编码保存文件
            with open(filename, 'w', encoding='gbk', errors='ignore') as f:
                f.write(content)
            print(f"Saved: {filename}")
            
            # 验证文件是否正确保存
            try:
                with open(filename, 'r', encoding='gbk') as f:
                    test_content = f.read()
                if not test_content:
                    print(f"Warning: File {filename} appears to be empty")
            except Exception as e:
                print(f"Warning: Unable to verify file content: {str(e)}")
                
        except Exception as e:
            print(f"Error saving {filename}: {str(e)}")

    def crawl(self, start_page=1, end_page=1):
        """爬取指定页数的内容"""
        for page_num in range(start_page, end_page + 1):
            print(f"\nCrawling page {page_num}...")
            posts = self.parse_list_page(page_num)
            
            for post in posts:
                print(f"\nProcessing: {post['title']}")
                content = self.parse_detail_page(post['url'])
                if content:
                    self.save_to_file(post['title'], content)
                time.sleep(1)  # 添加延时，避免请求过于频繁
            
            time.sleep(2)  # 页面之间的延时

def main():
    # 使用示例
    save_dir = './shuimu_data'  # 可以修改保存目录
    crawler = ShuimuCrawler(save_dir=save_dir)
    crawler.crawl(start_page=1, end_page=1)  # 先只爬取第1页进行测试

if __name__ == '__main__':
    main()