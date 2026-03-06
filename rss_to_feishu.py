import json
import os
import re
from html import unescape

import feedparser
import requests

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

# 结构化摘要中每条新闻展示的要点数量
DIGEST_POINTS_PER_ITEM = int(os.environ.get("DIGEST_POINTS_PER_ITEM", "2"))

# 每个分类最多展示多少条原文新闻
MAX_NEWS_PER_CATEGORY = int(os.environ.get("MAX_NEWS_PER_CATEGORY", "5"))

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

HEADING_TO_CATEGORY = {
    "资本与产业": "资本与产业",
    "安全与伦理": "安全与伦理",
    "开源与工具": "开源与工具",
    "医疗应用": "医疗应用",
    "AI for Science": "AI for Science",
}

LEAD_SENTENCE = "以下为 AI 早报原版要点分类整理，点击标题可直达原文。"


def classify_news(item: dict) -> str:
    preset = (item.get("category") or "").strip()
    if preset:
        return preset

    text = f"{(item.get('title') or '').strip()} {(item.get('summary') or '').strip()}".lower()
    for category, keywords in CATEGORIES.items():
        for keyword in keywords:
            if keyword.lower() in text:
                return category
    return "其他"


def markdown_link_to_text_and_url(text: str) -> tuple[str, str]:
    match = re.search(r"\[([^\]]+)\]\((https?://[^)]+)\)", text)
    if not match:
        return text.strip(), ""
    return match.group(1).strip(), match.group(2).strip()


def extract_summary_points(summary: str, max_points: int = 2) -> list[str]:
    if not summary or max_points <= 0:
        return []

    text = unescape(summary)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</(p|li|h\d)>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text).strip()

    if not text:
        return []

    candidates = re.split(r"[；;。.!?！？]\s*", text)
    points = []
    for seg in candidates:
        seg = seg.strip(" -•\t\n\r")
        if len(seg) < 10:
            continue
        if seg in points:
            continue
        points.append(seg)
        if len(points) >= max_points:
            break

    return points


def build_structured_digest(items: list[dict], source_links: list[str] | None = None) -> str:
    grouped = {category: [] for category in CATEGORIES}
    grouped["其他"] = []
    category_counter: dict[str, int] = {}

    for item in items:
        category = classify_news(item)
        if category_counter.get(category, 0) >= MAX_NEWS_PER_CATEGORY:
            continue

        title = (item.get("title") or "(无标题)").strip()
        link = (item.get("link") or "").strip()
        published = (item.get("published") or "").strip()
        summary = (item.get("summary") or "").strip()

        title_line = f"- [{title}]({link})" if link else f"- {title}"
        if published:
            title_line += f"（{published}）"

        detail_lines = [title_line]
        for point in extract_summary_points(summary, DIGEST_POINTS_PER_ITEM):
            if point == title:
                continue
            detail_lines.append(f"  - {point}")

        grouped.setdefault(category, []).append("\n".join(detail_lines))
        category_counter[category] = category_counter.get(category, 0) + 1

    sections = [LEAD_SENTENCE]
    if source_links:
        sections.append("来源：" + " | ".join([f"[原文]({u})" for u in source_links]))

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
    return getattr(entry, "id", None) or getattr(entry, "guid", None) or getattr(entry, "link", "")


def title_to_date(title: str) -> str:
    match = re.search(r"(\d{4}-\d{2}-\d{2})", title or "")
    return match.group(1) if match else ""


def candidate_markdown_urls(entry) -> list[str]:
    candidates = []
    title = getattr(entry, "title", "") or ""
    date_str = title_to_date(title)
    link = (getattr(entry, "link", "") or "").strip()

    if date_str:
        candidates.append(f"https://raw.githubusercontent.com/imjuya/juya-ai-daily/main/reports/ai_digest_{date_str}.md")

    if "github.com/imjuya/juya-ai-daily/blob/" in link:
        candidates.append(link.replace("github.com", "raw.githubusercontent.com").replace("/blob/", "/"))

    if link.endswith(".md"):
        candidates.append(link)

    # 去重并保留顺序
    seen = set()
    ordered = []
    for u in candidates:
        if u not in seen:
            ordered.append(u)
            seen.add(u)
    return ordered


def fetch_original_digest_items(entry) -> tuple[list[dict], str]:
    for url in candidate_markdown_urls(entry):
        try:
            resp = requests.get(url, timeout=TIMEOUT)
            if resp.status_code != 200 or not resp.text.strip():
                continue
            items = parse_digest_markdown(resp.text, getattr(entry, "published", "") or "")
            if items:
                return items, url
        except requests.RequestException:
            continue
    return [], ""


def parse_digest_markdown(markdown_text: str, published: str = "") -> list[dict]:
    items = []
    current_category = ""

    for raw_line in markdown_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        heading_match = re.match(r"^##\s+(.+)$", line)
        if heading_match:
            heading = heading_match.group(1).strip()
            current_category = HEADING_TO_CATEGORY.get(heading, heading)
            continue

        bullet_match = re.match(r"^-\s+(.+)$", line)
        if not bullet_match:
            continue

        bullet_text = bullet_match.group(1).strip()
        title, link = markdown_link_to_text_and_url(bullet_text)
        cleaned = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r"\1", bullet_text).strip()

        items.append({
            "title": title or cleaned,
            "link": link,
            "summary": cleaned,
            "published": published,
            "category": current_category or "其他",
        })

    return items


def feishu_send_card(card_title: str, custom_markdown: str):
    if not FEISHU_WEBHOOK:
        raise RuntimeError("Missing FEISHU_WEBHOOK (set it in GitHub Secrets).")

    payload = {
        "msg_type": "interactive",
        "card": {
            "header": {"title": {"tag": "plain_text", "content": card_title}},
            "elements": [{"tag": "div", "text": {"tag": "lark_md", "content": custom_markdown}}],
        },
    }

    resp = requests.post(FEISHU_WEBHOOK, json=payload, timeout=TIMEOUT)
    resp.raise_for_status()


def main():
    state = load_state()
    last_id = state.get("last_id", "")

    feed = feedparser.parse(RSS_URL)
    entries = getattr(feed, "entries", []) or []

    if not entries:
        feishu_send_card("RSS 机器人", f"未获取到内容，请检查 RSS：{RSS_URL}")
        return

    if FORCE_SEND:
        new_entries = entries[: max(1, FORCE_ITEMS)]
    else:
        new_entries = []
        for e in entries:
            if entry_id(e) == last_id:
                break
            new_entries.append(e)

        if not last_id:
            new_entries = new_entries[:1]
        else:
            new_entries = new_entries[:MAX_ITEMS_PER_RUN]

    if not new_entries:
        if ALWAYS_NOTIFY:
            feishu_send_card("AI早报更新", "暂无更新")
        return

    new_entries.reverse()

    digest_items = []
    source_links = []

    for e in new_entries:
        parsed_items, source_url = fetch_original_digest_items(e)
        if parsed_items:
            digest_items.extend(parsed_items)
            if source_url:
                source_links.append(source_url)
            continue

        # fallback：网络或解析失败时，至少保证有基础可读信息
        title = getattr(e, "title", "(无标题)")
        link = getattr(e, "link", "")
        summary = (getattr(e, "summary", "") or "").strip()
        published = (getattr(e, "published", "") or "").strip()
        digest_items.append({
            "title": title,
            "link": link,
            "summary": summary,
            "published": published,
        })

    card_title = "AI早报更新（测试）" if FORCE_SEND else "AI早报更新"
    digest = build_structured_digest(digest_items, source_links=source_links)
    feishu_send_card(card_title, digest)

    state["last_id"] = entry_id(entries[0])
    save_state(state)


if __name__ == "__main__":
    main()