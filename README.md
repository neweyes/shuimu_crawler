# Shuimu Crawler

一个用于爬取水木社区房产版面的爬虫程序。

## 功能特点

- 支持分页爬取
- 自动处理中文编码
- 保存帖子内容到文本文件
- 自定义保存目录
- 错误处理和重试机制

## 安装依赖

```bash
pip install -r requirements.txt
```

## 使用方法

1. 克隆仓库：

```bash
git clone https://github.com/neweyes/shuimu_crawler.git
cd shuimu_crawler
```

2. 安装依赖：

```bash
pip install -r requirements.txt
```

3. 运行爬虫：

```bash
python crawler.py
```

## 配置说明

在 `crawler.py` 的 `main()` 函数中，你可以修改以下参数：

- `save_dir`：保存文件的目录
- `start_page`：开始页码
- `end_page`：结束页码

## 注意事项

- 请遵守网站的使用规则和爬虫协议
- 建议设置适当的爬取间隔，避免对服务器造成压力
- 爬取的内容仅供学习研究使用

## 许可证

MIT License