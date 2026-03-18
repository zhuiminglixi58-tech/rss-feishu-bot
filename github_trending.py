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

    seen = set()
    for article in articles:
        repo = _parse_article(article)
        if not repo:
            continue
        # 数据层去重
        if repo["full_name"] in seen:
            continue
        seen.add(repo["full_name"])
        repos.append(repo)
        if len(repos) >= MAX_REPOS:
            break

    # 按总 stars 降序——更能反映项目成熟度和社区认可度
    repos.sort(key=lambda r: r["total_stars"], reverse=True)

    print(f"解析到 {len(repos)} 个项目（已去重、按总 stars 排序）")
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


# ===== Kimi 输出去重 =====

def _dedup_kimi_output(text: str) -> str:
    """
    Kimi 有时会在输出里重复同一个项目。
    按空行切分成块，提取每块第一行的 owner/repo，去掉重复块。
    """
    blocks = re.split(r'\n{2,}', text.strip())
    seen = set()
    unique_blocks = []
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        # 从第一行提取 owner/repo（格式：**owner/repo**...）
        first_line = block.split('\n')[0]
        m = re.search(r'\*\*([^*]+/[^*]+)\*\*', first_line)
        key = m.group(1).strip() if m else first_line[:40]
        if key in seen:
            print(f"去重：跳过重复项目 {key}")
            continue
        seen.add(key)
        unique_blocks.append(block)
    return "\n\n".join(unique_blocks)


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
        line += f"\n   总 ⭐：{r['total_stars']:,}　今日新增 ⭐：{r['stars_today']:,}"
        repo_lines.append(line)

    repo_text = "\n\n".join(repo_lines)

    prompt = f"""以下是今天 GitHub Trending 的热门项目列表：

{repo_text}

请从中挑选 5 个最值得关注的项目，优先选择：
1. AI、大模型、Agent、RAG、多模态相关
2. 解决真实痛点的开发工具
3. 有技术突破的基础设施

每个项目严格按以下格式输出，不要多写任何内容：

**owner/repo**（语言）⭐ 总stars · 今日+新增
是什么：一句话，说清楚它能干什么（不超过20字）
亮点：一句话，说清楚为什么值得看（不超过25字）

严格要求：
- 5个项目之间空一行
- 不加序号，不加总结
- 不编造信息
- 每个 owner/repo 只能出现一次，绝对禁止重复
- 直接输出，无需开场白
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
                            "content": "你是一名关注 AI 与开发工具的技术博主，擅长用简单的中文介绍 GitHub 上的有趣项目。",
                        },
                        {"role": "user", "content": prompt},
                    ],
                },
                timeout=60,
            )

            data = resp.json()
            if data.get("choices"):
                raw = data["choices"][0]["message"]["content"]
                result = _dedup_kimi_output(raw)
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
                            f"\n_由 Kimi AI 从今日 Top {MAX_REPOS} 中筛选_"
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
