# 水木社区爬虫

这是一个高性能的水木社区爬虫，使用Python异步编程实现，支持多版面并发爬取、图片下载、断点续传等功能。

## 功能特点

- 异步并发爬取，提高爬取效率
- 支持多版面同时爬取
- 自动下载和保存帖子内容及图片
- Markdown格式保存，便于阅读和分享
- 完善的断点续传机制
- 灵活的配置系统
- 详细的日志记录
- 代理支持和请求重试机制
- 智能编码检测

## 配置说明

配置文件使用JSON格式，支持以下配置项：

```json
{
    "base_url": "https://www.newsmth.net",
    "output_dir": "output",
    "image_dir": "output/images",
    "max_concurrent_tasks": 5,
    "max_retries": 3,
    "retry_delay": 1.0,
    "timeout": 30.0,
    "save_images": true,
    "user_agents": [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36"
    ],
    "proxies": [
        "http://proxy1.example.com:8080",
        "http://proxy2.example.com:8080"
    ],
    "boards": [
        {
            "name": "Python",
            "url": "https://www.newsmth.net/nForum/board/Python",
            "max_pages": 5,
            "max_posts": 100
        }
    ]
}
```

### 配置项说明

- `base_url`: 网站基础URL
- `output_dir`: 输出目录路径
- `image_dir`: 图片保存目录路径
- `max_concurrent_tasks`: 最大并发任务数
- `max_retries`: 请求失败最大重试次数
- `retry_delay`: 重试间隔时间（秒）
- `timeout`: 请求超时时间（秒）
- `save_images`: 是否保存图片
- `user_agents`: User-Agent列表
- `proxies`: 代理服务器列表
- `boards`: 要爬取的版面配置列表
  - `name`: 版面名称
  - `url`: 版面URL
  - `max_pages`: 最大爬取页数
  - `max_posts`: 最大爬取帖子数

## 使用方法

1. 安装依赖：

```bash
pip install -r requirements.txt
```

2. 创建配置文件 `config.json`

3. 运行爬虫：

```bash
python main.py
```

## 输出格式

爬虫将按以下结构保存数据：

```
output/
├── images/
│   └── [帖子标题]/
│       ├── image_1.jpg
│       ├── image_2.jpg
│       └── ...
├── [版面名称]/
│   └── posts/
│       ├── [帖子标题].md
│       ├── [帖子标题].json
│       └── ...
└── crawler.log
```

- `.md` 文件包含帖子的完整内容，包括标题、作者、发布时间、正文和图片
- `.json` 文件包含帖子的元数据
- `crawler.log` 记录爬虫运行日志

## 注意事项

1. 请遵守网站的robots协议
2. 建议适当设置并发数和延迟，避免对服务器造成压力
3. 使用代理时请确保代理服务器可用
4. 确保有足够的磁盘空间存储图片

## 开发计划

- [ ] 添加更多的数据导出格式
- [ ] 支持增量更新
- [ ] 添加命令行参数支持
- [ ] 优化内存使用
- [ ] 添加更多的数据分析功能

## 贡献指南

欢迎提交Issue和Pull Request！

## 许可证

MIT License