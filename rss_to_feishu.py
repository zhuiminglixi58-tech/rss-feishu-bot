import os
import json
import time
import requests
import feedparser

RSS_URL = os.environ.get("RSS_URL", "https://imjuya.github.io/juya-ai-daily/rss.xml")
FEISHU_WEBHOOK = os.environ.get("FEISHU_WEBHOOK")
STATE_FILE = "state.json"

MAX_ITEMS_PER_RUN = int(os.environ.get("MAX_ITEMS_PER_RUN", "5"))
TIMEOUT = 15

def load_state():
    if not os.path.exists(STATE_FILE):
        return {"last_id": ""}
    with open(STATE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def feishu_send_card(title, items):
    if not FEISHU_WEBHOOK:
        raise RuntimeError("Missing FEISHU_WEBHOOK")

    content_blocks = []

    for idx, item in enumerate(items, 1):
        content_blocks.append({
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": f"**{idx}. {item['title']}**\n[🔗 查看原文]({item['link']})"
            }
        })

        content_blocks.append({"tag": "hr"})

    payload = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": title
                }
            },
            "elements": content_blocks
        }
    }

    requests.post(FEISHU_WEBHOOK, json=payload)

def entry_id(entry):
    return getattr(entry, "id", None) or getattr(entry, "guid", None) or getattr(entry, "link", "")

def main():
    state = load_state()
    last_id = state.get("last_id", "")

    feed = feedparser.parse(RSS_URL)
    entries = getattr(feed, "entries", []) or []

    if not entries:
        feishu_send_text(f"[RSS机器人] 未获取到内容：{RSS_URL}")
        return

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
        return

    new_entries.reverse()

    for e in new_entries:
        title = getattr(e, "title", "(无标题)")
        link = getattr(e, "link", "")
        summary = getattr(e, "summary", "")
        summary = (summary or "").strip()
        if len(summary) > 240:
            summary = summary[:240] + "…"

        msg = f"【AI早报】{title}\n{link}"
        if summary:
            msg += f"\n\n{summary}"

        feishu_send_text(msg)
        time.sleep(0.4)

    state["last_id"] = entry_id(entries[0])
    save_state(state)

if __name__ == "__main__":
    main()
