# rss-feishu-bot

每天自动推送 AI 资讯到飞书群的机器人，每周五额外生成一份本周精华周报。

## 推送时间表

| 时间 | 卡片 | 数据来源 |
|------|------|---------|
| 每天 09:00 | 🤖 AI 早报 | juya-ai-daily 最新 Issue |
| 每天 09:00 | 🧠 今日 AI 解读 | 早报 + GitHub Trending，由 Kimi 综合生成 |
| 每天 12:00 | 📡 行业动态 | 6 个 RSS 源，由 Kimi 筛选关键人物/大会/融资动态 |
| 每天 18:00 | ⭐ GitHub 热门 | GitHub Trending，由 Kimi 筛选 5 个最值得关注的项目 |
| 每周五 17:00 | 📋 本周精华 | 本周早报 + GitHub Trending weekly + RSS，由 Kimi 综合生成周报 |

## 项目结构

```
rss_to_feishu.py      # 早报 + AI 解读（09:00）
industry_news.py      # RSS 行业动态（12:00）
github_trending.py    # GitHub 热门项目（18:00）
weekly_digest.py      # 每周精华周报（每周五 17:00）

.github/workflows/
  AI Daily.yml        # 触发 rss_to_feishu.py
  Industry News.yml   # 触发 industry_news.py
  Github trending.yml # 触发 github_trending.py
  Weekly digest.yml   # 触发 weekly_digest.py

reports/              # 历史报告存档（不参与主流程）
```

## 数据流

```
juya-ai-daily（GitHub Issues）
  └─→ rss_to_feishu.py
        ├─→ 飞书：🤖 AI 早报
        └─→ Kimi（+ GitHub Trending）→ 飞书：🧠 今日 AI 解读

36氪 / 机器之心 / 量子位 / VentureBeat / TechCrunch / The Verge（RSS）
  └─→ industry_news.py → Kimi 筛选 → 飞书：📡 行业动态

github.com/trending
  └─→ github_trending.py → Kimi 筛选 → 飞书：⭐ GitHub 热门

以上三路数据（本周汇总）
  └─→ weekly_digest.py → Kimi 综合 → 飞书：📋 本周精华
```

## 环境变量

在仓库 Settings → Secrets and variables → Actions 中配置：

| 变量 | 必填 | 说明 |
|------|------|------|
| `FEISHU_WEBHOOK` | 是 | 飞书机器人 Webhook 地址 |
| `LLM_API_KEY` | 推荐 | LLM API Key，未配置则跳过 AI 筛选，直接推原始列表 |
| `LLM_BASE_URL` | 否 | OpenAI 兼容 API 地址，默认 `https://api.deepseek.com` |
| `LLM_MODEL` | 否 | 模型名称，默认 `deepseek-v4-flash` |
| `GITHUB_TOKEN` | 否 | 提高 GitHub API 请求限额，避免匿名限流 |

## 本地运行

```bash
pip install requests feedparser

export FEISHU_WEBHOOK='https://open.feishu.cn/open-apis/bot/v2/hook/xxx'
export LLM_API_KEY='your-llm-api-key'

python rss_to_feishu.py    # 早报 + AI 解读
python industry_news.py    # 行业动态
python github_trending.py  # GitHub 热门
python weekly_digest.py    # 本周精华（可随时手动触发）
```

未配置 `FEISHU_WEBHOOK` 时，各脚本会直接打印卡片 JSON，方便本地调试。

## 降级策略

每个脚本在 Kimi 不可用时都有降级处理，保证每天必有内容推送：

- `rss_to_feishu.py`：仅推送早报卡片，跳过 AI 解读
- `industry_news.py`：推送相关度最高的 5 条原始标题
- `github_trending.py`：推送 Top 10 原始项目列表
- `weekly_digest.py`：推送提示卡片，告知 Kimi 不可用
