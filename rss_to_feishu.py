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


# ===== 飞书 API =====

def get_feishu_token():
    """获取飞书 tenant_access_token"""
    resp = requests.post(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        json={"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET},
        timeout=10
    )
    data = resp.json()
    token = data.get("tenant_access_token", "")
    print(f"获取飞书 token: {'成功' if token else '失败'} {data.get('msg','')}")
    return token


def upload_image_to_feishu(image_path, token):
    """上传图片到飞书，返回 image_key"""
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
        print(f"图片上传成功，image_key: {image_key}")
        return image_key
    else:
        print(f"图片上传失败: {data}")
        return None


def send_image_to_feishu_group(image_key, token):
    """通过飞书 API 发送图片消息到群"""
    resp = requests.post(
        "https://open.feishu.cn/open-apis/im/v1/messages",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        },
        params={"receive_id_type": "chat_id"},
        json={
            "receive_id": FEISHU_CHAT_ID,
            "msg_type": "image",
            "content": f'{{"image_key": "{image_key}"}}'
        },
        timeout=15
    )
    data = resp.json()
    print(f"飞书图片消息发送结果: {data.get('code')} {data.get('msg','')}")
    return data.get("code") == 0


# ===== 飞书 Webhook 文字卡片 =====

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

    # 1. 飞书 Webhook 推送文字卡片
    if FEISHU_WEBHOOK:
        card = build_feishu_card(issue, sections)
        resp = requests.post(FEISHU_WEBHOOK, json=card, timeout=10)
        print("飞书文字卡片:", resp.json())

    # 2. Server酱推送（微信提醒）
    if SERVERCHAN_KEY:
        push_to_serverchan(issue, sections)

    # 3. 生成长图 → 上传飞书 → 发送图片到群
    if FEISHU_APP_ID and FEISHU_APP_SECRET and FEISHU_CHAT_ID:
        try:
            from generate_image import generate_image
            img_path = generate_image(issue, sections, "daily_report.png")

            token = get_feishu_token()
            if token:
                image_key = upload_image_to_feishu(img_path, token)
                if image_key:
                    send_image_to_feishu_group(image_key, token)
        except Exception as e:
            print(f"生图/推图失败: {e}")
    else:
        print("飞书应用凭证未配置，跳过图片推送")


if __name__ == "__main__":
    main()
