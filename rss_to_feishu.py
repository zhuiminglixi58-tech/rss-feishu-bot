import requests
import re
import os
import base64
from datetime import datetime

# ===== Config =====
GITHUB_REPO       = "imjuya/juya-ai-daily"
FEISHU_WEBHOOK    = os.environ.get("FEISHU_WEBHOOK", "")
SERVERCHAN_KEY    = os.environ.get("SERVERCHAN_KEY", "")
FEISHU_APP_ID     = os.environ.get("FEISHU_APP_ID", "")
FEISHU_APP_SECRET = os.environ.get("FEISHU_APP_SECRET", "")
FEISHU_CHAT_ID    = os.environ.get("FEISHU_CHAT_ID", "")
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
            text = re.sub(r'`[^`]+`', '', text).strip()
            text = re.sub(r'\s*#\d+\s*$', '', text).strip()
            if text:
                sections[current_section].append({"text": text, "url": url})

    return sections


# ===== Kimi AI 解读 =====

def generate_ai_analysis(sections):
    """调用 Kimi API 对今日新闻生成解读"""
    today = datetime.now().strftime("%Y-%m-%d")

    # 整理新闻内容给 Kimi
    news_text = ""
    for title, items in sections.items():
        if not items:
            continue
        news_text += f"\n【{title}】\n"
        for item in items:
            news_text += f"- {item['text']}\n"

    prompt = f"""以下是{today}的AI科技早报内容：

{news_text}

请你作为一个AI行业观察者，用简洁易懂的语言为普通人解读今天的新闻：

1. 今日最值得关注的1-2个重大进展是什么？为什么重要？
2. 这些新闻背后反映了哪些行业趋势？
3. 对普通用户/从业者有什么实际影响？

要求：
- 语言通俗，避免堆砌专业术语
- 每个问题回答2-4句话，简洁有力
- 整体不超过300字
- 用"今日速览""趋势洞察""对你的影响"作为小标题"""

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
            overview_lines.append(f"• {text} [↗]({url})" if url else f"• {text}")
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


# ===== Server酱 =====

def push_to_serverchan(issue, sections):
    today = datetime.now().strftime("%Y-%m-%d")
    lines = []
    for title, items in sections.items():
        if not items:
            continue
        display_title = EMOJI_MAP.get(title, f"📌 {title}")
        lines.append(f"### {display_title}")
        for item in items:
            text = item["text"]
            url = item["url"]
            lines.append(f"- [{text}]({url})" if url else f"- {text}")
        lines.append("")
    lines.append(f"---\n[📖 查看完整原文]({issue['html_url']})")

    resp = requests.post(
        f"https://sctapi.ftqq.com/{SERVERCHAN_KEY}.send",
        data={"title": f"🤖 AI 早报 · {today}", "desp": "\n".join(lines).strip()},
        timeout=10
    )
    print("Server酱推送结果:", resp.json())


# ===== 飞书应用 API（发图片）=====

def get_feishu_token():
    resp = requests.post(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        json={"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET},
        timeout=10
    )
    data = resp.json()
    token = data.get("tenant_access_token", "")
    print(f"飞书 token: {'成功' if token else '失败'}")
    return token


def upload_image_to_feishu(image_path, token):
    with open(image_path, "rb") as f:
        resp = requests.post(
            "https://open.feishu.cn/open-apis/im/v1/images",
            headers={"Authorization": f"Bearer {token}"},
            data={"image_type": "message"},
            files={"image": f},
            timeout=30
        )
    data = resp.json()
    if data.get("code") == 0:
        image_key = data["data"]["image_key"]
        print(f"图片上传成功: {image_key}")
        return image_key
    else:
        print(f"图片上传失败: {data}")
        return None


def send_image_to_feishu(image_key, token):
    resp = requests.post(
        "https://open.feishu.cn/open-apis/im/v1/messages",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        params={"receive_id_type": "chat_id"},
        json={
            "receive_id": FEISHU_CHAT_ID,
            "msg_type": "image",
            "content": f'{{"image_key": "{image_key}"}}'
        },
        timeout=15
    )
    data = resp.json()
    print(f"飞书图片发送: {data.get('code')} {data.get('msg','')}")


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

    # ③ Server酱推送
    if SERVERCHAN_KEY:
        push_to_serverchan(issue, sections)

    # ④ 生成长图 → 上传飞书 → 发送图片
    if FEISHU_APP_ID and FEISHU_APP_SECRET and FEISHU_CHAT_ID:
        try:
            from generate_image import generate_image
            img_path = generate_image(issue, sections, "daily_report.png")
            token = get_feishu_token()
            if token:
                image_key = upload_image_to_feishu(img_path, token)
                if image_key:
                    send_image_to_feishu(image_key, token)
        except Exception as e:
            print(f"生图/推图失败: {e}")


if __name__ == "__main__":
    main()
