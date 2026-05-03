"""
industry_news.py

聚合多个 RSS 源，用 LLM 筛选关键人物动态和行业大事，推送到飞书。

环境变量：
    FEISHU_WEBHOOK   飞书机器人 Webhook
    LLM_API_KEY      LLM API Key（可选，配置后开启 AI 筛选）
    LLM_BASE_URL     OpenAI 兼容 API 地址，默认 https://api.deepseek.com
    LLM_MODEL        模型名称，默认 deepseek-v4-flash
"""

import os
import re
import time
import requests
import feedparser
from datetime import datetime, timezone, timedelta

# ===== Config =====
FEISHU_WEBHOOK = os.environ.get("FEISHU_WEBHOOK", "")

# LLM 配置（兼容 OpenAI API 格式）
LLM_API_KEY   = os.environ.get("LLM_API_KEY", "")
LLM_BASE_URL  = (os.environ.get("LLM_BASE_URL") or "https://api.deepseek.com").rstrip("/")
LLM_MODEL     = os.environ.get("LLM_MODEL", "deepseek-v4-flash")

HOURS_LOOKBACK  = 26   # 只抓最近 N 小时内的文章
MAX_TO_KIMI     = 30   # 送给 Kimi 的最大文章数
MAX_RAW_DISPLAY = 5    # 降级时最多展示条数

KEY_FIGURES = [
    "黄仁勋", "Jensen Huang",
    "Sam Altman", "Greg Brockman",
    "杨植麟", "张磊",
    "Demis Hassabis", "Sundar Pichai",
    "李飞飞", "朱啸虎",
    "Marc Andreessen", "Elon Musk",
    "Dario Amodei", "Yann LeCun",
]

KEY_EVENTS = [
    "GTC", "Google I/O", "WWDC", "CES", "NeurIPS", "ICML", "ICLR",
    "世界人工智能大会", "乌镇峰会", "中关村论坛",
]

AI_KEYWORDS = [
    "AI", "大模型", "LLM", "GPT", "Claude", "Gemini", "Kimi",
    "融资", "发布", "Agent", "multimodal", "open source", "开源",
    "transformer", "inference", "training", "benchmark",
]

RSS_FEEDS = [
    ("36氪",         "https://36kr.com/feed",                       "zh"),
    ("机器之心",      "https://www.jiqizhixin.com/rss",               "zh"),
    ("量子位",        "https://www.qbitai.com/feed",                  "zh"),
    ("VentureBeat",  "https://venturebeat.com/feed/",                "en"),
    ("TechCrunch",   "https://techcrunch.com/feed/",                 "en"),
    ("The Verge",    "https://www.theverge.com/rss/index.xml",       "en"),
]

RSS_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    )
}


# ===== 工具函数 =====

def _clean_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _parse_published(entry) -> datetime | None:
    import time as time_mod
    t = entry.get("published_parsed") or entry.get("updated_parsed")
    if not t:
        return None
    try:
        return datetime.fromtimestamp(time_mod.mktime(t), tz=timezone.utc)
    except Exception:
        return None


def _relevance_score(article: dict) -> int:
    text = (article["title"] + " " + article["summary"]).lower()
    all_kw = KEY_FIGURES + KEY_EVENTS + AI_KEYWORDS
    return sum(1 for kw in all_kw if kw.lower() in text)


# ===== RSS 抓取 =====

def fetch_recent_articles() -> list[dict]:
    """
    用 requests 拉 RSS，再交给 feedparser 解析。
    直接 feedparser.parse(url) 不带 headers 很多源会 403。
    单源超时 12s，失败跳过不影响整体。
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=HOURS_LOOKBACK)
    articles = []

    for source_name, feed_url, lang in RSS_FEEDS:
        try:
            print(f"抓取 {source_name}...")
            resp = requests.get(feed_url, headers=RSS_HEADERS, timeout=12)
            resp.raise_for_status()
            feed = feedparser.parse(resp.content)

            count = 0
            for entry in feed.entries:
                pub = _parse_published(entry)
                if pub and pub < cutoff:
                    continue
                title   = entry.get("title", "").strip()
                url     = entry.get("link", "").strip()
                summary = _clean_html(entry.get("summary", ""))[:200]
                if not title or not url:
                    continue
                articles.append({
                    "title":     title,
                    "url":       url,
                    "source":    source_name,
                    "summary":   summary,
                    "published": pub.strftime("%m-%d %H:%M") if pub else "",
                    "lang":      lang,
                })
                count += 1
            print(f"  → {source_name} {count} 篇")

        except requests.RequestException as e:
            print(f"  {source_name} 网络失败（跳过）: {e}")
        except Exception as e:
            print(f"  {source_name} 解析失败（跳过）: {e}")

    articles.sort(key=_relevance_score, reverse=True)
    print(f"共 {len(articles)} 篇，按相关度排序完成")
    return articles


# ===== Kimi 筛选 =====

def kimi_filter_news(articles: list[dict]) -> str | None:
    if not LLM_API_KEY or not articles:
        return None

    subset = articles[:MAX_TO_KIMI]
    lines = []
    for i, a in enumerate(subset, 1):
        line = f"{i}. 【{a['source']}】{a['title']}"
        if a["summary"]:
            line += f"\n   摘要：{a['summary']}"
        if a["published"]:
            line += f"\n   时间：{a['published']}"
        line += f"\n   链接：{a['url']}"
        lines.append(line)

    key_figures_str = "、".join(KEY_FIGURES)
    key_events_str  = "、".join(KEY_EVENTS)

    prompt = f"""以下是今天从多个科技媒体抓取的 AI 行业资讯：

{chr(10).join(lines)}

请筛选出最多 5 条最值得关注的内容，优先级：
1. 关键人物公开讲话、采访、观点（重点：{key_figures_str}）
2. 重要行业大会核心内容（重点：{key_events_str}）
3. 重大融资、并购、战略合作
4. 影响行业格局的政策或监管动态

每条严格按此格式：

**标题**（来源）
一句话：发生了什么（不超过25字）
影响：为什么重要（不超过25字）
🔗 链接

条目间空一行，不加序号，不加总结，不编造。
没有符合条件的内容则输出：今日暂无重要动态。
直接输出，不要开场白。
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
                    "temperature": 0.4,
                    "max_tokens": 1000,
                    "messages": [
                        {
                            "role": "system",
                            "content": "你是一名专注 AI 行业的资深分析师，擅长从海量资讯中找出真正影响行业走向的关键信息。",
                        },
                        {"role": "user", "content": prompt},
                    ],
                },
                timeout=60,
            )
            data = resp.json()
            if data.get("choices"):
                print("Kimi 筛选完成")
                return data["choices"][0]["message"]["content"].strip()

            error_type = data.get("error", {}).get("type", "")
            retryable = error_type in {
                "engine_overloaded_error",
                "rate_limit_reached_error",
                "service_unavailable_error",
            }
            print(f"Kimi 失败（{attempt}/{max_retries}）:", data)
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

def build_ai_card(content: str) -> dict:
    today = datetime.now().strftime("%Y-%m-%d")
    sources = "、".join(s for s, _, _ in RSS_FEEDS)
    return {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": f"📡 行业动态 · {today}"},
                "template": "orange",
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
                        "content": (
                            f"_来源：{sources}_\n"
                            f"_由 AI 从近 {HOURS_LOOKBACK}h 资讯中筛选_"
                        ),
                    },
                },
            ],
        },
    }


def build_raw_card(articles: list[dict]) -> dict:
    """降级卡片：只展示相关度最高的前 MAX_RAW_DISPLAY 条"""
    today = datetime.now().strftime("%Y-%m-%d")
    top = articles[:MAX_RAW_DISPLAY]
    lines = [f"• [{a['title']}]({a['url']})  —_{a['source']}_" for a in top]
    return {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": f"📡 行业动态 · {today}"},
                "template": "orange",
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {"tag": "lark_md", "content": "\n".join(lines)},
                },
                {"tag": "hr"},
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": "_（未启用 AI 筛选，展示相关度最高的文章）_",
                    },
                },
            ],
        },
    }


# ===== 主流程 =====

def main():
    print("=" * 40)
    print("RSS 行业动态 → 飞书")
    print("=" * 40)

    articles = fetch_recent_articles()
    if not articles:
        print("未抓取到任何文章，退出")
        return

    if LLM_API_KEY:
        print(f"调用 LLM 筛选（{len(articles)} 篇，取前 {MAX_TO_KIMI}）...")
        content = kimi_filter_news(articles)
        card = build_ai_card(content) if content else build_raw_card(articles)
    else:
        print("未配置 LLM_API_KEY，使用降级展示")
        card = build_raw_card(articles)

    if not FEISHU_WEBHOOK:
        import json
        print("未配置 FEISHU_WEBHOOK，打印卡片：")
        print(json.dumps(card, ensure_ascii=False, indent=2))
        return

    resp = requests.post(FEISHU_WEBHOOK, json=card, timeout=10)
    print("飞书推送结果:", resp.json().get("msg", ""))


if __name__ == "__main__":
    main()
