"""
weekly_digest.py

每周五汇总本周 AI 动态，生成一张「本周精华」飞书卡片推送。

运行逻辑：
  1. 拉取 juya-ai-daily 最近 7 条 issue（本周早报原料）
  2. 抓取 GitHub Trending（weekly 维度，反映本周热门）
  3. 抓取 RSS 本周文章
  4. 统一交给 LLM 生成周报
  5. 推送飞书

环境变量：
  FEISHU_WEBHOOK   飞书机器人 Webhook
  LLM_API_KEY      LLM API Key
  LLM_BASE_URL     OpenAI 兼容 API 地址，默认 https://api.deepseek.com
  LLM_MODEL        模型名称，默认 deepseek-v4-flash
  GITHUB_TOKEN     GitHub Token（可选）
"""

import os
import re
import time
import requests
import feedparser
from datetime import datetime, timezone, timedelta

FEISHU_WEBHOOK = os.environ.get("FEISHU_WEBHOOK", "")

# LLM 配置（兼容 OpenAI API 格式）
LLM_API_KEY   = os.environ.get("LLM_API_KEY", "")
LLM_BASE_URL  = (os.environ.get("LLM_BASE_URL") or "https://api.deepseek.com").rstrip("/")
LLM_MODEL     = os.environ.get("LLM_MODEL") or "deepseek-v4-flash"

GITHUB_TOKEN   = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO    = "imjuya/juya-ai-daily"

RSS_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    )
}

RSS_FEEDS = [
    ("36氪",        "https://36kr.com/feed",              "zh"),
    ("机器之心",     "https://www.jiqizhixin.com/rss",      "zh"),
    ("量子位",       "https://www.qbitai.com/feed",         "zh"),
    ("VentureBeat", "https://venturebeat.com/feed/",       "en"),
    ("TechCrunch",  "https://techcrunch.com/feed/",        "en"),
]


# ===== 数据采集 =====

def fetch_weekly_issues() -> str:
    """拉取 juya 最近 7 条 issue 的概览内容，拼成文本块"""
    url = f"https://api.github.com/repos/{GITHUB_REPO}/issues"
    params = {"state": "open", "per_page": 7, "sort": "created", "direction": "desc"}
    headers = {"Accept": "application/vnd.github.v3+json"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"

    try:
        resp = requests.get(url, params=params, headers=headers, timeout=15)
        issues = resp.json()
    except Exception as e:
        print(f"拉取 issues 失败: {e}")
        return ""

    blocks = []
    for issue in issues:
        title = issue.get("title", "")
        body  = issue.get("body", "")
        overview = _extract_overview_text(body)
        if overview:
            blocks.append(f"=== {title} ===\n{overview}")

    print(f"拉取到 {len(blocks)} 条 issue 概览")
    return "\n\n".join(blocks)


def _extract_overview_text(body: str) -> str:
    """提取 issue body 中 ## 概览 部分的纯文本"""
    in_overview = False
    lines = []
    for line in body.split("\n"):
        stripped = line.strip()
        if stripped.startswith("## ") and stripped[3:].strip() == "概览":
            in_overview = True
            continue
        if in_overview and stripped.startswith("## "):
            break
        if in_overview and stripped:
            text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", stripped)
            text = re.sub(r"<[^>]+>", "", text).strip()
            if text:
                lines.append(text)
    return "\n".join(lines)


def fetch_weekly_trending() -> str:
    """抓取 GitHub Trending weekly，返回前 10 个项目的文本摘要"""
    url = "https://github.com/trending?since=weekly"
    try:
        resp = requests.get(url, headers=RSS_HEADERS, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        print(f"抓取 Trending 失败: {e}")
        return ""

    articles = re.findall(
        r'<article\s+class="Box-row">(.*?)</article>',
        resp.text, re.DOTALL
    )

    lines = []
    seen = set()
    for article in articles:
        m = re.search(r'href="/([^/"]+/[^/"]+)"', article)
        if not m:
            continue
        full_name = m.group(1).strip()
        if full_name in seen:
            continue
        seen.add(full_name)

        desc_m = re.search(r'<p\s+class="[^"]*col-9[^"]*"[^>]*>(.*?)</p>', article, re.DOTALL)
        desc = re.sub(r"<[^>]+>", "", desc_m.group(1)).strip() if desc_m else ""

        stars_m = re.search(r'([\d,]+)\s+stars this week', article)
        stars = stars_m.group(1) if stars_m else "?"

        lines.append(f"- {full_name}（本周 +{stars} stars）: {desc}")
        if len(lines) >= 10:
            break

    print(f"抓取到 {len(lines)} 个本周热门项目")
    return "\n".join(lines)


def fetch_weekly_rss() -> str:
    """抓取近 7 天 RSS 文章，按 AI 相关度排序后返回前 40 条标题+摘要"""
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    ai_keywords = [
        "AI", "大模型", "LLM", "GPT", "Claude", "Gemini", "Kimi",
        "融资", "发布", "Agent", "open source", "开源",
        "黄仁勋", "Sam Altman", "杨植麟", "GTC", "Google I/O",
    ]

    articles = []
    for source, feed_url, _ in RSS_FEEDS:
        try:
            resp = requests.get(feed_url, headers=RSS_HEADERS, timeout=12)
            resp.raise_for_status()
            feed = feedparser.parse(resp.content)
            for entry in feed.entries:
                t = entry.get("published_parsed") or entry.get("updated_parsed")
                if t:
                    import time as tm
                    pub = datetime.fromtimestamp(tm.mktime(t), tz=timezone.utc)
                    if pub < cutoff:
                        continue
                title   = entry.get("title", "").strip()
                summary = re.sub(r"<[^>]+>", "", entry.get("summary", ""))[:150].strip()
                if title:
                    score = sum(1 for kw in ai_keywords if kw.lower() in (title + summary).lower())
                    articles.append((score, source, title, summary))
        except Exception as e:
            print(f"  {source} 失败（跳过）: {e}")

    articles.sort(key=lambda x: x[0], reverse=True)
    lines = []
    for _, source, title, summary in articles[:40]:
        line = f"- 【{source}】{title}"
        if summary:
            line += f"：{summary}"
        lines.append(line)

    print(f"RSS 获取 {len(lines)} 篇本周文章")
    return "\n".join(lines)


# ===== Kimi 生成周报 =====

def generate_weekly_report(issues_text: str, trending_text: str, rss_text: str) -> str | None:
    if not LLM_API_KEY:
        return None

    # 计算本周日期范围
    today = datetime.now()
    monday = today - timedelta(days=today.weekday())
    week_range = f"{monday.strftime('%m/%d')} - {today.strftime('%m/%d')}"

    prompt = f"""以下是本周（{week_range}）的 AI 行业信息汇总，来自三个维度：

【一、每日早报摘要（juya-ai-daily 本周内容）】
{issues_text[:3000]}

【二、GitHub 本周热门项目】
{trending_text}

【三、本周 RSS 媒体报道精选】
{rss_text[:2000]}

请你作为一名 AI 行业观察者，生成一份「本周 AI 精华周报」。

严格按以下结构输出，每个区块之间空一行：

**本周一句话总结**
用一句话概括本周 AI 行业最核心的变化（不超过 30 字）

**本周三大事件**
• 事件一：发生了什么 + 为什么重要（2 句以内）
• 事件二：同上
• 事件三：同上

**本周技术趋势**
• 趋势一：一句话描述（从 GitHub 热门或技术新闻中提炼）
• 趋势二：同上
• 趋势三：同上

**工具与产品更新**
• 最值得普通用户关注的 2-3 个产品/功能变化，每条一句话

**下周值得关注**
• 1-2 件下周可能发生或值得跟进的事情

要求：
- 全文控制在 350 字以内
- 全部分条，禁止长段落
- 不编造信息，只基于提供的内容
- 直接输出，不要开场白
"""

    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.post(
                f"{LLM_BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {LLM_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": LLM_MODEL,
                    "temperature": 0.5,
                    "max_tokens": 1200,
                    "messages": [
                        {
                            "role": "system",
                            "content": "你是一名专注 AI 行业的资深分析师，擅长提炼一周内的关键信息，输出简洁有价值的周报。",
                        },
                        {"role": "user", "content": prompt},
                    ],
                },
                timeout=90,
            )
            data = resp.json()
            if data.get("choices"):
                print("LLM 周报生成完成")
                return data["choices"][0]["message"]["content"].strip()

            error_type = data.get("error", {}).get("type", "")
            retryable = error_type in {
                "engine_overloaded_error",
                "rate_limit_reached_error",
                "service_unavailable_error",
            }
            print(f"LLM 失败（{attempt}/{max_retries}）:", data)
            if attempt == max_retries or not retryable:
                return None

        except requests.RequestException as e:
            print(f"LLM 请求异常（{attempt}/{max_retries}）: {e}")
            if attempt == max_retries:
                return None

        delay = 2 * (2 ** (attempt - 1))
        print(f"{delay}s 后重试...")
        time.sleep(delay)

    return None


# ===== 飞书卡片 =====

def build_weekly_card(content: str) -> dict:
    today = datetime.now()
    monday = today - timedelta(days=today.weekday())
    week_range = f"{monday.strftime('%m/%d')} - {today.strftime('%m/%d')}"

    return {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": f"📋 本周 AI 精华 · {week_range}",
                },
                "template": "indigo",
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {"tag": "lark_md", "content": content},
                },
                {"tag": "hr"},
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": "_由 AI 从本周早报、GitHub Trending、RSS 媒体综合生成_",
                    },
                },
            ],
        },
    }


def build_raw_card() -> dict:
    """Kimi 不可用时的降级卡片"""
    today = datetime.now()
    monday = today - timedelta(days=today.weekday())
    week_range = f"{monday.strftime('%m/%d')} - {today.strftime('%m/%d')}"
    return {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": f"📋 本周 AI 精华 · {week_range}",
                },
                "template": "indigo",
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": "本周周报生成失败（AI 服务不可用），请手动查看各日报回顾。",
                    },
                },
            ],
        },
    }


# ===== 主流程 =====

def main():
    print("=" * 40)
    print("周报生成 → 飞书")
    print("=" * 40)

    print("\n[1/3] 拉取本周早报...")
    issues_text = fetch_weekly_issues()

    print("\n[2/3] 抓取本周 GitHub Trending...")
    trending_text = fetch_weekly_trending()

    print("\n[3/3] 抓取本周 RSS 文章...")
    rss_text = fetch_weekly_rss()

    if not any([issues_text, trending_text, rss_text]):
        print("三个数据源全部失败，退出")
        return

    print("\n生成周报...")
    content = generate_weekly_report(issues_text, trending_text, rss_text)
    card = build_weekly_card(content) if content else build_raw_card()

    if not FEISHU_WEBHOOK:
        import json
        print("未配置 FEISHU_WEBHOOK，打印卡片：")
        print(json.dumps(card, ensure_ascii=False, indent=2))
        return

    resp = requests.post(FEISHU_WEBHOOK, json=card, timeout=10)
    print("飞书推送结果:", resp.json().get("msg", ""))


if __name__ == "__main__":
    main()
