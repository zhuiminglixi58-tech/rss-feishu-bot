# rss-feishu-bot

每天自动推送 AI 资讯到飞书群的机器人，覆盖早报、行业动态、GitHub Trending，并在每周五推送周报。

## 推送内容

| 卡片 | 脚本 | 触发时间（北京时间） | 说明 |
|---|---|---|---|
| 🤖 AI 早报 + 🧠 AI 解读 | `rss_to_feishu.py` | 每天 09:00 | 开工前扫一眼 |
| 📡 行业动态 | `industry_news.py` | 每天 12:00 | 午休碎片时间 |
| 🔥 GitHub Trending | `github_trending.py` | 每天 18:00 | 下班前看技术项目 |
| 📋 周报 | `weekly_digest.py` | 每周五 17:00 | 适合周末延伸阅读 |

## 数据来源

- **AI 早报**：[imjuya/juya-ai-daily](https://github.com/imjuya/juya-ai-daily) GitHub Issues
- **行业动态**：36氪、机器之心、量子位、VentureBeat、TechCrunch、The Verge 等 RSS 源，经 Kimi 筛选摘要
- **GitHub Trending**：每日 Trending 项目，经 Kimi 解读
- **周报**：汇总本周 `reports/` 目录内容，由 Kimi 生成综合解读

## 项目结构

```
rss_to_feishu.py          # AI 早报 + AI 解读（调用 github_trending.py + reports/）
industry_news.py          # 行业 RSS 动态
github_trending.py        # GitHub Trending 抓取
weekly_digest.py          # 周报生成
reports/                  # 历史报告（供周报引用）
.github/workflows/
  AI Daily.yml            # 09:00 每天
  Industry News.yml       # 12:00 每天
  Github trending.yml     # 18:00 每天
  Weekly digest.yml       # 17:00 每周五
```

## 环境变量

在 GitHub 仓库 Settings → Secrets and variables → Actions 中配置：

| 变量 | 必填 | 说明 |
|---|---|---|
| `FEISHU_WEBHOOK` | 是 | 飞书机器人 Webhook 地址 |
| `KIMI_API_KEY` | 推荐 | Moonshot Kimi API Key，未配置则跳过 AI 解读和筛选 |
| `GITHUB_TOKEN` | 否 | 提高 GitHub API 请求限额（Workflow 自动注入） |

## 本地运行

```bash
pip install -r requirements.txt

export FEISHU_WEBHOOK='https://open.feishu.cn/open-apis/bot/v2/hook/xxx'
export KIMI_API_KEY='your-kimi-api-key'

python rss_to_feishu.py    # 早报 + AI 解读
python industry_news.py    # 行业动态
python github_trending.py  # GitHub Trending
python weekly_digest.py    # 周报
```
