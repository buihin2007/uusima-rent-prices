import json, time, re, os, requests
from bs4 import BeautifulSoup

YES = {"kyllä": True, "ei": False}
PERIOD_RE = re.compile(r"aikavälillä\s+(\d{1,2}\.\d{1,2}\.\d{4})\s*-\s*(\d{1,2}\.\d{1,2}\.\d{4})")
FREE_TEXT = ["Muut kustannukset", "Lisätiedot", "Muut ehdot", "Vuokrauksen erityisehdot"]
COSTS = {  # khoản: (nhãn chính theo thứ tự ưu tiên, từ khoá tìm trong văn bản tự do)
    "water":       (["Vesimaksun lisätiedot", "Vesimaksu"], ["vesi", "vede"]),
    "electricity": (["Sähkömaksu", "Keskimääräinen sähkönkulutus"], ["sähkö"]),
    "sauna":       (["Saunamaksu"], ["sauna"]),
    "internet":    (["Kiinteistön laajakaistayhteys", "Tietoliikennepalvelut"], ["laajakaista", "internet", "netti"]),
    "parking":     (["Autopaikan kustannukset", "Pysäköintimaksu"], ["autopaik", "pysäköinti", "autohalli"]),
}

with open("failed.json", "r", encoding="utf-8") as f:
    failed_listings = json.load(f)
os.remove("failed.json")
s = requests.Session()
def fetch(url, maxretry = 3):
    for i in range(maxretry):
        wait = 3 ** (i+1)
        try:
            res = s.get(url, timeout = 30)
        except requests.RequestException as e:
            print(f"timeout or network connection problem: {e}, {i+1} tries")
            time.sleep(wait)
            continue
        if res.status_code in (403, 429):
            return "blocked", res
        if res.status_code in (404,410):
            return "gone", res
        if res.status_code in (500, 502, 503, 504):
            print(f" server error, {i+1} tries, wait {wait} seconds before fetching again.")
            time.sleep(wait)
            continue
        return "ok", res
    return "failed", None
def to_int(t):
    m = re.search(r"\d+", t or "")
    return int(m.group()) if m else None

def classify(t):
    
    t = t.lower().replace("\xa0", " ")
    if any(k in t for k in ["sisältyy", "sis.", "kuuluu vuokra", "maksuton", "ilmai"]):
        return "included", None, None
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:€|e\b|eur)", t)
    unit = "per_use" if "kerta" in t else "per_person_month" if "hlö" in t or "henk" in t else "per_month"
    if m:
        return "extra_fixed", float(m.group(1).replace(",", ".")), unit
    if any(k in t for k in ["kulutuksen mukaan", "sopimuksen", "toteutuneen", "ennakko"]):
        return "extra_usage", None, None
    if "hinnaston" in t:
        return "extra_fixed", None, None
    return None

def cost(tbl, primary, keywords, free_text):
    for label in primary:                                           # 1. nhãn chính
        if label in tbl and (r := classify(tbl[label])):
            return r
    for sentence in re.split(r"(?<=[.!?])\s+|\n|;", free_text):     # 2. câu có từ khoá
        if any(k in sentence.lower() for k in keywords) and (r := classify(sentence)):
            return r
    return "unknown", None, None

def parse(soup):
    ld = None                                                       # khối ld+json của căn hộ
    for sc in soup.find_all("script", type="application/ld+json"):
        data = json.loads(sc.string)
        if "Apartment" in str(data.get("@type")):
            ld = data; break
    if ld is None:
        raise ValueError("no Apartment ld+json")
    addr, geo = ld.get("address") or {}, ld.get("geo") or {}

    tbl = {}                                                        # nhãn -> giá trị
    for row in soup.select(".info-table__row"):
        k, v = row.select_one(".info-table__title"), row.select_one(".info-table__value")
        if k and v:
            tbl[k.get_text(" ", strip=True)] = v.get_text(" ", strip=True).replace("\xa0", " ")
    get = tbl.get
    yes = lambda k: YES.get((get(k) or "").lower())

    free_text = "\n".join(get(k) or "" for k in FREE_TEXT)
    low = free_text.lower()
    floors = re.findall(r"\d+", get("Kerros") or "")

    equip = f'{get("Kylpyhuoneen varusteet") or ""} {get("Keittiön varusteet") or ""}'.lower()
    if re.search(r"pesukone\s*liitä|pesukoneen liitä", equip):  washing = False   # chỉ có chỗ cắm
    elif re.search(r"(?<!astian)pesukone", equip):              washing = True    # loại trừ máy rửa bát
    else:                                                       washing = None

    if re.search(r"tupakointi (on )?kielletty|tupakointi sallittu: ?ei|savuton", low): smoking = False
    elif "tupakointi sallittu" in low:                                                smoking = True
    else:                                                                             smoking = None

    pets = yes("Lemmikkieläimet sallittu")
    if pets is None and re.search(r"lemmik\w* (on )?sallittu", low):
        pets = True

    out = {
        "listing_id":     (ld.get("url") or "").rstrip("/").split("/")[-1],
        "url":            ld.get("url"),
        "street_address": (get("Sijainti") or "").split(",")[0].strip() or None,
        "postal_code":    addr.get("postalCode"),
        "city":           (addr.get("addressRegion") or "").title() or None,
        "district":       get("Kaupunginosa"),
        "lat":            geo.get("latitude"),
        "lon":            geo.get("longitude"),
        "area_m2":        (ld.get("floorSize") or {}).get("value"),
        "rooms":          ld.get("numberOfRooms"),
        "floor":          int(floors[0]) if floors else None,
        "floor_total":    int(floors[1]) if len(floors) > 1 else to_int(get("Kerroksia")),
        "condition":      get("Kunto"),
        "has_balcony":    yes("Parveke"),
        "has_own_sauna":  yes("Asunnossa sauna"),
        "furnished":      yes("Vuokrataan kalustettuna"),
        "has_washing_machine": washing,
        "pets_allowed":   pets,
        "smoking_allowed": smoking,
        "kitchen_equipment":  get("Keittiön varusteet"),
        "bathroom_equipment": get("Kylpyhuoneen varusteet"),
        "rent_eur":       (ld.get("offers") or {}).get("price"),
    }
    for name, (primary, keywords) in COSTS.items():
        out[f"{name}_status"], out[f"{name}_eur"], out[f"{name}_unit"] = cost(tbl, primary, keywords, free_text)
    out.update({
        "building_type":    get("Rakennuksen tyyppi"),
        "year_built":       to_int(get("Rakennusvuosi")),
        "year_in_use":      to_int(get("Rakennuksen käyttöönottovuosi")),
        "has_elevator":     yes("Hissi"),
        "has_shared_sauna": yes("Taloyhtiössä on sauna"),
        "housing_company":  get("Taloyhtiön nimi"),
    })
    return out



if os.path.exists("listing_details.json") and os.path.getsize("listing_details.json") > 0:
    with open("listing_details.json", "r", encoding="utf-8") as f:
        data = json.load(f)
else:
    data = []

gone, failed, parse_error = [], [], []
try:
    for item in failed_listings:
        status, res = fetch(item["url"])
        if status == "blocked":
            print("blocked, stopped.")
            break
        if status == "gone":
            gone.append(item)
            print(f"page of {item['id']} gone")
            continue
        if status == "failed":
            failed.append(item)
            print(f"fail to fetch {item['id']}")
            continue

        soup = BeautifulSoup(res.text, "html.parser")

        # tin hết hạn: vẫn 200 nhưng có khối .listing-inactive, hoặc bị redirect sang trang khác
        if soup.select_one(".listing-inactive") or item["id"] not in res.url:
            gone.append(item)
            print(f"{item['id']} expired")
            continue

        try:
            data.append(parse(soup))
        except Exception as e:                          # trang lạ -> ghi lại, đi tiếp
            parse_error.append(item) 
            print(f"parse error {item['id']}: {e}")
            continue

        print(f"ok {item['id']} ({len(data)})")
finally:                                                # dừng giữa chừng vẫn lưu phần đã lấy
    with open("listing_details.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    with open("gone.json", "w", encoding="utf-8") as f:
        json.dump(gone, f, ensure_ascii=False, indent=2)
    with open("failed.json", "w", encoding="utf-8") as f:
        json.dump(failed, f, ensure_ascii=False, indent=2)
    with open("parse_error.json", "w", encoding="utf-8") as f:
        json.dump(parse_error, f, ensure_ascii=False, indent=2)
    print(f"ok={len(data)} gone={len(gone)} failed={len(failed)}")
    
