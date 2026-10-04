import requests,re
url="https://www.ksdenki.com/shop/r/r09023124_m4900030718_og/"
t=requests.get("https://r.jina.ai/"+url,headers={"Accept":"text/plain","User-Agent":"Mozilla/5.0","X-Locale":"ja-JP"},timeout=45).text
print("chars",len(t))
for key in ["MJX54J/A","239,800","カートに入れる","在庫あり","在庫なし","販売終了","予約終了","在庫限り","Web価格"]:
    poss=[m.start() for m in re.finditer(re.escape(key),t,re.I)]
    if poss: print(key,poss[:20],"count",len(poss))
for m in re.finditer("MJX54J/A",t,re.I):
    p=m.start()
    print("CTX",re.sub(r"\s+"," ",t[max(0,p-500):p+1200]))
