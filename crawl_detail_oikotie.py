import json, time, re, random, requests
from bs4 import BeautifulSoup

YES = {"kyllä": True, "ei": False}
CITIES = {"helsinki": "Helsinki", "espoo": "Espoo", "vantaa": "Vantaa"}
FREE_TEXT = ["Muut kustannukset", "Lisätiedot", "Muut ehdot", "Vuokrauksen erityisehdot"]
COSTS = {  # khoản: (nhãn chính, từ khoá trong văn bản tự do, € tối thiểu, € tối đa)
    "water":       (["Vesimaksu", "Vesimaksun lisätiedot"], ["vesi", "vede", "water"], 5, 150),
    "electricity": (["Sähkömaksu", "Keskimääräinen sähkönkulutus"], ["sähkö", "electric"], 5, 200),
    "sauna":       (["Saunamaksu"], ["sauna"], 1, 100),
    "internet":    (["Kiinteistön laajakaistayhteys", "Tietoliikennepalvelut"], ["laajakaista", "internet", "netti"], 1, 100),
    "parking":     (["Autopaikan kustannukset", "Pysäköintimaksu"], ["autopaik", "pysäköinti", "autohalli", "parking"], 5, 300),
}
PERIOD = ["kk", "kuuk", "month", "hlö", "henk", "kerta", "vuosi", "year"]

def to_int(t):
    m = re.search(r"\d+", t or "")
    return int(m.group()) if m else None

def to_eur(t):
    """'1 029 € / kk' -> 1029.0 ; '772,41 € / kk' -> 772.41"""
    m = re.search(r"\d[\d ]*(?:,\d+)?", (t or "").replace("\xa0", " "))
    return float(m.group().replace(" ", "").replace(",", ".")) if m else None

def classify(t, need_period=False):
    """văn bản về 1 khoản phí -> (status, eur, unit), không chắc -> None"""
    t = t.lower().replace("\xa0", " ")
    if re.search(r"/\s*m2|/\s*m²|neliö", t):
        return None                                     # tính theo m²
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:€|e\b|eur)", t)
    if any(k in t for k in ["sisältyy", "sis.", "kuuluu vuokra", "maksuton", "ilmai", "included"]):
        if m and float(m.group(1).replace(",", ".")) > 0:
            return None                                 # vừa "đã gồm" vừa có số tiền
        return "included", None, None
    if m and need_period and not any(p in t for p in PERIOD):
        m = None                                        # số trần trong văn bản tự do
    if "hlö" in t or "henk" in t:                       unit = "per_person_month"
    elif "kerta" in t and "kk" not in t:                unit = "per_use"
    else:                                               unit = "per_month"
    if m:
        eur = float(m.group(1).replace(",", "."))
        return ("included", None, None) if eur == 0 else ("extra_fixed", eur, unit)
    if any(k in t for k in ["kulutuksen mukaan", "kulutukseen perustuv", "kulutuksen perusteella",
                            "sopimu", "toteutuneen", "ennakko"]):
        return "extra_usage", None, None
    if "hinnaston" in t:
        return "extra_fixed", None, None
    return None

def cost(tbl, primary, keywords, lo, hi, free_text):
    r = None
    joined = " ".join(tbl[l] for l in primary if l in tbl)          # gộp các nhãn chính
    if joined:
        r = classify(joined)
    if r is None:
        for part in re.split(r"[.,;](?=\s|$)|\n", free_text):      # mệnh đề có từ khoá
            if any(k in part.lower() for k in keywords) and (r := classify(part, need_period=True)):
                break
    if r is None or (r[1] is not None and not lo <= r[1] <= hi):     # ngoài ngưỡng -> không chắc
        return "unknown", None, None
    return r

def parse(soup, url):
    ld = None
    for sc in soup.find_all("script", type="application/ld+json"):
        data = json.loads(sc.string)
        if "Apartment" in str(data.get("@type")):
            ld = data; break
    if ld is None:
        raise ValueError("no Apartment ld+json")
    addr = ld.get("address") or {}

    tbl = {}                                                        # bảng chi tiết
    for row in soup.select(".info-table__row"):
        k, v = row.select_one(".info-table__title"), row.select_one(".info-table__value")
        if k and v:
            tbl[k.get_text(" ", strip=True)] = v.get_text(" ", strip=True).replace("\xa0", " ")
    grid = {}                                                       # khối thông tin nhanh
    for it in soup.select(".details-grid__item"):
        for k, v in zip(it.select(".details-grid__item-title"), it.select(".details-grid__item-value")):
            grid[k.get_text(" ", strip=True)] = v.get_text(" ", strip=True).replace("\xa0", " ")
    get = tbl.get
    yes = lambda k: YES.get((get(k) or "").lower())
    free_text = "\n".join(get(k) or "" for k in FREE_TEXT)
    low = free_text.lower()

    slug = url.rstrip("/").split("/")[-2].lower()                   # city: URL -> grid -> null
    city = CITIES.get(slug) or CITIES.get((grid.get("Kaupunki") or "").strip().lower())

    postal = addr.get("postalCode")                                 # chỉ nhận 00xxx-02xxx
    postal = postal if re.fullmatch(r"0[0-2]\d{3}", postal or "") else None

    district = re.sub(r"\(.*?\)", "", (get("Kaupunginosa") or "").split("/")[0]).strip()
    district = district.title() if district and not re.search(r"\d", district) else None

    rent = (ld.get("offers") or {}).get("price") or to_eur(get("Vuokra/kk")) or to_eur(grid.get("Vuokra/kk"))
    rent = float(rent) if rent else None

    area = (ld.get("floorSize") or {}).get("value")
    area = float(area) if area and area > 0 else None

    floors = re.findall(r"\d+", get("Kerros") or "")
    floor = int(floors[0]) if floors else None
    floor_total = int(floors[1]) if len(floors) > 1 else to_int(get("Kerroksia"))
    if floor is not None and floor_total is not None and floor > floor_total:
        floor = None

    year_built = to_int(get("Rakennusvuosi"))
    if year_built is not None and not 1800 <= year_built <= 2030:
        year_built = None
    year_in_use = to_int(get("Rakennuksen käyttöönottovuosi"))
    if year_in_use is not None and not 1800 <= year_in_use <= 2030:
        year_in_use = None

    equip = f'{get("Kylpyhuoneen varusteet") or ""} {get("Keittiön varusteet") or ""}'.lower()
    if re.search(r"pesukone\s*liitä|pesukoneen liitä", equip):  washing = False
    elif re.search(r"(?<!astian)pesukone", equip):              washing = True
    else:                                                       washing = None

    if re.search(r"tupakointi (on )?kielletty|tupakointi sallittu: ?ei|ei tupakoida|savuton", low): smoking = False
    elif re.search(r"tupakointi (on )?sallittu(?!: ?ei)", low):                                    smoking = True
    else:                                                                                          smoking = None

    pets = yes("Lemmikkieläimet sallittu")
    if pets is None and re.search(r"lemmik\w* (on )?sallittu", low):
        pets = True

    out = {
        "listing_id":     str(ld.get("identifier")),
        "url":            url,
        "street_address": (get("Sijainti") or "").split(",")[0].strip() or None,
        "postal_code":    postal,
        "city":           city,
        "district":       district,
        "area_m2":        area,
        "rooms":          ld.get("numberOfRooms"),
        "floor":          floor,
        "floor_total":    floor_total,
        "condition":      get("Kunto"),
        "has_balcony":    yes("Parveke"),
        "has_own_sauna":  yes("Asunnossa sauna"),
        "furnished":      yes("Vuokrataan kalustettuna"),
        "has_washing_machine": washing,
        "pets_allowed":   pets,
        "smoking_allowed": smoking,
        "kitchen_equipment":  get("Keittiön varusteet"),
        "bathroom_equipment": get("Kylpyhuoneen varusteet"),
        "rent_eur":       rent,
    }
    for name, (primary, keywords, lo, hi) in COSTS.items():
        out[f"{name}_status"], out[f"{name}_eur"], out[f"{name}_unit"] = cost(tbl, primary, keywords, lo, hi, free_text)
    out.update({
        "building_type":    get("Rakennuksen tyyppi"),
        "year_built":       year_built,
        "year_in_use":      year_in_use,
        "has_elevator":     yes("Hissi"),
        "has_shared_sauna": yes("Taloyhtiössä on sauna"),
        "housing_company":  get("Taloyhtiön nimi"),
    })
    return out


# ---------- vòng lặp chính ----------
full_field_listing = {}
gone, failed, parse_error = [], [], []
try:
    for item in listings:
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
            full_field_listing[item["id"]] = parse(soup, item["url"])
        except Exception as e:                          # trang lạ -> ghi lại, đi tiếp
            parse_error.append(item) 
            print(f"parse error {item['id']}: {e}")
            continue

        print(f"ok {item['id']} ({len(full_field_listing)})")
finally:                                                # dừng giữa chừng vẫn lưu phần đã lấy
    with open("listing_details.json", "w", encoding="utf-8") as f:
        json.dump(list(full_field_listing.values()), f, ensure_ascii=False, indent=2)
    with open("gone.json", "w", encoding="utf-8") as f:
        json.dump(gone, f, ensure_ascii=False, indent=2)
    with open("failed.json", "w", encoding="utf-8") as f:
        json.dump(failed, f, ensure_ascii=False, indent=2)
    with open("parse_error.json", "w", encoding="utf-8") as f:
        json.dump(parse_error, f, ensure_ascii=False, indent=2)
    print(f"ok={len(full_field_listing)} gone={len(gone)} failed={len(failed)}")
    
