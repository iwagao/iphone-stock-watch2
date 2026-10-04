import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import quote

import requests

MODEL = "MJX54J/A"
JAN = "4549995734546"
MAX_PRICE = 239800
NTFY_TOPIC = os.environ["NTFY_TOPIC"]
STATE_FILE = Path("state.json")

TARGETS = [
    {
        "name": "Amazon.co.jp",
        "url": "https://www.amazon.co.jp/dp/B0HJ9ZYXPV",
        "markers": ["MJX54J/A", "iPhone 18 Pro Max"],
        "positive": ["カートに入れる", "今すぐ買う", "在庫あり"],
        "negative": ["現在在庫切れです", "一時的に在庫切れ", "現在お取り扱いできません"],
        "seller_required": "Amazon.co.jp",
    },
    {
        "name": "ヤマダウェブコム",
        "url": "https://www.yamada-denkiweb.com/7164953012/",
        "markers": ["MJX54J/A", JAN, "iPhone 18 Pro Max"],
        "positive": ["カートに入れる", "在庫あり", "24時間以内に出荷"],
        "negative": ["売り切れ", "在庫なし", "販売終了", "予約受付終了"],
    },
    {
        "name": "ケーズデンキ",
        "url": "https://www.ksdenki.com/shop/g/g4549995734546/",
        "markers": [JAN, "MJX54J/A", "iPhone 18 Pro Max"],
        "positive": ["カートに入れる", "在庫あり", "お届け"],
        "negative": ["売り切れ", "在庫なし", "販売終了", "予約終了"],
    },
    {
        "name": "ヨドバシカメラ",
        "url": "https://www.yodobashi.com/?word=MJX54J%2FA",
        "markers": ["MJX54J/A", JAN, "iPhone 18 Pro Max"],
        "positive": ["カートに入れる", "在庫あり", "在庫残少", "お取り寄せ"],
        "negative": ["販売終了", "予定数の販売を終了", "在庫なし"],
    },
]

def fetch_via_jina(url):
    r = requests.get(
        "https://r.jina.ai/" + url,
        headers={"Accept": "text/plain", "User-Agent": "Mozilla/5.0"},
        timeout=45,
    )
    r.raise_for_status()
    text = r.text
    if len(text.strip()) < 500:
        raise RuntimeError("Jina response too short")
    block_words = ["Access Denied", "Just a moment", "アクセスを遮断しました", "CAPTCHA"]
    if any(x.lower() in text.lower() for x in block_words):
        raise RuntimeError("target site blocked Jina")
    return text

def normalize(text):
    return re.sub(r"\s+", " ", text)

def product_window(text, markers, radius=7000):
    low = text.lower()
    positions = []
    for marker in markers:
        p = low.find(marker.lower())
        if p >= 0:
            positions.append(p)
    if not positions:
        raise RuntimeError("product marker not found")
    p = min(positions)
    return text[max(0, p - radius): p + radius]

def extract_prices(text):
    prices = set()
    patterns = [
        r"([0-9]{1,3}(?:,[0-9]{3})+)\s*円",
        r"[￥¥]\s*([0-9]{1,3}(?:,[0-9]{3})+)",
        r"([0-9]{6})\s*円",
    ]
    for pat in patterns:
        for m in re.findall(pat, text):
            try:
                prices.add(int(m.replace(",", "")))
            except ValueError:
                pass
    return sorted(p for p in prices if 200000 <= p <= 400000)

def check_target(text, target):
    snippet = product_window(text, target["markers"])
    compact = normalize(snippet)

    prices = extract_prices(compact)
    if not prices or min(prices) > MAX_PRICE:
        return False, f"price={prices or 'not found'}"

    if any(word in compact for word in target["negative"]):
        return False, "negative stock phrase"

    if not any(word in compact for word in target["positive"]):
        return False, "purchase phrase not found"

    seller = target.get("seller_required")
    if seller and seller not in compact:
        return False, "seller not confirmed"

    return True, f"price={min(prices):,}"

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

def notify(target):
    message = (
        f"{target['name']}で iPhone 18 Pro Max 256GB ブラックを検知しました。\n"
        f"価格条件: {MAX_PRICE:,}円以下\n"
        "タップして購入ページを確認してください。"
    )
    r = requests.post(
        "https://ntfy.sh/" + quote(NTFY_TOPIC),
        data=message.encode("utf-8"),
        headers={
            "Title": "iPhone 定価在庫復活",
            "Priority": "5",
            "Tags": "iphone,shopping_cart",
            "Click": target["url"],
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
            text = fetch_via_jina(target["url"])
            available, reason = check_target(text, target)
            print(f"{name}: {'IN STOCK' if available else 'OUT'} ({reason})")

            if available and not before:
                notify(target)

            state[name] = available
        except Exception as e:
            print(f"{name}: UNKNOWN ({e})", file=sys.stderr)
            # UNKNOWNでは前回状態を維持し、復旧後の重複通知を防ぐ

    save_state(state)

if __name__ == "__main__":
    main()
