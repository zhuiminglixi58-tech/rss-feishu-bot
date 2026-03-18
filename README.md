# rss-feishu-bot

每天自动推送三条飞书卡片的 AI 资讯机器人，数据来源涵盖 AI 早报、行业 RSS 动态、GitHub Trending，并通过 Kimi 生成综合解读。

## 推送内容

每天北京时间 09:00 自动触发，推送以下三条卡片：

| 卡片 | 内容 | 触发时间 |
|---|---|---|
| 🤖 AI 早报 | 来自 [imjuya/juya-ai-daily](https://github.com/imjuya/juya-ai-daily) 的分类新闻概览 | 09:00 |
| 🧠 今日 AI 解读 | Kimi 综合早报 + 行业动态 + GitHub Trending 生成解读 | 09:00（紧随早报） |
| 📡 行业动态 | 36氪、机器之心、量子位、VentureBeat 等 6 个 RSS 源，经 Kimi 筛选 | 09:30 |

> GitHub Trending 数据由 AI 解读卡片内联展示，不单独推送。

## 项目结构

```
rss_to_feishu.py          # 主脚本：早报 + AI 综合解读
industry_news.py          # RSS 行业动态抓取与推送
github_trending.py        # GitHub Trending 抓取（供 rss_to_feishu.py 调用）
reports/                  # industry_news.py 生成的 Markdown 报告（供解读引用）
.github/workflows/
  AI Daily.yml            # 每天 09:00 运行 rss_to_feishu.py
  Industry News.yml       # 每天 09:30 运行 industry_news.py
  Github trending.yml     # 每天 09:00 单独推送 GitHub Trending（可选保留）
```

## 数据流

```
GitHub Issues API
  └─→ rss_to_feishu.py
        ├─→ 飞书：🤖 AI 早报卡片
        └─→ (+ Kimi API + GitHub Trending + reports/)
              └─→ 飞书：🧠 今日 AI 解读卡片

6 个 RSS 源 (36氪 / 机器之心 / 量子位 / VentureBeat / TechCrunch / The Verge)
  └─→ industry_news.py
        └─→ Kimi 筛选
              └─→ 飞书：📡 行业动态卡片
```

## 环境变量

| 变量 | 必填 | 说明 |
|---|---|---|
| `FEISHU_WEBHOOK` | 是 | 飞书机器人 Webhook 地址 |
| `KIMI_API_KEY` | 推荐 | Moonshot Kimi API Key，未配置则跳过 AI 解读和筛选 |
| `GITHUB_TOKEN` | 否 | 提高 GitHub API 请求限额 |

在 GitHub 仓库 → Settings → Secrets and variables → Actions 中配置。

## 本地运行

```bash
pip install -r requirements.txt

export FEISHU_WEBHOOK='https://open.feishu.cn/open-apis/bot/v2/hook/xxx'
export KIMI_API_KEY='your-kimi-api-key'
export GITHUB_TOKEN='your-github-token'   # 可选

# 推送早报 + AI 解读
python rss_to_feishu.py

# 推送行业动态
python industry_news.py
```

## 依赖

```
requests
feedparser
```
