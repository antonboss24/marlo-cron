"""Batch Bien'ici — TOUT un département, ventes immo.
Usage : python3 bienici_departement.py [code_dept]   (défaut 49)
Communes officielles (geo.api.gouv) -> zone Bien'ici matchée par CP ->
recherche achat paginée (segmentée par prix si > plafond 2400) -> filtre dept ->
dédoublonnage -> CSV riche sur le Bureau + résumé stats.
"""
import sys, json, urllib.request, urllib.parse, time, csv, os, collections, statistics

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
DEPT = (sys.argv[1] if len(sys.argv) > 1 else "49")
PROP = ["house","flat","loft","townhouse","castle","manor","terrain","building","premises","parking"]
SLICES = [(0,50000),(50000,100000),(100000,150000),(150000,200000),(200000,250000),(250000,300000),(300000,400000),(400000,500000),(500000,700000),(700000,1000000),(1000000,1500000),(1500000,2500000),(2500000,5000000),(5000000,None)]

def get_json(url, tries=3):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent":UA,"Accept":"application/json","Referer":"https://www.bienici.com/"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except Exception:
            if i == tries-1: raise
            time.sleep(1.5)

def zone_for(nom, cp):
    items = get_json("https://res.bienici.com/suggest.json?q=" + urllib.parse.quote(f"{nom} {cp}"))
    items = items if isinstance(items, list) else []
    for t in ("city","town","delegated-city","arrondissement"):
        for it in items:
            if it.get("type")==t and it.get("zoneIds"): return it["zoneIds"]
    return items[0]["zoneIds"] if items and items[0].get("zoneIds") else None

def search(zoneIds, pmin=None, pmax=None):
    out=[]; page=1
    while True:
        f={"size":100,"from":(page-1)*100,"filterType":"buy","propertyType":PROP,"page":page,
           "resultsPerPage":100,"maxAuthorizedResults":2400,"onTheMarket":[True],"zoneIdsByTypes":{"zoneIds":zoneIds}}
        if pmin is not None: f["minPrice"]=pmin
        if pmax is not None: f["maxPrice"]=pmax
        d=get_json("https://www.bienici.com/realEstateAds.json?filters="+urllib.parse.quote(json.dumps(f)))
        ads=d.get("realEstateAds",[]); total=d.get("total",0); out+=ads
        if len(out)>=min(total,2400) or not ads or page>=24: break
        page+=1; time.sleep(0.3)
    return out, total

def collect(zoneIds):
    ads,total=search(zoneIds)
    if total>2400:
        ads=[]
        for pmin,pmax in SLICES:
            seg,_=search(zoneIds,pmin,pmax); ads+=seg; time.sleep(0.3)
    return ads

coms=get_json(f"https://geo.api.gouv.fr/departements/{DEPT}/communes?fields=nom,code,codesPostaux,population&format=json")
print(f"{len(coms)} communes dans le {DEPT}", flush=True)
seen={}; vides=0
for i,c in enumerate(sorted(coms,key=lambda x:-(x.get('population') or 0))):
    cp=(c.get("codesPostaux") or [""])[0]
    try:
        z=zone_for(c["nom"], cp)
        if not z: vides+=1; continue
        kept=0
        for a in collect(z):
            if str(a.get("departmentCode"))==DEPT and a.get("id") not in seen:
                a["_commune_req"]=c["nom"]; seen[a["id"]]=a; kept+=1
        if kept==0: vides+=1
    except Exception as e:
        print("  err", c["nom"], str(e)[:40], flush=True)
    time.sleep(0.2)
    if (i+1)%25==0: print(f"  ...{i+1}/{len(coms)} communes — {len(seen)} biens", flush=True)

ads=list(seen.values())
out=os.path.expanduser(os.environ.get("BIENICI_OUT_DIR", "~/Desktop")) + f"/biens_dept_{DEPT}.csv"
os.makedirs(os.path.dirname(out), exist_ok=True)
cols=["id","source","propertyType","commune","city","postalCode","insee","price","pricePerSquareMeter",
      "surfaceArea","roomsQuantity","bedroomsQuantity","energyClassification","greenhouseGazClassification",
      "priceHasDecreased","adCreatedByPro","isExclusiveSaleMandate","reference","publicationDate",
      "modificationDate","title","nb_photos","photo_url"]
with open(out,"w",newline="") as f:
    w=csv.writer(f); w.writerow(cols)
    for a in ads:
        d=a.get("district") or {}; ph=a.get("photos") or []
        purl=(ph[0].get("url_photo") or ph[0].get("url")) if ph and isinstance(ph[0],dict) else ""
        w.writerow([a.get("id"),a.get("id","").split("-")[0],a.get("propertyType"),a.get("_commune_req"),
                    a.get("city"),a.get("postalCode"),d.get("code_insee"),a.get("price"),a.get("pricePerSquareMeter"),
                    a.get("surfaceArea"),a.get("roomsQuantity"),a.get("bedroomsQuantity"),a.get("energyClassification"),
                    a.get("greenhouseGazClassification"),a.get("priceHasDecreased"),a.get("adCreatedByPro"),
                    a.get("isExclusiveSaleMandate"),a.get("reference"),a.get("publicationDate"),
                    a.get("modificationDate"),a.get("title"),len(ph),purl])

def med(xs): xs=[x for x in xs if x]; return statistics.median(xs) if xs else 0
print(f"\n========== RÉSUMÉ BATCH {DEPT} ==========", flush=True)
print(f"Biens uniques : {len(ads)} | communes sans résultat : {vides}")
print(f"Poids CSV : {os.path.getsize(out)/1e6:.1f} Mo  ->  {out}")
print("Types :", dict(collections.Counter(a.get("propertyType") for a in ads)))
pro=sum(1 for a in ads if a.get("adCreatedByPro")); part=len(ads)-pro
print(f"Vendeurs : {pro} pros / {part} particuliers ({100*part/max(len(ads),1):.0f}% particuliers)")
print("DPE :", dict(sorted(collections.Counter(a.get('energyClassification') or '?' for a in ads).items())))
print(f"Baisses de prix : {sum(1 for a in ads if a.get('priceHasDecreased'))} | mandats exclusifs : {sum(1 for a in ads if a.get('isExclusiveSaleMandate'))}")
top_villes=[v for v,_ in collections.Counter(a.get('city') for a in ads if a.get('city')).most_common(3)]
for v in top_villes:
    sub=[a['pricePerSquareMeter'] for a in ads if a.get('city')==v and a.get('propertyType')=='flat' and a.get('pricePerSquareMeter')]
    print(f"  {v}: {len([a for a in ads if a.get('city')==v])} biens | prix/m² appart médian {med(sub):.0f} €")
print("Top sources :", dict(collections.Counter(a.get('id','').split('-')[0] for a in ads).most_common(8)))
