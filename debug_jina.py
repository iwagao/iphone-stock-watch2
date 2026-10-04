import requests,re
TARGETS={
"Amazon.co.jp":"https://www.amazon.co.jp/dp/B0HJ9ZYXPV",
"ヤマダ":"https://www.yamada-denkiweb.com/7164953012/",
"ケーズ":"https://www.ksdenki.com/shop/g/g4549995734546/",
"ヨドバシ":"https://www.yodobashi.com/?word=MJX54J%2FA",
}
markers=["MJX54J/A","4549995734546","iPhone 18 Pro Max"]
for name,url in TARGETS.items():
    t=requests.get("https://r.jina.ai/"+url,headers={"Accept":"text/plain","User-Agent":"Mozilla/5.0"},timeout=45).text
    low=t.lower()
    poss=[low.find(m.lower()) for m in markers if low.find(m.lower())>=0]
    p=min(poss) if poss else 0
    s=re.sub(r"\s+"," ",t[max(0,p-2500):p+5000])
    print("\n###",name,"###")
    print(s[:7000])
