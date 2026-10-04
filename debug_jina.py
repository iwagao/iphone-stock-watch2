import requests,re
from bs4 import BeautifulSoup
urls=[
("desktop","https://www.amazon.co.jp/dp/B0HJ9ZYXPV"),
("mobile","https://www.amazon.co.jp/gp/aw/d/B0HJ9ZYXPV"),
("detail","https://www.amazon.co.jp/dp/B0HJ9ZYXPV?th=1&psc=1&language=ja_JP"),
("search","https://www.amazon.co.jp/s?k=B0HJ9ZYXPV"),
]
headers={"User-Agent":"Mozilla/5.0 (Linux; Android 16; Pixel 10 Pro XL) AppleWebKit/537.36 Chrome/140.0 Mobile Safari/537.36","Accept-Language":"ja-JP,ja;q=0.9"}
for name,url in urls:
    try:
        r=requests.get(url,headers=headers,timeout=25,allow_redirects=True)
        t=r.text
        s=BeautifulSoup(t,"html.parser")
        text=" ".join(s.stripped_strings)
        prices=re.findall(r"(?:￥|¥)?\s*([0-9]{1,3}(?:,[0-9]{3})+)\s*円?",text)
        print(name,"status",r.status_code,"len",len(t),"final",r.url)
        print("price samples",prices[:10])
        print("cart",bool(s.select_one("#add-to-cart-button")),"buy",bool(s.select_one("#buy-now-button")))
        print("availability",(s.select_one("#availability").get_text(" ",strip=True) if s.select_one("#availability") else "")[:300])
        print("merchant",(s.select_one("#merchant-info").get_text(" ",strip=True) if s.select_one("#merchant-info") else "")[:300])
        print("title",(s.select_one("#productTitle").get_text(" ",strip=True) if s.select_one("#productTitle") else "")[:300])
    except Exception as e:
        print(name,"ERROR",repr(e))
