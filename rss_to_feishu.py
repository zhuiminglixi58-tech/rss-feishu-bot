import os
import json
import re
import requests
import feedparser

# ---------------- 配置 ----------------
RSS_URL = os.environ.get("RSS_URL", "https://imjuya.github.io/juya-ai-daily/rss.xml")
FEISHU_WEBHOOK = os.environ.get("FEISHU_WEBHOOK")
STATE_FILE = "state.json"

# 手动测试模式：强制推送（忽略 state.json）
FORCE_SEND = os.environ.get("FORCE_SEND", "false").lower() == "true"
FORCE_ITEMS = int(os.environ.get("FORCE_ITEMS", "3"))

# 正常模式：每次最多推送几条新内容
MAX_ITEMS_PER_RUN = int(os.environ.get("MAX_ITEMS_PER_RUN", "5"))

# 网络超时
TIMEOUT = int(os.environ.get("TIMEOUT", "15"))

# 卡片显示摘要（1=显示，0=不显示）
INCLUDE_SUMMARY = os.environ.get("INCLUDE_SUMMARY", "0") == "1"
SUMMARY_MAX_LEN = int(os.environ.get("SUMMARY_MAX_LEN", "140"))

# 没有新内容时是否也发提示（可选：1=发提示，0=不发）
ALWAYS_NOTIFY = os.environ.get("ALWAYS_NOTIFY", "0") == "1"


# ---------------- 新闻分类与摘要构建 ----------------
CATEGORIES = {
    "资本与产业": ["融资", "投资", "并购", "领投", "估值", "政策"],
    "安全与伦理": ["安全", "国防", "伦理", "监管", "政府"],
    "开源与工具": ["开源", "发布", "模型", "工具", "LoRA"],
    "医疗应用": ["医疗", "脑机", "临床", "医院"],
    "AI for Science": ["物理", "材料", "数学", "科研"],
}

LEAD_SENTENCE = "近期AI领域资本与伦理议题频出，同时开源生态持续活跃，医疗应用与 AI for Science 也在加速落地。"


def classify_news(item: dict) -> str:
    text = f"{(item.get('title') or '').strip()} {(item.get('summary') or '').strip()}".lower()
    for category, keywords in CATEGORIES.items():
        for keyword in keywords:
            if keyword.lower() in text:
                return category
    return "其他"


def build_structured_digest(items: list[dict]) -> str:
    grouped = {category: [] for category in CATEGORIES}
    grouped["其他"] = []

    for item in items:
        category = classify_news(item)
        title = (item.get("title") or "(无标题)").strip()
        grouped.setdefault(category, []).append(f"- {title}")

    sections = [LEAD_SENTENCE]
    for category in [*CATEGORIES.keys(), "其他"]:
        news_lines = grouped.get(category, [])
        if news_lines:
            sections.append(f"**{category}**")
            sections.extend(news_lines)

    return "\n\n".join(sections)


# ---------------- 状态读写（去重） ----------------
def load_state():
    if not os.path.exists(STATE_FILE):
        return {"last_id": ""}
    with open(STATE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def entry_id(entry):
    # 尽量稳定地取唯一标识
    return getattr(entry, "id", None) or getattr(entry, "guid", None) or getattr(entry, "link", "")


# ---------------- 飞书推送（卡片） ----------------
def format_item_content(title: str, link: str, summary: str) -> str:
    """格式化单条推送内容，优先把 AI 早报标题拆成更易读的多行。"""
    content = title.strip() or "(无标题)"

    # 兼容「YYYY-MM-DD - AI 早报 ... 概览 ... #1 ... #2」格式
    match = re.match(r"^(\d{4}-\d{2}-\d{2})\s*-\s*AI\s*早报", content)
    if match:
        date = match.group(1)
        lines = [f"{date} - AI 早报"]

        # 优先展示“概览”后的分段内容
        overview = content.split("概览", 1)[1].strip() if "概览" in content else ""
        if overview:
            for seg in re.finditer(r"(.*?)(?:\s*#(\d+))(?:\s+|$)", overview):
                text = (seg.group(1) or "").strip()
                idx = seg.group(2)
                if text and idx:
                    lines.append(f"{text} #{idx}")

        if len(lines) > 1:
            content = "\n".join(lines)

    if link:
        content = f"[{content}]({link})"

    if INCLUDE_SUMMARY and summary:
        if len(summary) > SUMMARY_MAX_LEN:
            summary = summary[:SUMMARY_MAX_LEN] + "…"
        content += f"\n{summary}"

    return content


def feishu_send_card(card_title: str, items: list[dict], custom_markdown: str | None = None):
    """
    items: [{"title": "...", "link": "...", "summary": "..."}]
    """
    if not FEISHU_WEBHOOK:
        raise RuntimeError("Missing FEISHU_WEBHOOK (set it in GitHub Secrets).")

    elements = []
    if custom_markdown is not None:
        elements.append({
            "tag": "div",
            "text": {"tag": "lark_md", "content": custom_markdown}
        })
    else:
        for item in items:
            title = item.get("title", "(无标题)")
            link = item.get("link", "")
            summary = (item.get("summary") or "").strip()

            md = format_item_content(title=title, link=link, summary=summary)

            elements.append({
                "tag": "div",
                "text": {"tag": "lark_md", "content": md}
            })

    payload = {
        "msg_type": "interactive",
        "card": {
            "header": {"title": {"tag": "plain_text", "content": card_title}},
            "elements": elements
        }
    }

    resp = requests.post(FEISHU_WEBHOOK, json=payload, timeout=TIMEOUT)
    resp.raise_for_status()


# ---------------- 主逻辑 ----------------
def main():
    state = load_state()
    last_id = state.get("last_id", "")

    feed = feedparser.parse(RSS_URL)
    entries = getattr(feed, "entries", []) or []

    if not entries:
        feishu_send_card("RSS 机器人", [{
            "title": "未获取到内容",
            "link": RSS_URL,
            "summary": "请检查 RSS 链接是否可访问，或稍后再试。"
        }])
        return

    # 选择本次要推送的条目列表
    if FORCE_SEND:
        # 手动测试：忽略去重，强制推最新 N 条
        new_entries = entries[:max(1, FORCE_ITEMS)]
    else:
        # 正常：只推送 last_id 之后的新内容
        new_entries = []
        for e in entries:
            if entry_id(e) == last_id:
                break
            new_entries.append(e)

        # 首次运行只推 1 条，防止刷屏
        if not last_id:
            new_entries = new_entries[:1]
        else:
            new_entries = new_entries[:MAX_ITEMS_PER_RUN]

    # 没有新内容：默认不发（除非 ALWAYS_NOTIFY=1）
    if not new_entries:
        if ALWAYS_NOTIFY:
            feishu_send_card("AI早报更新", [{
                "title": "暂无更新",
                "link": RSS_URL,
                "summary": "本次运行未发现新条目。"
            }])
        return

    # 为了阅读体验：按旧->新展示（RSS 通常是新->旧）
    new_entries.reverse()

    items = []
    for e in new_entries:
        title = getattr(e, "title", "(无标题)")
        link = getattr(e, "link", "")
        summary = (getattr(e, "summary", "") or "").strip()
        items.append({"title": title, "link": link, "summary": summary})

    # 卡片标题：强制推送时标记为“测试”
    card_title = "AI早报更新（测试）" if FORCE_SEND else "AI早报更新"
    digest = build_structured_digest(items)
    feishu_send_card(card_title, [], custom_markdown=digest)

    # 更新状态：记录 RSS 当前最新的一条（entries[0] 是最新）
    state["last_id"] = entry_id(entries[0])
    save_state(state)


if __name__ == "__main__":
    main()
