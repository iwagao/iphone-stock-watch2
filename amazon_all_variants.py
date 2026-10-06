import subprocess
import time

BROWSER_UA = (
    "Mozilla/5.0 (Linux; Android 16; Pixel 10 Pro XL) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/140.0 Mobile Safari/537.36"
)

SKUS = [
    ("256GB", "ブラック", "MJX54J/A", "B0HJ9ZYXPV"),
    ("256GB", "シルバー", "MJX64J/A", "B0HJBCT1D5"),
    ("256GB", "バーガンディ", "MJX74J/A", "B0HJB6YR8X"),
    ("256GB", "グレイシャー", "MJX84J/A", "B0HJB7L347"),
    ("512GB", "ブラック", "MJX94J/A", "B0HJB4296X"),
    ("512GB", "シルバー", "MJXA4J/A", "B0HJB69RVJ"),
    ("512GB", "バーガンディ", "MJXC4J/A", "B0HJB72MGS"),
    ("512GB", "グレイシャー", "MJXD4J/A", "B0HJBHQY2N"),
    ("1TB", "ブラック", "MJXE4J/A", "B0HJB36LR2"),
    ("1TB", "シルバー", "MJXF4J/A", "B0HJB7V8R5"),
    ("1TB", "バーガンディ", "MJXG4J/A", "B0HJB4RVLW"),
    ("1TB", "グレイシャー", "MJXH4J/A", "B0HJB65BLC"),
    ("2TB", "ブラック", "MJXJ4J/A", "B0HJ9VS44C"),
    ("2TB", "シルバー", "MJXK4J/A", "B0HJB4LCRD"),
    ("2TB", "バーガンディ", "MJXL4J/A", "B0HJ9Y9FN4"),
    ("2TB", "グレイシャー", "MJXM4J/A", "B0HJBHHXK2"),
]

NEGATIVE = [
    "現在在庫切れです",
    "一時的に在庫切れ",
    "現在お取り扱いできません",
]


def fetch(url, timeout=45):
    cmd = [
        "curl",
        "--http1.1",
        "--compressed",
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
    p = subprocess.run(cmd, capture_output=True, timeout=timeout + 5)
    if p.returncode != 0:
        err = p.stderr.decode("utf-8", "ignore").strip()
        raise RuntimeError(f"curl rc={p.returncode}: {err[:180]}")
    return p.stdout.decode("utf-8", "ignore")


def check(capacity, color, model, asin):
    url = f"https://www.amazon.co.jp/dp/{asin}"
    try:
        page = fetch(url)
    except Exception as e:
        return "UNKNOWN", f"FETCH_FAIL {e}", url

    if len(page) < 100000:
        return "UNKNOWN", f"RESPONSE_TOO_SHORT {len(page)}", url

    low = page.lower()
    identity = (
        model.lower() in low
        or (
            "iphone 18 pro max" in low
            and capacity.lower() in low
            and color.lower() in low
        )
    )
    if not identity:
        return "UNKNOWN", "PRODUCT_MISMATCH", url

    p = low.find('id="availability"')
    availability = page[p:p + 14000] if p >= 0 else page

    for phrase in NEGATIVE:
        if phrase in availability or phrase in page:
            return "OUT", phrase, url

    has_cart = (
        'id="add-to-cart-button"' in page
        or 'id="buy-now-button"' in page
        or 'name="submit.add-to-cart"' in page
    )

    p = low.find('id="merchant-info"')
    merchant = page[p:p + 12000] if p >= 0 else ""
    amazon_seller = "Amazon.co.jp" in merchant

    if has_cart and amazon_seller:
        return "IN STOCK", "Amazon.co.jp seller + purchase button", url
    if has_cart:
        return "POSSIBLE", "purchase button but non-Amazon seller", url

    return "UNKNOWN", "no explicit stock phrase or purchase button", url


def main():
    results = []

    print("Amazon iPhone 18 Pro Max 全16SKU 在庫チェック")
    print("=" * 72)

    for i, (capacity, color, model, asin) in enumerate(SKUS, 1):
        status, reason, url = check(capacity, color, model, asin)
        results.append((capacity, color, model, asin, status, reason, url))
        print(
            f"[{i:02d}/16] {capacity:5} | {color:7} | {model:8} | "
            f"{status:8} | {reason}"
        )
        if i < len(SKUS):
            time.sleep(3)

    print("\n" + "=" * 72)
    print("SUMMARY")
    counts = {}
    for row in results:
        counts[row[4]] = counts.get(row[4], 0) + 1

    for key in ["IN STOCK", "POSSIBLE", "OUT", "UNKNOWN"]:
        print(f"{key:8}: {counts.get(key, 0)}")

    in_stock = [r for r in results if r[4] == "IN STOCK"]
    possible = [r for r in results if r[4] == "POSSIBLE"]

    if in_stock:
        print("\n購入可能と確認できた商品:")
        for capacity, color, model, asin, status, reason, url in in_stock:
            print(f"- {capacity} {color} {model} {url}")
    elif possible:
        print("\n購入可能性あり（Amazon.co.jp販売とは未確認）:")
        for capacity, color, model, asin, status, reason, url in possible:
            print(f"- {capacity} {color} {model} {url}")
    else:
        print("\nAmazon.co.jp販売の在庫あり商品は確認できませんでした。")


if __name__ == "__main__":
    main()
