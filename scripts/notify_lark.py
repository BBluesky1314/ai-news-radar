"""
Post new AI news items to a Lark group bot via incoming webhook.

Usage:
  python scripts/notify_lark.py --data-dir data [--max-items 10]

Required env:
  LARK_WEBHOOK_URL - the Lark incoming webhook URL
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone

import requests

SENT_IDS_FILE = "lark_sent_ids.json"
MAX_CARD_MD_CHARS = 8000


def load_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: str, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def format_time(ts: str) -> str:
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        local_dt = dt.astimezone()
        return local_dt.strftime("%H:%M")
    except Exception:
        return ts


def build_md(news, max_items: int) -> str:
    lines = []
    for item in news[:max_items]:
        title = item.get("title_bilingual") or item.get("title_zh") or item.get("title", "")
        url = item.get("url", "")
        source = item.get("source", "")
        pub = format_time(item.get("published_at", ""))
        label = item.get("ai_label", "")

        label_map = {
            "model_release": "模型发布",
            "product_launch": "产品上线",
            "research_paper": "论文",
            "funding": "融资",
            "policy_regulation": "政策",
            "ai_tool": "AI工具",
            "trending": "热门",
        }
        tag = label_map.get(label, label) if label else ""

        if tag:
            title = f"{title}  `{tag}`"

        lines.append(f"**[{title}]({url})**\n{source} · {pub}")

    return "\n\n".join(lines)


def send_card(webhook_url: str, md_content: str, item_count: int, generated_at: str):
    payload = {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": "AI 新闻雷达"},
                "template": "blue",
            },
            "elements": [
                {
                    "tag": "markdown",
                    "content": md_content,
                }
            ],
            "note": {
                "elements": [
                    {
                        "tag": "plain_text",
                        "content": f"共 {item_count} 条 · 更新于 {generated_at}",
                    }
                ]
            },
        },
    }

    resp = requests.post(webhook_url, json=payload, timeout=30)
    resp.raise_for_status()
    body = resp.json()
    if body.get("code") != 0:
        print(f"Lark API error: {body}", file=sys.stderr)
        sys.exit(1)
    print(f"Sent {item_count} items to Lark, StatusMessageId={body.get('StatusMessageId', 'N/A')}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--max-items", type=int, default=10)
    args = parser.parse_args()

    webhook_url = os.environ.get("LARK_WEBHOOK_URL", "").strip()
    if not webhook_url:
        print("LARK_WEBHOOK_URL is not set, skipping notification")
        return

    latest_path = os.path.join(args.data_dir, "latest-24h.json")
    if not os.path.exists(latest_path):
        print(f"Data file not found: {latest_path}")
        return

    sent_ids_path = os.path.join(args.data_dir, SENT_IDS_FILE)
    sent_ids = set()
    if os.path.exists(sent_ids_path):
        try:
            sent_ids = set(load_json(sent_ids_path))
        except Exception:
            sent_ids = set()

    data = load_json(latest_path)
    items = data.get("items", [])
    generated_at = data.get("generated_at", "")

    ai_items = [it for it in items if it.get("ai_is_related")]
    ai_items.sort(key=lambda it: it.get("ai_score", 0), reverse=True)

    new_items = [it for it in ai_items if it.get("id") not in sent_ids]

    if not new_items:
        print("No new AI items to send")
        return

    item_count = len(new_items)
    md = build_md(new_items, args.max_items)
    send_card(webhook_url, md, item_count, generated_at)

    new_ids = {it["id"] for it in new_items}
    sent_ids.update(new_ids)
    save_json(sent_ids_path, sorted(sent_ids))
    print(f"Saved {len(new_ids)} new IDs to {SENT_IDS_FILE}")


if __name__ == "__main__":
    main()
