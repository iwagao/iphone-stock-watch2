import requests,re
url="https://www.amazon.co.jp/dp/B0HJ9ZYXPV"
t=requests.get("https://r.jina.ai/"+url,headers={"Accept":"text/plain","User-Agent":"Mozilla/5.0","X-Locale":"ja-JP"},timeout=45).text
print("chars",len(t))
for key in ["Add to cart","Buy Now","Ships from","Sold by","販売元","Amazon.co.jp","Currently unavailable","Temporarily out of stock"]:
    poss=[m.start() for m in re.finditer(re.escape(key),t,re.I)]
    print(key,poss[:20],"count",len(poss))
for key in ["Add to cart","Buy Now","Ships from","Sold by","販売元"]:
    for m in list(re.finditer(re.escape(key),t,re.I))[:8]:
        p=m.start()
        print("CTX",key,re.sub(r"\s+"," ",t[max(0,p-500):p+900]))
