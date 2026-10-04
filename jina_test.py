import requests

TARGETS = {
    "Amazon.co.jp": "https://www.amazon.co.jp/dp/B0HJ9ZYXPV",
    "ビックカメラ": "https://www.biccamera.com/bc/item/15593282/",
    "ヤマダウェブコム": "https://www.yamada-denkiweb.com/7164953012/",
    "エディオン": "https://www.edion.com/detail.html?p_cd=00086916134",
    "ノジマオンライン": "https://online.nojima.co.jp/commodity/1/4549995734546/",
    "ケーズデンキ": "https://www.ksdenki.com/shop/g/g4549995734546/",
    "ヨドバシカメラ": "https://www.yodobashi.com/?word=MJX54J%2FA",
    "Joshin web": "https://joshinweb.jp/search/?KEYWORD=4549995734546",
}

HEADERS = {
    "Accept": "text/plain",
    "User-Agent": "Mozilla/5.0",
}

for name, url in TARGETS.items():
    jina = "https://r.jina.ai/" + url
    try:
        r = requests.get(jina, headers=HEADERS, timeout=45)
        text = r.text
        ok = r.status_code == 200 and len(text.strip()) > 500
        product_hint = any(x.lower() in text.lower() for x in [
            "MJX54J/A", "4549995734546", "iPhone 18 Pro Max"
        ])
        print(f"{name}\tstatus={r.status_code}\tchars={len(text)}\tproduct_hint={product_hint}\tok={ok}")
        if not ok:
            print(text[:300].replace("\n"," "))
    except Exception as e:
        print(f"{name}\tERROR\t{type(e).__name__}: {e}")
