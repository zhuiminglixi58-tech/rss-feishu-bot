"""
github_trending.py

抓取 GitHub Trending 每日热门项目，经 Kimi 筛选后推送到飞书。

用法：
    python github_trending.py

环境变量（与 rss_to_feishu.py 共用）：
    FEISHU_WEBHOOK   飞书机器人 Webhook
    KIMI_API_KEY     Kimi API Key（可选，配置后开启 AI 筛选）
    GITHUB_TOKEN     GitHub Token（可选，用于提高 API 请求限额）
"""

import os
import re
import time
import requests
from datetime import datetime

# ===== Config =====
FEISHU_WEBHOOK = os.environ.get("FEISHU_WEBHOOK", "")
KIMI_API_KEY   = os.environ.get("KIMI_API_KEY", "")
GITHUB_TOKEN   = os.environ.get("GITHUB_TOKEN", "")

# 抓取的语言范围：空字符串 = 全语言，可改为 "python" / "typescript" 等
TRENDING_LANGUAGE = ""
# 时间范围：daily / weekly / monthly
TRENDING_SINCE = "daily"
# 最多取前 N 个项目送给 Kimi 筛选
MAX_REPOS = 25


# ===== 抓取 GitHub Trending =====

def fetch_trending_repos(language: str = "", since: str = "daily") -> list[dict]:
    """
    直接解析 github.com/trending 页面 HTML。
    官方页面是最权威的信息源，无需依赖第三方 API。
    返回 list of dict，每项包含：name, full_name, url, description, language, stars_today, total_stars
    """
    lang_path = f"/{language}" if language else ""
    url = f"https://github.com/trending{lang_path}?since={since}"

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/123.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    print(f"正在抓取 GitHub Trending: {url}")
    resp = requests.get(url, headers=headers, timeout=20)
    resp.raise_for_status()

    repos = []
    # 每个项目在 <article class="Box-row"> 里
    articles = re.findall(
        r'<article\s+class="Box-row">(.*?)</article>',
        resp.text,
        re.DOTALL,
    )

    for article in articles[:MAX_REPOS]:
        repo = _parse_article(article)
        if repo:
            repos.append(repo)

    print(f"解析到 {len(repos)} 个项目")
    return repos


def _parse_article(html: str) -> dict | None:
    """从单个 <article> 块中提取项目信息"""

    # full_name: owner/repo
    m = re.search(r'href="/([^/"]+/[^/"]+)"', html)
    if not m:
        return None
    full_name = m.group(1).strip()
    name = full_name.split("/")[-1]
    repo_url = f"https://github.com/{full_name}"

    # description
    desc_m = re.search(r'<p\s+class="[^"]*col-9[^"]*"[^>]*>(.*?)</p>', html, re.DOTALL)
    description = ""
    if desc_m:
        description = re.sub(r'<[^>]+>', '', desc_m.group(1)).strip()

    # 今日新增 stars
    stars_today = 0
    today_m = re.search(r'([\d,]+)\s+stars today', html)
    if today_m:
        stars_today = int(today_m.group(1).replace(",", ""))

    # 总 star 数
    total_stars = 0
    total_m = re.search(
        r'href="/' + re.escape(full_name) + r'/stargazers"[^>]*>\s*'
        r'.*?([\d,]+)\s*</a>',
        html, re.DOTALL
    )
    if total_m:
        total_stars = int(total_m.group(1).replace(",", ""))

    # 主语言
    lang_m = re.search(
        r'itemprop="programmingLanguage"[^>]*>(.*?)<',
        html
    )
    language = lang_m.group(1).strip() if lang_m else ""

    return {
        "name": name,
        "full_name": full_name,
        "url": repo_url,
        "description": description,
        "language": language,
        "stars_today": stars_today,
        "total_stars": total_stars,
    }


# ===== Kimi 筛选与解读 =====

def kimi_filter_repos(repos: list[dict]) -> str | None:
    """
    把原始 Trending 列表送给 Kimi，
    让它筛选出最有趣/前沿的项目并用人话描述。
    返回格式化好的 Markdown 文本，直接塞进飞书卡片。
    """
    if not KIMI_API_KEY:
        return None

    # 整理成文本给 Kimi
    repo_lines = []
    for i, r in enumerate(repos, 1):
        line = f"{i}. [{r['full_name']}]({r['url']})"
        if r["description"]:
            line += f"\n   描述：{r['description']}"
        if r["language"]:
            line += f"\n   语言：{r['language']}"
        line += f"\n   今日新增 ⭐：{r['stars_today']:,}"
        repo_lines.append(line)

    repo_text = "\n\n".join(repo_lines)

    prompt = f"""以下是今天 GitHub Trending 的热门项目列表：

{repo_text}

请你作为一个编程新手导师，从中挑选 5 个最适合编程初学者（有 Python、SQL 基础）的项目。

选择标准（按优先级）：
1. Python 相关项目：学习资源、实用小工具、数据分析、自动化脚本
2. SQL / 数据库相关：数据查询、可视化、数据处理工具
3. AI / 大模型工具：用 Python 就能上手体验的 AI 应用
4. 新手友好的学习资源：教程、练习项目、入门指南
5. 实用小工具：安装简单、立竿见影、不需要复杂环境的项目

【排除】以下类型不适合新手，请不要选：
- 底层系统、编译器、Rust/C++ 等低级语言项目
- 需要复杂部署环境的基础设施
- 纯前端框架或移动端开发

输出格式要求（严格遵守）：
- 每个项目单独一条，用以下固定结构：
  **项目名**（编程语言）⭐ 今日新增stars数
  是什么：用最通俗的中文一句话说清楚这个项目是什么
  新手怎么用：1-2 句，告诉初学者这个项目能帮他做什么、怎么快速上手
  适合你，因为：一句话说明为什么有 Python/SQL 基础就能用

- 5 个项目之间用空行分隔
- 不要加序号
- 不要加总结段落
- 不要编造信息，只基于提供的描述

请直接输出，不要加任何开场白或结尾说明。
"""

    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.post(
                "https://api.moonshot.cn/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {KIMI_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "moonshot-v1-8k",
                    "temperature": 0.5,
                    "max_tokens": 1024,
                    "messages": [
                        {
                            "role": "system",
                            "content": "你是一名耐心的编程新手导师，擅长从编程初学者的视角出发，用简单易懂的中文介绍 GitHub 上适合新手的项目，尤其关注 Python、SQL、数据分析方向。",
                        },
                        {"role": "user", "content": prompt},
                    ],
                },
                timeout=60,
            )

            data = resp.json()
            if data.get("choices"):
                result = data["choices"][0]["message"]["content"]
                print("Kimi 筛选完成")
                return result

            error_type = data.get("error", {}).get("type", "")
            retryable = error_type in {
                "engine_overloaded_error",
                "rate_limit_reached_error",
                "service_unavailable_error",
            }
            print(f"Kimi 调用失败（第 {attempt}/{max_retries} 次）:", data)
            if attempt == max_retries or not retryable:
                return None

        except requests.RequestException as e:
            print(f"Kimi 请求异常（第 {attempt}/{max_retries} 次）: {e}")
            if attempt == max_retries:
                return None

        delay = 2 * (2 ** (attempt - 1))
        print(f"{delay} 秒后重试...")
        time.sleep(delay)

    return None


# ===== 飞书卡片构建 =====

def build_trending_card_with_ai(ai_content: str) -> dict:
    """有 Kimi 筛选结果时，用 AI 内容构建卡片"""
    today = datetime.now().strftime("%Y-%m-%d")
    since_label = {"daily": "今日", "weekly": "本周", "monthly": "本月"}.get(
        TRENDING_SINCE, "今日"
    )
    lang_label = f" · {TRENDING_LANGUAGE}" if TRENDING_LANGUAGE else ""

    return {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": f"⭐ GitHub {since_label}热门{lang_label} · {today}",
                },
                "template": "green",
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": ai_content.strip(),
                    },
                },
                {"tag": "hr"},
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": (
                            f"[📊 查看完整 Trending →](https://github.com/trending"
                            f"{'/' + TRENDING_LANGUAGE if TRENDING_LANGUAGE else ''}"
                            f"?since={TRENDING_SINCE})"
                            f"\n_由 Kimi AI 为 Python/SQL 新手从今日 Top {MAX_REPOS} 中筛选_"
                        ),
                    },
                },
            ],
        },
    }


def build_trending_card_raw(repos: list[dict]) -> dict:
    """无 Kimi 时，直接列出原始 Trending 数据（取前 10）"""
    today = datetime.now().strftime("%Y-%m-%d")
    since_label = {"daily": "今日", "weekly": "本周", "monthly": "本月"}.get(
        TRENDING_SINCE, "今日"
    )

    lines = []
    for r in repos[:10]:
        lang_tag = f" `{r['language']}`" if r["language"] else ""
        stars_tag = f" ⭐+{r['stars_today']:,}" if r["stars_today"] else ""
        desc = f"\n  {r['description']}" if r["description"] else ""
        lines.append(f"• [{r['full_name']}]({r['url']}){lang_tag}{stars_tag}{desc}")

    return {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": f"⭐ GitHub {since_label}热门 · {today}",
                },
                "template": "green",
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": "\n".join(lines),
                    },
                },
                {"tag": "hr"},
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": (
                            f"[📊 查看完整 Trending →](https://github.com/trending"
                            f"{'/' + TRENDING_LANGUAGE if TRENDING_LANGUAGE else ''}"
                            f"?since={TRENDING_SINCE})"
                        ),
                    },
                },
            ],
        },
    }


# ===== 主流程 =====

def main():
    print("=" * 40)
    print("GitHub Trending → 飞书")
    print("=" * 40)

    # 1. 抓取
    try:
        repos = fetch_trending_repos(TRENDING_LANGUAGE, TRENDING_SINCE)
    except Exception as e:
        print(f"抓取失败: {e}")
        return

    if not repos:
        print("未获取到任何项目，退出")
        return

    # 2. Kimi 筛选（可选）
    ai_content = None
    if KIMI_API_KEY:
        print("正在调用 Kimi 筛选项目...")
        ai_content = kimi_filter_repos(repos)
    else:
        print("未配置 KIMI_API_KEY，跳过 AI 筛选，直接推送原始列表")

    # 3. 构建卡片
    if ai_content:
        card = build_trending_card_with_ai(ai_content)
    else:
        card = build_trending_card_raw(repos)

    # 4. 推送飞书
    if not FEISHU_WEBHOOK:
        print("未配置 FEISHU_WEBHOOK，仅打印卡片内容：")
        import json
        print(json.dumps(card, ensure_ascii=False, indent=2))
        return

    resp = requests.post(FEISHU_WEBHOOK, json=card, timeout=10)
    result = resp.json()
    print("飞书推送结果:", result.get("msg", result))


if __name__ == "__main__":
    main()
