"""
rss_to_feishu.py

从 GitHub Issues 获取 AI 日报内容，结合 Industry News 和 GitHub Trending，
调用 Kimi AI 生成解读，最终推送到飞书 Webhook。
"""

import requests
import re
import os
import sys
import time
from datetime import datetime

# ===== 配置 =====
GITHUB_REPO       = "imjuya/juya-ai-daily"           # 数据来源的 GitHub 仓库
FEISHU_WEBHOOK    = os.environ.get("FEISHU_WEBHOOK", "")  # 飞书机器人 Webhook 地址
KIMI_API_KEY      = os.environ.get("KIMI_API_KEY", "")    # Kimi AI API Key

# 各分类对应的带 Emoji 显示标题
EMOJI_MAP = {
    "要闻":            "🗞️ 要闻",
    "模型发布":         "🚀 模型发布",
    "开发生态":         "🛠️ 开发生态",
    "技术与洞察":       "🔬 技术与洞察",
    "行业动态":         "📊 行业动态",
    "前瞻与传闻":       "🔮 前瞻与传闻",
    "AI for Science":  "🧪 AI for Science",
    "具身智能":         "🤖 具身智能",
    "AI音乐":          "🎵 AI音乐",
    "AI绘画":          "🎨 AI绘画",
    "AI视频":          "🎬 AI视频",
    "工具推荐":         "⚙️ 工具推荐",
    "产品动态":         "📱 产品动态",
}


# ===== 数据获取 =====

def get_latest_issue():
    """从 GitHub API 获取指定仓库最新的一条 open issue。"""
    url = f"https://api.github.com/repos/{GITHUB_REPO}/issues"
    params = {"state": "open", "per_page": 1, "sort": "created", "direction": "desc"}
    headers = {"Accept": "application/vnd.github.v3+json"}
    token = os.environ.get("GITHUB_TOKEN", "")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    resp = requests.get(url, params=params, headers=headers, timeout=15)
    issues = resp.json()
    return issues[0] if issues else None


def extract_overview(body):
    """
    从 issue body（Markdown 格式）中提取"概览"章节的内容。

    Issue 格式：
    - `# 概览` 一级标题标志概览开始
    - `## 要闻` 等二级标题作为分类
    - `- 条目` 列表作为新闻条目

    返回：
        dict，结构为 { 分类名: [{"text": str, "url": str|None}, ...] }
    """
    sections = {}
    current_section = None
    in_overview = False

    if not body:
        return sections

    print(f"Body前500字: {repr(body[:500])}")
    for line in body.split('\n'):
        line = line.strip()
        if not line:
            continue

        # 进入"概览"章节（一级标题 # 概览）
        if line.startswith('# ') and line[2:].strip() == '概览':
            in_overview = True
            continue

        # 遇到下一个一级标题，退出概览解析
        if in_overview and line.startswith('# ') and line[2:].strip() != '概览':
            break

        if not in_overview:
            continue

        # 二级标题作为分类名（## 要闻、## 模型发布 等）
        if line.startswith('## '):
            current_section = line[3:].strip()
            sections[current_section] = []
        # 列表条目：提取文本和链接
        elif (line.startswith('- ') or line.startswith('* ')) and current_section is not None:
            raw = line[2:].strip()

            # 从括号内容中提取第一个 http 链接
            url = None
            for m in re.finditer(r'\(([^)]+)\)', raw):
                c = m.group(1)
                if c.startswith('http'):
                    url = c
                    break

            # 去除 Markdown 链接语法，保留纯文本
            text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', raw)
            text = re.sub(r'\(https?://[^\s)]+\)', '', text)
            text = re.sub(r'`[^`]+`', '', text).strip()
            # 去除末尾的 issue 编号（如 #42）
            text = re.sub(r'\s*#\d+\s*$', '', text).strip()
            # 去除末尾的箭头/链接符号
            text = re.sub(r'\s*[↗→➜➚⇗🔗]+[\s\u3000]*$', '', text).strip()

            if text:
                sections[current_section].append({"text": text, "url": url})

    return sections


# ===== Industry News 读取 =====

def read_industry_news() -> str | None:
    """
    读取 reports/ 目录下最新的 ai_digest_*.md 文件内容。
    """
    reports_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reports")
    if not os.path.isdir(reports_dir):
        return None
    files = sorted(
        [f for f in os.listdir(reports_dir) if f.startswith("ai_digest_") and f.endswith(".md")],
        reverse=True
    )
    if not files:
        return None
    latest = os.path.join(reports_dir, files[0])
    print(f"读取 Industry News: {files[0]}")
    with open(latest, encoding="utf-8") as f:
        return f.read().strip()


# ===== Kimi AI 解读 =====

def generate_ai_analysis(sections, trending_repos=None, industry_news=None):
    """
    调用 Kimi API，综合三个信息源生成今日 AI 解读。
    """
    # 信息源 1：橘子早报
    news_text = ""
    for title, items in sections.items():
        if not items:
            continue
        news_text += f"\n【{title}】\n"
        for item in items:
            news_text += f"- {item['text']}\n"

    # 信息源 2：Industry News
    industry_text = ""
    if industry_news:
        industry_text = f"\n\n【行业动态 · 商业视角】\n{industry_news}"

    # 信息源 3：GitHub trending
    trending_text = ""
    if trending_repos:
        trending_text = "\n\n【GitHub 今日热门项目】\n"
        for r in trending_repos[:15]:
            lang = f"（{r['language']}）" if r.get("language") else ""
            stars = f" ⭐+{r['stars_today']:,}" if r.get("stars_today") else ""
            desc = f"：{r['description']}" if r.get("description") else ""
            trending_text += f"- {r['full_name']}{lang}{stars}{desc}\n"

    combined_input = news_text + industry_text + trending_text

    sources_desc = "1. 橘子早报（AI 技术动态）"
    if industry_news:
        sources_desc += "\n2. Industry News（商业视角行业动态，含资本、伦理、产业政策）"
    if trending_repos:
        sources_desc += "\n3. GitHub Trending（今日热门开源项目）"

    prompt = f"""以下是今天的多个信息源内容：
{sources_desc}

{combined_input}

请你作为一个"面向普通用户"的 AI 行业观察者，用简洁、清晰、适合飞书卡片阅读的中文，输出一份"今日 AI 解读"，综合涵盖以上所有信息源。

我的目标不是长分析，而是：分条展示、清晰可读、一眼能扫完，并且尽量贴近日常使用场景。

请严格按照下面结构输出，不要自由发挥格式，不要写成长段落：

今日速览
1. 最值得关注的 3 个重大进展
- 必须用 3 条 bullet 分别写
- 每条只讲 1 个进展
- 每条都要包含两层意思：
  1. 发生了什么
  2. 为什么值得关注
- 每条 1-2 句话，尽量短，适合快速阅读
- 注意：这里可以优先选择行业影响最大的新闻，不要求覆盖 Claude 或 ChatGPT

商业视角
2. 从 Industry News 提炼 2-3 条商业层面的关键动态
- 覆盖资本、产业政策、伦理监管等方向
- 每条说明：发生了什么 + 对行业意味着什么
- 如果没有提供 Industry News 数据，跳过此部分

趋势洞察
3. 综合所有信息源，反映了哪些行业趋势
- 必须分成 2-3 条 bullet，不要写成一整段
- 每条只讲 1 个趋势
- 每条都要包含两层意思：
  1. 趋势是什么
  2. 这说明了什么
- 每条 1-2 句话，语言直白，不要空泛

对你的影响
4. 从用户实际使用角度解读（重点部分）

⚠️ 本部分必须完整覆盖产品功能更新，并对重要程度进行星级排序。

必须固定分成 3 个小节：

- Claude：
- ChatGPT（包含 OpenAI、ChatGPT、Codex 等产品）：
- 其他好用产品：

Claude：
- 必须总结今天新闻里出现的所有 Claude 相关功能更新，不能遗漏
- 每个功能更新前必须添加重要程度星级：
  ⭐⭐⭐ 强烈建议关注（明显改变使用方式 / 效率提升巨大）
  ⭐⭐ 可以了解（对部分人群有用 / 中等提升）
  ⭐ 行业参考（偏技术或轻量更新）
- 每条更新需要说明：
  1. 更新了什么能力
  2. 日常可以怎么用
  3. 是否值得普通用户关注
- 如果当天没有 Claude 功能更新，明确写：
  Claude：今天没有明确的产品功能更新

ChatGPT（包含 OpenAI、ChatGPT、Codex 等）：
- 必须总结今天所有属于 OpenAI 产品体系的功能更新
- 包括：ChatGPT 产品能力、Codex / 编程能力、OpenAI API / 多模态能力、Agent / 自动化 / UI 能力
- 每条更新必须加星级：
  ⭐⭐⭐ 强烈建议关注（普通用户马上能感知变化）
  ⭐⭐ 可以了解（对特定场景明显有用）
  ⭐ 行业参考（偏开发者或行业层面）
- 每条更新需要说明：
  1. 更新了什么
  2. 日常能怎么用
  3. 是否值得关注
- 如果当天没有 OpenAI 产品更新，明确写：
  ChatGPT：今天没有明确的产品功能更新

其他好用产品：
- 只挑选 2–3 个普通用户今天就可能用到的更新
- 不需要打星级
- 但要说明：更新内容 + 使用场景 + 是否值得关注

今日 GitHub 热门
5. 从 GitHub 热门项目中挑出 2-3 个最值得关注的
- 每条说明：项目名 + 是什么 + 对普通用户有什么用
- 优先选 Python/AI 相关、普通人能用到的项目
- 如果没有提供 GitHub 数据，跳过此部分

额外要求：
1. 全文控制在 350-500 字
2. 必须全部分条展示
3. 不允许出现长段落
4. 用手机阅读友好的短句
5. 不要像行业研报
6. 不要编造新闻
7. Claude 和 ChatGPT 体系功能更新 **必须完整覆盖**
8. 不允许漏掉 Codex / OpenAI 编程类更新
9. 输出要有"帮我筛选"的感觉，而不是简单复述

请直接输出最终内容。
不要解释思路。
不要加开场白。
不要加"当然可以"。
不要添加任何额外说明。
"""
    max_retries = 3
    base_delay_seconds = 2

    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.post(
                "https://api.moonshot.cn/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {KIMI_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "moonshot-v1-8k",
                    "temperature": 0.6,
                    "max_tokens": 1024,
                    "messages": [
                        {
                            "role": "system",
                            "content": "你是一名中文科技资讯分析师，擅长把复杂 AI 新闻讲清楚。"
                        },
                        {"role": "user", "content": prompt}
                    ]
                },
                timeout=60
            )

            data = resp.json()
            if data.get("choices"):
                analysis = data["choices"][0]["message"]["content"]
                print("AI 解读生成成功")
                return analysis

            error_type = data.get("error", {}).get("type", "")
            should_retry = error_type in {
                "engine_overloaded_error",
                "rate_limit_reached_error",
                "service_unavailable_error"
            }
            print(f"AI 解读生成失败（第 {attempt}/{max_retries} 次）:", data)

            if attempt == max_retries or not should_retry:
                return None

        except requests.RequestException as exc:
            print(f"调用 Kimi 接口异常（第 {attempt}/{max_retries} 次）: {exc}")
            if attempt == max_retries:
                return None

        delay = base_delay_seconds * (2 ** (attempt - 1))
        print(f"{delay} 秒后重试 AI 解读...")
        time.sleep(delay)

    return None


def build_analysis_card(analysis):
    """构建 AI 解读飞书交互卡片。"""
    today = datetime.now().strftime("%Y-%m-%d")
    return {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": f"🧠 今日 AI 解读 · {today}"},
                "template": "purple"
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": analysis.strip()
                    }
                },
                {"tag": "hr"},
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": "_以上解读由 Kimi AI 自动生成，仅供参考_"
                    }
                }
            ]
        }
    }


# ===== 飞书 Webhook 早报卡片 =====

def build_feishu_card(issue, sections):
    """构建 AI 早报飞书交互卡片。"""
    today = datetime.now().strftime("%Y-%m-%d")
    overview_lines = []
    for title, items in sections.items():
        if not items:
            continue
        display_title = EMOJI_MAP.get(title, f"📌 {title}")
        overview_lines.append(f"**{display_title}**")
        for item in items:
            text = item["text"]
            url = item["url"]
            overview_lines.append(f"• {text} [🔗]({url})" if url else f"• {text}")
        overview_lines.append("")

    return {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": f"🤖 AI 早报 · {today}"},
                "template": "blue"
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {"tag": "lark_md", "content": "\n".join(overview_lines).strip()}
                },
                {"tag": "hr"},
                {
                    "tag": "div",
                    "text": {"tag": "lark_md", "content": f"[📖 查看完整原文 →]({issue['html_url']})"}
                }
            ]
        }
    }


# ===== 主流程 =====

def main():
    print("Fetching latest issue...")
    issue = get_latest_issue()
    if not issue:
        print("No issue found")
        return

    print(f"Got: {issue['title']}")
    print("===BODY START===")
    print(issue['body'][:800] if issue['body'] else "BODY IS NONE")
    print("===BODY END===")
    sections = extract_overview(issue['body'])
    print(f"Parsed {len(sections)} sections: {list(sections.keys())}")

    if not sections:
        print("Warning: no overview sections found")
        return

    # ① 推送飞书早报卡片
    if FEISHU_WEBHOOK:
        card = build_feishu_card(issue, sections)
        resp = requests.post(FEISHU_WEBHOOK, json=card, timeout=10)
        print("飞书早报卡片:", resp.json().get("msg", ""))

    # ② 推送飞书 AI 解读卡片（综合三个信息源）
    if FEISHU_WEBHOOK and KIMI_API_KEY:
        industry_news = read_industry_news()
        if not industry_news:
            print("未找到 Industry News 文件，将跳过该信息源")

        trending_repos = None
        try:
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            from github_trending import fetch_trending_repos
            print("正在抓取 GitHub trending 数据...")
            trending_repos = fetch_trending_repos("", "daily")
        except Exception as e:
            print(f"GitHub trending 抓取失败，将跳过该信息源: {e}")

        print("正在生成综合 AI 解读（橘子早报 + Industry News + GitHub trending）...")
        analysis = generate_ai_analysis(sections, trending_repos, industry_news)
        if analysis:
            analysis_card = build_analysis_card(analysis)
            resp = requests.post(FEISHU_WEBHOOK, json=analysis_card, timeout=10)
            print("飞书 AI 解读卡片:", resp.json().get("msg", ""))

    elif FEISHU_WEBHOOK and not KIMI_API_KEY:
        print("跳过 AI 解读：未配置 KIMI_API_KEY")


if __name__ == "__main__":
    main()
