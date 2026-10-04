import requests,re
TARGETS={
"Amazon.co.jp":"https://www.amazon.co.jp/dp/B0HJ9ZYXPV",
"ヤマダ":"https://www.yamada-denkiweb.com/7164953012/",
"ケーズ":"https://www.ksdenki.com/shop/g/g4549995734546/",
"ヨドバシ":"https://www.yodobashi.com/?word=MJX54J%2FA",
}
KEYS=["MJX54J/A","4549995734546","239,800","239800","カートに入れる","在庫あり","在庫なし","販売終了","予約終了","現在在庫切れ","Add to cart","Buy Now","Amazon.co.jp"]
for name,url in TARGETS.items():
    t=requests.get("https://r.jina.ai/"+url,headers={"Accept":"text/plain","User-Agent":"Mozilla/5.0"},timeout=45).text
    print("\n###",name,"chars",len(t),"###")
    for key in KEYS:
        poss=[m.start() for m in re.finditer(re.escape(key),t,re.I)]
        if poss:
            print(key, poss[:12], "count", len(poss))
    for m in re.finditer(r"(?:[￥¥]\s*)?[0-9]{1,3}(?:,[0-9]{3})+(?:\s*円)?",t):
        s=m.group(0)
        digits=int(re.sub(r"\D","",s) or 0)
        if 180000 <= digits <= 300000:
            p=m.start()
            ctx=re.sub(r"\s+"," ",t[max(0,p-160):p+220])
            print("PRICECTX",ctx)
