# print("hellow world")

import requests
res = requests.get("http://www.naver.com")
print(res.text)