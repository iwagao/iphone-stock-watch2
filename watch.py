import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

MODEL = "MJX54J/A"
JAN = "4549995734546"
MAX_PRICE = 239800
NTFY_TOPIC = os.environ["NTFY_TOPIC"]
STATE_FILE = Path("state.json")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 16; Pixel 10 Pro XL) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/140.0 Mobile Safari/537.36"
    ),
    "Accept-Language": "ja-JP,ja;q=0.9,en;q=0.8",
}

TARGETS = [
    {
        "name": "Amazon.co.jp",
        "url": "https://www.amazon.co.jp/dp/B0HJ9ZYXPV",
        "kind": "amazon",
    },
    {
        "name": "ビックカメラ",
        "url": "https://www.biccamera.com/bc/item/15593282/",
        "kind": "generic",
        "positive": ["カートに入れる", "在庫あり"],
        "negative": ["予定数の販売を終了", "販売休止中", "売り切れ", "在庫なし"],
    },
    {
        "name": "ヤマダウェブコム",
        "url": "https://www.yamada-denkiweb.com/7164953012/",
        "kind": "generic",
        "positive": ["カートに入れる", "在庫あり"],
        "negative": ["売り切れ", "在庫なし", "販売終了"],
    },
    {
        "name": "エディオン",
        "url": "https://www.edion.com/detail.html?p_cd=00086916134",
        "kind": "edion",
    },
    {
        "name": "ノジマオンライン",
        "url": "https://online.nojima.co.jp/commodity/1/4549995734546/",
        "kind": "generic",
        "positive": ["カートに入れる", "在庫あり", "即納", "24時間以内"],
        "negative": ["予約準備中", "売り切れ", "在庫なし", "入荷次第", "販売終了"],
    },
    {
        "name": "ケーズデンキ",
        "url": "https://www.ksdenki.com/shop/g/g4549995734546/",
        "kind": "generic",
        "positive": ["カートに入れる", "在庫あり"],
        "negative": ["売り切れ", "在庫なし", "販売終了"],
    },
    {
        "name": "ヨドバシカメラ",
        "url": "https://www.yodobashi.com/?word=MJX54J%2FA",
        "kind": "search",
        "positive": ["カートに入れる", "在庫あり", "在庫残少"],
        "negative": ["販売終了", "予定数の販売を終了"],
    },
    {
        "name": "Joshin web",
        "url": "https://joshinweb.jp/search/?KEYWORD=4549995734546",
        "kind": "search",
        "positive": ["カートに入れる", "在庫あり"],
        "negative": ["売り切れ", "販売終了", "完売"],
    },
]

def fetch(url):
    r = requests.get(url, headers=HEADERS, timeout=20, allow_redirects=True)
    r.raise_for_status()
    return r.text

def text_from_html(html):
    return " ".join(BeautifulSoup(html, "html.parser").stripped_strings)

def extract_prices(text):
    vals = []
    for pat in [
        r"([0-9]{1,3}(?:,[0-9]{3})+)\s*円",
        r"[￥¥]\s*([0-9]{1,3}(?:,[0-9]{3})+)",
    ]:
        for m in re.findall(pat, text):
            try:
                vals.append(int(m.replace(",", "")))
            except ValueError:
                pass
    return vals

def acceptable_price(text):
    vals = [p for p in extract_prices(text) if 200000 <= p <= 400000]
    return any(p <= MAX_PRICE for p in vals)

def identifies_product(text):
    low = text.lower()
    return (
        MODEL.lower() in low
        or JAN in text
        or (
            "iphone 18 pro max" in low
            and "256" in low
            and ("ブラック" in text or "black" in low)
        )
    )

def check_amazon(html):
    soup = BeautifulSoup(html, "html.parser")
    title = soup.select_one("#productTitle")
    title_text = title.get_text(" ", strip=True) if title else ""
    if not identifies_product(title_text):
        return False

    availability = soup.select_one("#availability")
    availability_text = availability.get_text(" ", strip=True) if availability else ""
    bad = ["現在在庫切れです", "一時的に在庫切れ", "現在お取り扱いできません"]
    if any(x in availability_text for x in bad):
        return False

    price_text = ""
    for selector in [
        "#corePriceDisplay_desktop_feature_div .a-offscreen",
        "#corePrice_feature_div .a-offscreen",
        ".a-price .a-offscreen",
    ]:
        el = soup.select_one(selector)
        if el:
            price_text = el.get_text(" ", strip=True)
            break

    if not acceptable_price(price_text):
        return False

    if not (soup.select_one("#add-to-cart-button") or soup.select_one("#buy-now-button")):
        return False

    merchant = ""
    for selector in ["#merchant-info", "#sellerProfileTriggerId"]:
        el = soup.select_one(selector)
        if el:
            merchant += " " + el.get_text(" ", strip=True)

    return "Amazon.co.jp" in merchant

def check_edion(text):
    if not identifies_product(text) or not acceptable_price(text):
        return False
    if any(x in text for x in ["在庫数0台", "売り切れ", "販売可能期間ではございません"]):
        return False
    m = re.search(r"在庫数\s*([0-9]+)\s*台", text)
    if m:
        return int(m.group(1)) > 0
    return "カートに入れる" in text

def check_generic(text, target):
    if not identifies_product(text) or not acceptable_price(text):
        return False
    if any(x in text for x in target.get("negative", [])):
        return False
    return any(x in text for x in target.get("positive", []))

def load_state():
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}

def save_state(state):
    STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
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
        before = state.get(name, False)

        try:
            html = fetch(target["url"])
            text = text_from_html(html)

            if target["kind"] == "amazon":
                available = check_amazon(html)
            elif target["kind"] == "edion":
                available = check_edion(text)
            else:
                available = check_generic(text, target)

            print(f"{name}: {'IN STOCK' if available else 'OUT'}")

            if available and not before:
                notify(target)

            state[name] = available

        except Exception as e:
            print(f"{name}: UNKNOWN ({e})", file=sys.stderr)

    save_state(state)

if __name__ == "__main__":
    main()
