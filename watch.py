import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import requests

MODEL = "MJX54J/A"
JAN = "4549995734546"
MAX_PRICE = 239800
NTFY_TOPIC = os.environ["NTFY_TOPIC"]
STATE_FILE = Path("state.json")

BROWSER_UA = (
    "Mozilla/5.0 (Linux; Android 16; Pixel 10 Pro XL) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/140.0 Mobile Safari/537.36"
)

TARGETS = [
    {
        "name": "Amazon.co.jp",
        "site": "amazon",
        "url": "https://www.amazon.co.jp/dp/B0HJ9ZYXPV",
        "check_url": "https://www.amazon.co.jp/dp/B0HJ9ZYXPV",
    },
    {
        "name": "ヤマダウェブコム",
        "site": "yamada",
        "url": "https://www.yamada-denkiweb.com/7164953012/",
        "check_url": "https://www.yamada-denkiweb.com/7164953012/",
    },
    {
        "name": "ケーズデンキ",
        "site": "ks",
        "url": "https://www.ksdenki.com/shop/g/g4549995734546/",
        "check_url": "https://www.ksdenki.com/shop/g/g4549995734546/",
    },
    {
        "name": "ヨドバシカメラ",
        "site": "yodobashi",
        "url": "https://www.yodobashi.com/product/100000001010202098/",
        "check_url": "https://www.yodobashi.com/product/100000001010202098/",
        "fallback_url": "https://www.yodobashi.com/?word=MJX54J%2FA",
    },
]


def fetch_curl(url, timeout=40):
    cmd = [
        "curl",
        "--http1.1",
        "-L",
        "-sS",
        "--fail",
        "--max-time",
        str(timeout),
        "-A",
        BROWSER_UA,
        "-H",
        "Accept-Language: ja-JP,ja;q=0.9,en;q=0.8",
        "-H",
        "Cache-Control: no-cache",
        url,
    ]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 5)
    if p.returncode != 0:
        raise RuntimeError(f"curl failed: {p.stderr.strip()[:160]}")
    return p.stdout


def fetch_amazon(url):
    text = fetch_curl(url, timeout=40)
    if len(text) < 100000:
        raise RuntimeError(f"Amazon response too short ({len(text)} bytes)")
    if MODEL.lower() not in text.lower():
        raise RuntimeError("Amazon exact model missing from response")
    return text


def fetch_jina(url, engine=None):
    headers = {
        "Accept": "text/plain",
        "User-Agent": "Mozilla/5.0",
        "X-Locale": "ja-JP",
        "X-No-Cache": "true",
        "X-Cache-Tolerance": "0",
    }
    if engine:
        headers["X-Engine"] = engine

    r = requests.get(
        "https://r.jina.ai/" + url,
        headers=headers,
        timeout=55,
    )
    r.raise_for_status()
    text = r.text

    if len(text.strip()) < 500:
        raise RuntimeError(f"Jina response too short ({len(text)} bytes)")

    blocked = ["Access Denied", "Just a moment", "アクセスを遮断しました", "CAPTCHA"]
    if any(x.lower() in text.lower() for x in blocked):
        raise RuntimeError("target site blocked Jina")

    return text


def fetch_jina_with_direct_fallback(url):
    try:
        return fetch_jina(url)
    except Exception as jina_error:
        try:
            text = fetch_curl(url, timeout=12)
            if len(text.strip()) < 500:
                raise RuntimeError(f"direct response too short ({len(text)} bytes)")
            return text
        except Exception as direct_error:
            raise RuntimeError(
                f"FETCH_FAIL Jina={jina_error}; direct={direct_error}"
            ) from direct_error


def has_inventory_field(text):
    return bool(
        re.search(
            r"在庫\s*[:：]\s*(?:\|\s*)?"
            r"(?:販売終了|予約終了|在庫なし|売り切れ|在庫あり|在庫僅少|残りわずか)",
            re.sub(r"\s+", " ", text),
        )
    )


def fetch_target(target):
    site = target["site"]

    if site == "amazon":
        return fetch_amazon(target["check_url"])

    if site == "ks":
        primary = fetch_jina_with_direct_fallback(target["check_url"])
        if has_inventory_field(primary):
            return primary

        # K's inventory is dynamically rendered. Try Jina's alternate browser
        # renderer only when the normal fresh response lacks the official field.
        try:
            alternate = fetch_jina(target["check_url"], engine="cf-browser-rendering")
            if has_inventory_field(alternate):
                return alternate
        except Exception:
            pass
        return primary

    if site == "yodobashi":
        try:
            primary = fetch_jina(target["check_url"])
            low = primary.lower()
            if MODEL.lower() in low and "iphone 18 pro max" in low:
                return primary
        except Exception:
            pass

        # Exact product page is preferred, but the unique model search page is
        # a safe fallback because the current query returns exactly one model.
        return fetch_jina_with_direct_fallback(target["fallback_url"])

    return fetch_jina_with_direct_fallback(target["check_url"])


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
    return sorted(p for p in vals if 180000 <= p <= 500000)


def choose_target_price(text):
    prices = extract_prices(text)
    if not prices:
        return None
    if MAX_PRICE in prices:
        return MAX_PRICE
    affordable = [p for p in prices if p <= MAX_PRICE]
    return max(affordable) if affordable else min(prices)


def compact(text):
    return re.sub(r"\s+", " ", text).strip()


def product_identity(text, require_jan=False):
    low = text.lower()
    if "iphone 18 pro max" not in low or "256gb" not in low:
        return False
    if MODEL.lower() not in low and require_jan and JAN not in text:
        return False
    if require_jan and JAN not in text:
        return False
    return True


def best_model_window(text, radius=3500):
    low = text.lower()
    positions = [m.start() for m in re.finditer(re.escape(MODEL.lower()), low)]
    if not positions:
        return ""

    status_words = [
        "好評につき売り切れました",
        "売り切れました",
        "販売終了しました",
        "予定数の販売を終了しました",
        "予定数の販売を終了",
        "在庫なし",
        "在庫あり",
        "在庫残少",
        "在庫僅少",
        "残りわずか",
        "お取り寄せ",
        "24時間以内に出荷",
        "カートに入れる",
    ]

    best = ""
    best_score = -1
    for p in positions:
        w = text[max(0, p - radius): min(len(text), p + radius)]
        score = 0
        score += 8 if JAN in w else 0
        score += 5 if "iPhone 18 Pro Max" in w else 0
        score += 3 if "256GB" in w else 0
        score += 3 if "ブラック" in w else 0
        score += 3 if extract_prices(w) else 0
        score += sum(4 for x in status_words if x in w)
        if score > best_score:
            best_score = score
            best = w

    return best


def price_check(text):
    price = choose_target_price(text)
    if price is None:
        return None, "STATUS_UNKNOWN target price not found"
    if price > MAX_PRICE:
        return False, f"{price:,}円 > {MAX_PRICE:,}円"
    return True, f"{price:,}円"


def check_yamada(text):
    if not product_identity(text):
        return None, "PRODUCT_NOT_FOUND Yamada exact product identity missing"

    block = best_model_window(text)
    if not block:
        return None, "PRODUCT_NOT_FOUND Yamada model block missing"

    negative = [
        "好評につき売り切れました",
        "売り切れました",
        "販売終了しました",
        "予約開始待ち",
        "予約受付終了",
    ]
    for phrase in negative:
        if phrase in block:
            return False, f"{phrase} / exact product block"

    positive = [
        "24時間以内に出荷",
        "在庫あり",
        "お取り寄せ",
    ]
    stock = next((x for x in positive if x in block), None)
    if stock:
        ok, price_reason = price_check(block)
        if ok is False:
            return False, price_reason
        if ok is True and ("数量" in block or "カートに入れる" in block):
            return True, f"{stock} + purchase control / {price_reason}"

    return None, "STATUS_UNKNOWN Yamada exact purchase status not confirmed"


def check_ks(text):
    # The exact URL itself contains the JAN. Jina sometimes omits the model
    # title, so identify the product using JAN + product family/capacity.
    low = text.lower()
    if JAN not in text or "iphone 18 pro max" not in low or "256gb" not in low:
        return None, "PRODUCT_NOT_FOUND K's exact product identity missing"

    c = compact(text)

    negative_re = re.compile(
        r"在庫\s*[:：]\s*(?:\|\s*)?"
        r"(販売終了|予約終了|在庫なし|売り切れ)"
    )
    positive_re = re.compile(
        r"在庫\s*[:：]\s*(?:\|\s*)?"
        r"(在庫あり|在庫僅少|残りわずか)"
    )

    neg = negative_re.search(c)
    if neg:
        return False, f"在庫:{neg.group(1)} / official inventory field"

    pos = positive_re.search(c)
    if pos:
        ok, price_reason = price_check(c)
        if ok is False:
            return False, price_reason
        if ok is True:
            return True, f"在庫:{pos.group(1)} / official inventory field / {price_reason}"

    # Never use generic legend text such as "在庫限り" as a positive signal.
    return None, "STATUS_UNKNOWN K's official inventory field not exposed"


def check_yodobashi(text):
    if not product_identity(text):
        return None, "PRODUCT_NOT_FOUND Yodobashi exact model missing"

    block = best_model_window(text, radius=2800) or text

    negative = [
        "予定数の販売を終了しました",
        "予定数の販売を終了",
        "販売終了",
        "在庫なし",
        "売り切れ",
    ]
    for phrase in negative:
        if phrase in block:
            return False, f"{phrase} / exact model block"

    ok, price_reason = price_check(block)
    if ok is False:
        return False, price_reason

    positive = [
        "在庫あり",
        "在庫残少",
        "在庫僅少",
        "残りわずか",
        "お取り寄せ",
    ]
    stock = next((x for x in positive if x in block), None)
    if stock and "カートに入れる" in block and ok is True:
        return True, f"{stock} + カートに入れる / {price_reason}"

    return None, "STATUS_UNKNOWN Yodobashi stock + cart action not confirmed"


def check_amazon(html):
    if MODEL.lower() not in html.lower():
        return None, "PRODUCT_NOT_FOUND Amazon exact model missing"

    availability_pos = html.lower().find('id="availability"')
    availability_block = ""
    if availability_pos >= 0:
        availability_block = html[availability_pos:availability_pos + 12000]

    negative = [
        "現在在庫切れです",
        "一時的に在庫切れ",
        "現在お取り扱いできません",
    ]
    for phrase in negative:
        if phrase in availability_block or phrase in html:
            return False, f"{phrase} / exact Amazon product"

    has_cart = (
        'id="add-to-cart-button"' in html
        or 'id="buy-now-button"' in html
        or 'name="submit.add-to-cart"' in html
    )
    if not has_cart:
        return None, "STATUS_UNKNOWN Amazon purchase button not found"

    merchant_pos = html.lower().find('id="merchant-info"')
    if merchant_pos < 0:
        return None, "STATUS_UNKNOWN Amazon merchant field not found"

    merchant_block = html[merchant_pos:merchant_pos + 10000]
    if "Amazon.co.jp" not in merchant_block:
        return False, "seller is not Amazon.co.jp"

    price_block = html
    for marker in [
        'id="corepricedisplay_desktop_feature_div"',
        'id="coreprice_feature_div"',
    ]:
        p = html.lower().find(marker)
        if p >= 0:
            price_block = html[p:p + 20000]
            break

    price = choose_target_price(price_block)
    if price is None:
        return None, "STATUS_UNKNOWN Amazon target price not confirmed"
    if price > MAX_PRICE:
        return False, f"{price:,}円 > {MAX_PRICE:,}円"

    return True, f"Amazon.co.jp + purchase button / {price:,}円"


def check_target(text, target):
    site = target["site"]
    if site == "amazon":
        return check_amazon(text)
    if site == "yamada":
        return check_yamada(text)
    if site == "ks":
        return check_ks(text)
    if site == "yodobashi":
        return check_yodobashi(text)
    return None, "STATUS_UNKNOWN unknown site parser"


def load_state():
    if not STATE_FILE.exists():
        return {}
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
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
        f"{target['name']}で iPhone 18 Pro Max 256GB ブラックの在庫を"
        f"厳格判定で確認しました。\n{reason}\n"
        "タップして購入ページを最終確認してください。"
    )
    r = requests.post(
        "https://ntfy.sh",
        json={
            "topic": NTFY_TOPIC,
            "message": message,
            "title": "iPhone 在庫確認",
            "priority": 5,
            "tags": ["iphone", "shopping_cart"],
            "click": target["url"],
        },
        timeout=15,
    )

    try:
        payload = r.json()
    except ValueError:
        payload = {}

    if not r.ok:
        print(
            f"NOTIFY FAILED: {target['name']} / HTTP {r.status_code}",
            file=sys.stderr,
        )
        r.raise_for_status()

    msg_id = payload.get("id", "unknown")
    print(
        f"NOTIFY SENT: {target['name']} / HTTP {r.status_code} / message-id {msg_id}"
    )


def main():
    state = load_state()

    for target in TARGETS:
        name = target["name"]
        before = bool(state.get(name, False))

        try:
            text = fetch_target(target)
            available, reason = check_target(text, target)

            # A positive result must be reproduced by a second fresh fetch.
            if available is True:
                time.sleep(3)
                confirm_text = fetch_target(target)
                confirm, confirm_reason = check_target(confirm_text, target)

                if confirm is not True:
                    available = None
                    reason = (
                        "STATUS_UNKNOWN positive not confirmed twice; "
                        f"second={confirm_reason}"
                    )
                else:
                    reason = f"{reason} / confirmed twice"

            status = (
                "UNKNOWN"
                if available is None
                else ("IN STOCK" if available else "OUT")
            )
            print(f"{name}: {status} ({reason})")

            if available is True and not before:
                notify(target, reason)

            if available is not None:
                state[name] = available

        except Exception as e:
            print(f"{name}: UNKNOWN (FETCH_FAIL {e})", file=sys.stderr)

    save_state(state)


if __name__ == "__main__":
    main()
