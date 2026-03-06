import requests
import re
import os
from datetime import datetime

# ===== 配置 =====
GITHUB_REPO = "imjuya/juya-ai-daily"
FEISHU_WEBHOOK = os.environ.get("FEISHU_WEBHOOK", "")

def get_latest_issue():
    """通过 GitHub API 获取最新一期 Issue"""
    url = f"https://api.github.com/repos/{GITHUB_REPO}/issues"
    params = {"state": "open", "per_page": 1, "sort": "created", "direction": "desc"}
    headers = {"Accept": "application/vnd.github.v3+json"}
    # 如果有 GITHUB_TOKEN 可以加，避免 API 限速
    token = os.environ.get("GITHUB_TOKEN", "")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    resp = requests.get(url, params=params, headers=headers, timeout=15)
    issues = resp.json()
    return issues[0] if issues else None

def parse_markdown(body):
    """解析 Issue Markdown，按 ## 标题分类提取条目"""
    sections = {}
    current_section = None

    for line in body.split('\n'):
        line = line.strip()
        if not line:
            continue
        # ## 标题 = 分类
        if line.startswith('## '):
            current_section = line[3:].strip()
            sections[current_section] = []
        # ### 子标题跳过
        elif line.startswith('###'):
            continue
        # 列表条目
        elif (line.startswith('- ') or line.startswith('* ')) and current_section is not None:
            text = line[2:].strip()
            # 去掉 Markdown 链接，保留文字: [文字](url) → 文字
            text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
            # 去掉行内代码
            text = re.sub(r'`[^`]+`', '', text).strip()
            # 去掉 #数字 标签（如 #1 #2）
            text = re.sub(r'\s*#\d+\s*$', '', text).strip()
            if text:
                sections[current_section].append(text)

    return sections

def build_feishu_card(issue, sections):
    """构建飞书交互卡片"""
    today = datetime.now().strftime("%Y-%m-%d")
    elements = []

    for title, items in sections.items():
        if not items:
            continue

        # 分类标题
        elements.append({
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": f"**📌 {title}**"
            }
        })

        # 条目内容
        content_lines = "\n".join([f"• {item}" for item in items])
        elements.append({
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": content_lines
            }
        })

        # 分割线
        elements.append({"tag": "hr"})

    # 底部跳转原文
    elements.append({
        "tag": "div",
        "text": {
            "tag": "lark_md",
            "content": f"[📖 查看完整原文 →]({issue['html_url']})"
        }
    })

    return {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": f"🤖 AI 早报 · {today}"
                },
                "template": "blue"
            },
            "elements": elements
        }
    }

def main():
    if not FEISHU_WEBHOOK:
        print("❌ 未配置 FEISHU_WEBHOOK")
        return

    print("📡 正在获取最新 Issue...")
    issue = get_latest_issue()
    if not issue:
        print("❌ 未找到 Issue")
        return

    print(f"✅ 获取到: {issue['title']}")
    sections = parse_markdown(issue['body'])
    print(f"✅ 解析到 {len(sections)} 个分类: {list(sections.keys())}")

    card = build_feishu_card(issue, sections)
    resp = requests.post(FEISHU_WEBHOOK, json=card, timeout=10)
    result = resp.json()
    print("📨 推送结果:", result)

if __name__ == "__main__":
    main()
