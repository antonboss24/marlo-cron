#!/usr/bin/env python3
"""Collecteur NATIONAL Bien'ici exhaustif — découpage par PRIX (binary-split), parallèle.
Le prix partitionne TOUTES les annonces (aucune jetée). Si un point de prix ultra-dense plafonne
encore (fenêtre <=1000 et >2400), on découpe par TYPE (toujours présent). Jamais par pièces
(qui jetait les annonces sans pièces déclarées). Dédup par id, CSV incrémental. insee = district.code_insee.
"""
import os, sys, json, time, csv, datetime, pathlib, urllib.request, urllib.parse, threading
import concurrent.futures as cf

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
ALL_TYPES = ["house","flat","loft","townhouse","castle","manor","terrain","building","premises","parking"]
CAP = 2400
PRICE0 = [0,50000,80000,110000,140000,170000,200000,230000,270000,320000,400000,500000,700000,1000000,2000000,5000000,20000000,None]
OUT_CSV = pathlib.Path(os.environ.get("NAT_OUT", str(pathlib.Path.home()/"Desktop"/"biens_national.csv")))
COLS = ["id","property_type","city","postal_code","insee","price","price_max","price_per_m2","surface_m2",
        "rooms","bedrooms","dpe","ges","price_has_decreased","ad_created_by_pro","is_exclusive_mandate",
        "reference","publication_date","modification_date","title","nb_photos","photo_url","url_annonce"]

def get(types, pmin, pmax, page=1):
    f = {"size":100,"from":(page-1)*100,"filterType":"buy","propertyType":types,"page":page,
         "resultsPerPage":100,"maxAuthorizedResults":CAP,"onTheMarket":[True],"minPrice":pmin}
    if pmax is not None: f["maxPrice"] = pmax
    url = "https://www.bienici.com/realEstateAds.json?filters=" + urllib.parse.quote(json.dumps(f))
    for t in range(4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent":UA,"Accept":"application/json","Referer":"https://www.bienici.com/"})
            with urllib.request.urlopen(req, timeout=40) as r:
                d = json.load(r)
            return d.get("realEstateAds", []), d.get("total", 0)
        except Exception:
            if t == 3: return [], -1
            time.sleep(1.0 + t)

def map_row(a):
    pr = a.get("price")
    if isinstance(pr, list):
        nums = [x for x in pr if isinstance(x,(int,float))]
        price = min(nums) if nums else None; price_max = max(nums) if nums else None
    else:
        price = pr; price_max = None
    d = a.get("district") or {}; photos = a.get("photos") or []
    return [a.get("id"), a.get("propertyType"), a.get("city"), a.get("postalCode"),
            d.get("code_insee") or d.get("insee_code"), price, price_max, a.get("pricePerSquareMeter"),
            a.get("surfaceArea"), a.get("roomsQuantity"), a.get("bedroomsQuantity"),
            a.get("energyClassification"), a.get("greenhouseGazClassification"),
            a.get("priceHasDecreased"), a.get("adCreatedByPro"), a.get("isExclusiveSaleMandate"),
            a.get("reference"), a.get("publicationDate"), a.get("modificationDate"), a.get("title"),
            len(photos), (photos[0].get("url") if photos else None),
            "https://www.bienici.com/annonce/"+str(a.get("id"))]

seen = set(); lock = threading.Lock(); writer = None; done = [0]

def collect(leaf):
    """leaf = (types, pmin, pmax). Aspire ; renvoie total annoncé."""
    types, pmin, pmax = leaf
    page = 1; total = 0
    while page <= 24:
        ads, total = get(types, pmin, pmax, page)
        if total == -1: total = CAP; break
        if not ads: break
        with lock:
            for a in ads:
                i = str(a.get("id"))
                if i in seen: continue
                seen.add(i); writer.writerow(map_row(a))
        if page*100 >= min(total, CAP): break
        page += 1
    with lock:
        done[0] += 1
        if done[0] % 40 == 0: print(f"  {done[0]} tranches, {len(seen)} uniques", flush=True)
    return total

def split(leaf):
    """Renvoie les sous-tranches d'une feuille qui plafonne."""
    types, pmin, pmax = leaf
    hi = pmax if pmax is not None else 100000000
    if (hi - pmin) > 1000:                       # 1) binary-split prix
        mid = (pmin + hi) // 2
        return [(types, pmin, mid), (types, mid+1, pmax)]
    if len(types) > 1:                            # 2) prix au plancher -> split par type
        return [([t], pmin, pmax) for t in types]
    return []                                     # 3) résiduel irréductible (rarissime)

def main():
    global writer
    t0 = time.time()
    f = open(OUT_CSV, "w", newline="", encoding="utf-8")
    writer = csv.writer(f); writer.writerow(COLS)
    queue = [(ALL_TYPES, PRICE0[k], PRICE0[k+1]) for k in range(len(PRICE0)-1)]
    rounds = 0
    while queue and rounds < 30:
        rounds += 1
        print(f"ROUND {rounds} : {len(queue)} tranches, {len(seen)} uniques", flush=True)
        nxt = []
        with cf.ThreadPoolExecutor(max_workers=12) as ex:
            totals = list(ex.map(collect, queue))
        for leaf, total in zip(queue, totals):
            if total > CAP: nxt.extend(split(leaf))
        queue = nxt
    f.close()
    print(f"FINI : {len(seen)} annonces uniques -> {OUT_CSV} en {int(time.time()-t0)}s", flush=True)

if __name__ == "__main__":
    main()
