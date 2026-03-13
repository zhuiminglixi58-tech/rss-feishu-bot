import requests
import re
import os
from datetime import datetime

# ===== Config =====
GITHUB_REPO       = "imjuya/juya-ai-daily"
FEISHU_WEBHOOK    = os.environ.get("FEISHU_WEBHOOK", "")
KIMI_API_KEY      = os.environ.get("KIMI_API_KEY", "")

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
    sections = {}
    current_section = None
    in_overview = False

    for line in body.split('\n'):
        line = line.strip()
        if not line:
            continue
        if line.startswith('## ') and line[3:].strip() == '概览':
            in_overview = True
            continue
        if in_overview and line.startswith('## '):
            break
        if not in_overview:
            continue
        if line.startswith('### '):
            current_section = line[4:].strip()
            sections[current_section] = []
        elif (line.startswith('- ') or line.startswith('* ')) and current_section is not None:
            raw = line[2:].strip()
            url = None
            for m in re.finditer(r'\(([^)]+)\)', raw):
                c = m.group(1)
                if c.startswith('http'):
                    url = c
                    break

            text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', raw)
            text = re.sub(r'\(https?://[^\s)]+\)', '', text)
            text = re.sub(r'`[^`]+`', '', text).strip()
            text = re.sub(r'\s*#\d+\s*$', '', text).strip()
            text = re.sub(r'\s*[↗→➜➚⇗🔗]+[\s\u3000]*$', '', text).strip()

            if text:
                sections[current_section].append({"text": text, "url": url})

    return sections


# ===== Kimi AI 解读 =====

def generate_ai_analysis(sections):
    """调用 Kimi API 对今日新闻生成解读"""
    # 整理新闻内容给 Kimi
    news_text = ""
    for title, items in sections.items():
        if not items:
            continue
        news_text += f"\n【{title}】\n"
        for item in items:
            news_text += f"- {item['text']}\n"

    prompt = f"""以下是今天的 AI 科技早报内容：

{news_text}

请你作为一个“面向普通用户”的 AI 行业观察者，用简洁、清晰、适合飞书卡片阅读的中文，输出一份“今日 AI 解读”。

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

趋势洞察
2. 这些新闻背后反映了哪些行业趋势
- 必须分成 2-3 条 bullet，不要写成一整段
- 每条只讲 1 个趋势
- 每条都要包含两层意思：
  1. 趋势是什么
  2. 这说明了什么
- 每条 1-2 句话，语言直白，不要空泛

对你的影响
3. 从用户实际使用角度解读
- 必须分成 3 条 bullet，且固定为以下三部分：
  - Claude：
  - ChatGPT：
  - 其他好用产品：
- Claude：
  - 只解读今天新闻里和 Claude 相关的功能更新
  - 重点说明这个更新对普通用户日常使用有什么影响
  - 例如写作、总结、协作、信息整理、效率提升等
  - 如果当天没有明确的 Claude 功能更新，就直接写：
    - Claude：今天没有特别重大的功能更新，更值得关注的是……
- ChatGPT：
  - 只解读今天新闻里和 ChatGPT / OpenAI 相关的功能更新
  - 重点说明这个更新对普通用户日常使用有什么影响
  - 例如搜索、写作、学习、办公、图片/视频处理等
  - 如果当天没有明确的 ChatGPT / OpenAI 功能更新，就直接写：
    - ChatGPT：今天没有特别重大的功能更新，更值得关注的是……
- 其他好用产品：
  - 不要泛泛罗列产品名
  - 优先挑选“普通用户今天就可能用到”的功能更新
  - 优先关注这些方向：搜索、地图、办公、写作、编程、健康、效率工具、图片/视频处理
  - 只挑 2-3 个最实用的产品或功能
  - 对每个产品/功能都要说明：
    1. 更新了什么
    2. 日常生活、学习或工作里能怎么用
    3. 值不值得关注
  - 如果当天没有特别适合普通用户的实用更新，就直接写：
    - 其他好用产品：今天没有特别强的日常工具更新，更偏行业或技术层面

额外要求：
1. 全文控制在 250-350 字左右
2. 一定要分条展示，不要出现大段连续文字
3. 每条尽量短，适合手机上快速阅读
4. 语言通俗，不要堆砌专业术语，不要像研报
5. 不要编造新闻里没有出现的产品、功能或结论
6. 输出内容要有“筛选感”，不是把新闻复述一遍，而是帮我挑出最值得我关注的点
7. 第三部分尤其要突出：哪些更新是我日常真的可能用上的，哪些只是行业新闻但和我关系不大

请直接输出最终内容，不要解释思路，不要加开场白，不要加“当然可以”，不要加任何额外说明。

输出格式示例（仅参考格式，不要照抄内容）：

今日速览
1. 最值得关注的 3 个重大进展
- XXX：这意味着……
- XXX：这说明……
- XXX：普通用户可以关注……

趋势洞察
2. 背后趋势
- XXX：说明行业正在……
- XXX：说明产品正在……
- XXX：说明竞争正在……

对你的影响
3. 从使用角度看
- Claude：……
- ChatGPT：……
- 其他好用产品：……"""

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
    else:
        print("AI 解读生成失败:", data)
        return None


def build_analysis_card(analysis):
    """构建 AI 解读飞书卡片"""
    today = datetime.now().strftime("%Y-%m-%d")

    # 把解读文字按小标题分段，转成飞书 Markdown
    content = analysis.strip()

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
                        "content": content
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

    # ② 推送飞书 AI 解读卡片（第二条消息）
    if FEISHU_WEBHOOK and KIMI_API_KEY:
        print("正在生成 AI 解读...")
        analysis = generate_ai_analysis(sections)
        if analysis:
            analysis_card = build_analysis_card(analysis)
            resp = requests.post(FEISHU_WEBHOOK, json=analysis_card, timeout=10)
            print("飞书 AI 解读卡片:", resp.json().get("msg", ""))

    elif FEISHU_WEBHOOK and not KIMI_API_KEY:
        print("跳过 AI 解读：未配置 KIMI_API_KEY")

if __name__ == "__main__":
    main()
