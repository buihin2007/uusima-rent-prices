import json
import time
import random
from playwright.sync_api import sync_playwright, Error

URL = "https://asunnot.oikotie.fi/vuokra-asunnot?pagination={page}&locations=%5B%5B64,6,%22Helsinki%22%5D,%5B65,6,%22Vantaa%22%5D,%5B39,6,%22Espoo%22%5D%5D&cardType=101&secondarySearchType=1"
JS = r"""() => [...document.querySelectorAll(".cards-v3__card card-v3")].map(c => {
  const a = c.querySelector("a.ot-card-v3");
  if (!a) return null;
  const raw = c.querySelector(".card-v3-text-container__heading")?.innerText || "";
  const num = raw.split(",")[0].replace(/\D/g, "");
  return {
    id:        new URL(a.href).pathname.split("/").pop(),
    url:       a.href.split("?")[0],
    price_eur: num ? Number(num) : null,
  };
}).filter(Boolean)"""
CARD = ".cards-v3__card card-v3"
NO_RESULTS = "ei nyt löytynyt ilmoituksia"   

seen = {}
n=1
            
def current_page(page):
    txt = page.locator("pagination-indication span[ng-bind]").first.inner_text()
    return int(txt.strip().split("/")[0])
def fetch(page, url, maxretry =3):
        for i in range(maxretry):
            wait = 3 ** (i+1)
            try:
                res = page.goto(url, timeout = 30000)
            except Error as e:
                print(f"timeout or network connection problem: {e}, {i+1} tries")
                time.sleep(wait)
                continue
            if res is None:
                print(f"no response, try {i+1}")
                time.sleep(wait)
                continue
            if res.status in (403, 429, 404, 410):
                return "blocked or gone"
            if res.status in (500, 502, 503, 504):
                print(f" server error, {i+1} tries, wait {wait} seconds before fetching again.")
                time.sleep(wait)
                continue
            return "ok"
        return "failed"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False, slow_mo=500)
    page = browser.new_page()
    
    while True:
        status = fetch(page, URL.format(page=n))
        if status == "blocked or gone":
            print("We are blocked or page gone. Stopped")
            break
        if status == "failed":
            print("can not fetch this url. stopped")
            break
        if n>current_page(page):
            print(f"end.")
            break
        page.wait_for_selector(".cards-v3__card card-v3")
        for card in page.evaluate(JS):
            seen[card["id"]] = card
            print(f"obtained {card["id"]}")
        print(f"done page {n}, {len(seen)} listings obtained")
        n+=1
        time.sleep(random.uniform(0.5,1))
    browser.close()
json.dump(list(seen.values()), open("listings_new.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print(f"saved {len(seen)} listings into listings_new.json")