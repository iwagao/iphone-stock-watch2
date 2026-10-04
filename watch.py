import json
import os
import re
import sys
import time
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
        "url": "https://www.yodobashi.com/?word=MJX54J%2FA",
        "check_url": "https://www.yodobashi.com/?word=MJX54J%2FA",
    },
]


def fetch_jina(url):
    r = requests.get(
        "https://r.jina.ai/" + url,
        headers={
            "Accept": "text/plain",
            "User-Agent": "Mozilla/5.0",
            "X-Locale": "ja-JP",
            "Cache-Control": "no-cache",
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
    return sorted(p for p in vals if 180000 <= p <= 500000)


def choose_target_price(text):
    prices = extract_prices(text)
    if not prices:
        return None
    if MAX_PRICE in prices:
        return MAX_PRICE
    affordable = [p for p in prices if p <= MAX_PRICE]
    return max(affordable) if affordable else min(prices)


def product_chunks(text, radius=1400):
    """Return only blocks where the exact JAN and model occur together."""
    if JAN not in text or MODEL.lower() not in text.lower():
        return []

    chunks = []
    seen = set()
    for m in re.finditer(re.escape(JAN), text):
        start = max(0, m.start() - radius)
        end = min(len(text), m.end() + radius)
        chunk = text[start:end]
        if MODEL.lower() not in chunk.lower():
            continue
        key = (start, end)
        if key not in seen:
            chunks.append(chunk)
            seen.add(key)
    return chunks


def compact(text):
    return re.sub(r"\s+", " ", text).strip()


def price_check(chunk):
    price = choose_target_price(chunk)
    if price is None:
        return None, "target price not found"
    if price > MAX_PRICE:
        return False, f"{price:,}円 > {MAX_PRICE:,}円"
    return True, f"{price:,}円"


def check_yamada(chunks):
    negative = {
        "好評につき売り切れました",
        "売り切れました",
        "販売終了しました",
        "予約開始待ち",
        "予約受付終了",
    }
    positive = {
        "お取り寄せ",
        "在庫あり",
        "24時間以内に出荷",
    }
    status_re = re.compile(
        r"配送\s*(好評につき売り切れました|売り切れました|販売終了しました|"
        r"予約開始待ち|予約受付終了|お取り寄せ|在庫あり|24時間以内に出荷)\s*詳細"
    )

    found_positive = None
    for chunk in chunks:
        c = compact(chunk)
        statuses = status_re.findall(c)
        for status in statuses:
            if status in negative:
                return False, f"{status} / exact product status"

        for status in statuses:
            if status in positive:
                ok, price_reason = price_check(chunk)
                if ok is False:
                    return False, price_reason
                if ok is True and ("数量" in chunk or "カートに入れる" in chunk):
                    found_positive = f"{status} / {price_reason}"

    if found_positive:
        return True, found_positive
    return None, "exact Yamada purchase status not confirmed"


def check_ks(chunks):
    # K's has a structured inventory field. Only that field is trusted.
    # Generic legend text such as "在庫限り" is intentionally ignored.
    negative_re = re.compile(
        r"在庫\s*[:：]\s*(?:\|\s*)?"
        r"(販売終了|予約終了|在庫なし|売り切れ)"
    )
    positive_re = re.compile(
        r"在庫\s*[:：]\s*(?:\|\s*)?"
        r"(在庫あり|在庫僅少|残りわずか)"
    )

    found_positive = None
    for chunk in chunks:
        c = compact(chunk)

        neg = negative_re.search(c)
        if neg:
            return False, f"在庫:{neg.group(1)} / exact inventory field"

        pos = positive_re.search(c)
        if pos:
            ok, price_reason = price_check(chunk)
            if ok is False:
                return False, price_reason
            if ok is True and "数量" in chunk:
                found_positive = f"在庫:{pos.group(1)} / {price_reason}"

    if found_positive:
        return True, found_positive
    return None, "exact K's inventory field not confirmed"


def check_yodobashi(chunks):
    # Search/result pages can contain unrelated products, so require:
    # exact JAN + model, an explicit stock phrase, AND a cart action.
    negative = [
        "予定数の販売を終了しました",
        "予定数の販売を終了",
        "販売終了",
        "在庫なし",
        "売り切れ",
    ]
    stock_positive = [
        "在庫あり",
        "在庫残少",
        "在庫僅少",
        "残りわずか",
        "お取り寄せ",
    ]

    found_positive = None
    for chunk in chunks:
        if any(x in chunk for x in negative):
            hit = next(x for x in negative if x in chunk)
            return False, f"{hit} / exact product block"

        stock = next((x for x in stock_positive if x in chunk), None)
        if stock and "カートに入れる" in chunk:
            ok, price_reason = price_check(chunk)
            if ok is False:
                return False, price_reason
            if ok is True:
                found_positive = f"{stock} + カートに入れる / {price_reason}"

    if found_positive:
        return True, found_positive
    return None, "Yodobashi requires stock phrase + cart action"


def check_target(text, target):
    chunks = product_chunks(text)
    if not chunks:
        return None, "exact MODEL + JAN product block not found"

    if target["site"] == "yamada":
        return check_yamada(chunks)
    if target["site"] == "ks":
        return check_ks(chunks)
    if target["site"] == "yodobashi":
        return check_yodobashi(chunks)
    return None, "unknown site parser"


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
            available, reason = check_target(fetch_jina(target["check_url"]), target)

            # False positives are costlier than missed alerts. A positive result
            # must therefore be reproduced by a second independent fetch.
            if available is True:
                time.sleep(3)
                confirm, confirm_reason = check_target(
                    fetch_jina(target["check_url"]), target
                )
                if confirm is not True:
                    available = None
                    reason = f"positive not confirmed twice; second={confirm_reason}"
                else:
                    reason = f"{reason} / confirmed twice"

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
