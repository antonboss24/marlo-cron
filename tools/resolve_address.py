#!/usr/bin/env python3
"""Localisateur d'annonce Bien'ici -> adresse exacte + GPS via la base DPE ADEME.
Usage: python3 resolve_address.py <url_ou_id_bienici>
Methode: signature DPE (type+DPE+GES+surface+conso) matchee sur dpe03existant.
Score triangule = Dconso + penalite distance(10/km) + Dsurface  (jamais la conso seule).
Sans DPE (ruine/vierge) -> NO_DPE: bascule facade/enseigne (vision)."""
import sys, json, math, urllib.request, urllib.parse
UA={"User-Agent":"Mozilla/5.0","Accept":"application/json"}
def fetch(u): return json.loads(urllib.request.urlopen(urllib.request.Request(u,headers=UA),timeout=90).read())
def aid(s):
    s=s.strip()
    return urllib.parse.urlparse(s).path.rstrip("/").split("/")[-1] if s.startswith("http") else s
def hav(a,b,c,d):
    R=6371000;p=math.pi/180
    x=math.sin((c-a)*p/2)**2+math.cos(a*p)*math.cos(c*p)*math.sin((d-b)*p/2)**2
    return 2*R*math.asin(math.sqrt(x))
def resolve(arg):
    ad=fetch("https://www.bienici.com/realEstateAd.json?id="+aid(arg))
    tb={"house":"maison","flat":"appartement"}.get(ad.get("propertyType"),ad.get("propertyType"))
    dpe=ad.get("energyClassification"); ges=ad.get("greenhouseGazClassification")
    surf=ad.get("surfaceArea"); conso=ad.get("energyValue") or ad.get("averageAnnualEnergyConsumption")
    cp=ad.get("postalCode"); bi=(ad.get("blurInfo") or {}).get("position") or {}
    clat,clon=bi.get("lat"),bi.get("lon")
    info={"type":tb,"dpe":dpe,"ges":ges,"surface":surf,"conso":conso,"cp":cp,
          "ville":ad.get("city"),"quartier":(ad.get("district") or {}).get("name"),"prix":ad.get("price")}
    if not dpe or dpe in ("NS","VI") or not ges or ges in ("NS","VI"):
        return {"status":"NO_DPE","raison":"pas de DPE exploitable (ruine/vierge) -> fallback facade/enseigne (vision)","annonce":info}
    sel="_geopoint,adresse_ban,surface_habitable_logement,type_batiment,etiquette_dpe,etiquette_ges,conso_5_usages_par_m2_ep"
    rows=fetch("https://data.ademe.fr/data-fair/api/v1/datasets/dpe03existant/lines?q="+urllib.parse.quote(str(cp))+"&q_fields=code_postal_ban&size=10000&select="+urllib.parse.quote(sel)).get("results",[])
    c=[]
    for r in rows:
        if r.get("type_batiment")!=tb or r.get("etiquette_dpe")!=dpe or r.get("etiquette_ges")!=ges: continue
        try: s=float(r.get("surface_habitable_logement"))
        except: continue
        if surf is None or abs(s-surf)>7 or not r.get("_geopoint"): continue
        la,lo=[float(z) for z in r["_geopoint"].split(",")]
        dist=hav(clat,clon,la,lo) if clat else 0
        cd=r.get("conso_5_usages_par_m2_ep")
        try: dc=abs(float(cd)-float(conso)) if (cd and conso) else None
        except: dc=None
        score=(dc if dc is not None else 15)+10.0*(dist/1000.0)+abs(s-surf)
        c.append({"score":round(score,1),"dconso":(round(dc,1) if dc is not None else None),
                  "dist_m":round(dist),"surface":s,"conso_dpe":cd,
                  "gps":[round(la,6),round(lo,6)],"adresse":r.get("adresse_ban")})
    c.sort(key=lambda x:x["score"])
    if not c: return {"status":"NO_MATCH","annonce":info}
    t=c[0]; gap=(c[1]["score"]-t["score"]) if len(c)>1 else 99
    conf="haute" if (t["dconso"] is not None and t["dconso"]<5 and gap>5) else ("moyenne" if gap>4 else "a_verifier")
    g=t["gps"]
    return {"status":"OK","adresse":t["adresse"],"gps":g,"confiance":conf,
            "maps":f"https://www.google.com/maps?q={g[0]},{g[1]}","annonce":info,"top":c[:3]}
if __name__=="__main__":
    if len(sys.argv)<2: print("usage: resolve_address.py <url_ou_id>"); sys.exit(1)
    print(json.dumps(resolve(sys.argv[1]),ensure_ascii=False,indent=2))
