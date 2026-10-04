import json
import os
import re
import sys
from pathlib import Path

import requests

MODEL = "MJX54J/A"
JAN = "4549995734546"
MAX_PRICE = 239800
NTFY_TOPIC = os.environ["NTFY_TOPIC"]
STATE_FILE = Path("state.json")

TARGETS = [
    {
        "name": "ヤマダウェブコム",
        "url": "https://www.yamada-denkiweb.com/7164953012/",
        "check_url": "https://www.yamada-denkiweb.com/7164953012/",
        "markers": [MODEL, JAN],
        "positive": ["カートに入れる", "在庫あり", "24時間以内に出荷"],
        "negative": ["好評につき売り切れました", "売り切れ", "在庫なし", "販売終了", "予約受付終了"],
    },
    {
        "name": "ケーズデンキ",
        "url": "https://www.ksdenki.com/shop/g/g4549995734546/",
        "check_url": "https://www.ksdenki.com/shop/r/r09023124_m4900030718_og/",
        "markers": [MODEL, JAN],
        "positive": ["在庫限り"],
        "negative": ["販売終了", "予約終了", "在庫なし", "売り切れ"],
    },
    {
        "name": "ヨドバシカメラ",
        "url": "https://www.yodobashi.com/?word=MJX54J%2FA",
        "check_url": "https://www.yodobashi.com/?word=MJX54J%2FA",
        "markers": [MODEL, JAN],
        "positive": ["カートに入れる", "在庫あり", "在庫残少", "お取り寄せ"],
        "negative": ["予定数の販売を終了しました", "予定数の販売を終了", "販売終了", "在庫なし"],
    },
]

def fetch_jina(url):
    r = requests.get(
        "https://r.jina.ai/" + url,
        headers={
            "Accept": "text/plain",
            "User-Agent": "Mozilla/5.0",
            "X-Locale": "ja-JP",
        },
        timeout=45,
    )
    r.raise_for_status()
    text = r.text
    if len(text.strip()) < 500:
        raise RuntimeError("Jina response too short")
    blocked = ["Access Denied", "Just a moment", "アクセスを遮断しました", "CAPTCHA"]
    if any(x.lower() in text.lower() for x in blocked):
        raise RuntimeError("target site blocked Jina")
    return text

def extract_prices(text):
    vals = set()
    for pat in [
        r"([0-9]{1,3}(?:,[0-9]{3})+)\s*円",
        r"[￥¥]\s*([0-9]{1,3}(?:,[0-9]{3})+)",
        r"([0-9]{6})\s*円",
    ]:
        for m in re.findall(pat, text):
            try:
                vals.add(int(m.replace(",", "")))
            except ValueError:
                pass
    return sorted(p for p in vals if 180000 <= p <= 400000)

def choose_price(prices):
    if MAX_PRICE in prices:
        return MAX_PRICE
    under = [p for p in prices if p <= MAX_PRICE]
    if under:
        return max(under)
    return min(prices)

def windows_for_markers(text, markers, radius=1200):
    low = text.lower()
    windows = []
    seen = set()
    for marker in markers:
        start = 0
        marker_low = marker.lower()
        while True:
            p = low.find(marker_low, start)
            if p < 0:
                break
            key = max(0, p - radius)
            if key not in seen:
                windows.append(text[max(0, p - radius): p + radius])
                seen.add(key)
            start = p + 1
    return windows

def check_target(text, target):
    windows = windows_for_markers(text, target["markers"])
    if not windows:
        return None, "product marker not found"

    best = None
    best_score = -1
    for w in windows:
        prices = extract_prices(w)
        pos = [x for x in target["positive"] if x in w]
        neg = [x for x in target["negative"] if x in w]
        score = (3 if prices else 0) + len(pos) * 2 + len(neg) * 2
        if score > best_score:
            best_score = score
            best = (prices, pos, neg)

    prices, pos, neg = best
    if not prices:
        return None, "price not found"

    price = choose_price(prices)
    if neg:
        return False, f"{neg[0]} / {price:,}円"
    if price > MAX_PRICE:
        return False, f"{price:,}円 > {MAX_PRICE:,}円"
    if not pos:
        return None, f"stock phrase not found / {price:,}円"

    return True, f"{pos[0]} / {price:,}円"

def load_state():
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}

def save_state(state):
    active = {t["name"]: bool(state.get(t["name"], False)) for t in TARGETS}
    STATE_FILE.write_text(
        json.dumps(active, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

def notify(target, reason):
    message = (
        f"{target['name']}で iPhone 18 Pro Max 256GB ブラックの在庫候補を検知しました。\n"
        f"{reason}\n"
        "タップして購入ページを確認してください。"
    )
    r = requests.post(
        "https://ntfy.sh",
        json={
            "topic": NTFY_TOPIC,
            "message": message,
            "title": "iPhone 在庫候補",
            "priority": 5,
            "tags": ["iphone", "shopping_cart"],
            "click": target["url"],
        },
        timeout=15,
    )
    r.raise_for_status()

def main():
    state = load_state()

    for target in TARGETS:
        name = target["name"]
        before = bool(state.get(name, False))
        try:
            available, reason = check_target(fetch_jina(target["check_url"]), target)
            status = "UNKNOWN" if available is None else ("IN STOCK" if available else "OUT")
            print(f"{name}: {status} ({reason})")

            if available is True and not before:
                notify(target, reason)

            if available is not None:
                state[name] = available
        except Exception as e:
            print(f"{name}: UNKNOWN ({e})", file=sys.stderr)

    save_state(state)

if __name__ == "__main__":
    main()
