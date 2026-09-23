#!/usr/bin/env python3
"""Restaure bienici_live.details (galerie photos + description + titre + attributs)
depuis l'API détail Bien'ici, gratuite et publique.

L'enrichissement d'origine s'est arrêté le 30/06/2026 : depuis, 100 % des nouvelles
annonces ont details=NULL, donc une galerie vide dans l'app alors que les photos
existent côté source (17 pour l'annonce témoin).

Usage :
    python3 bienici_details_backfill.py            # tout le reliquat
    python3 bienici_details_backfill.py --limit 20 # test
    python3 bienici_details_backfill.py --dry-run  # n'écrit rien

Reprise : relancer la commande, seules les annonces details IS NULL sont traitées.
"""
import argparse, json, pathlib, sys, threading, time, urllib.error, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor

import psycopg

DSN = pathlib.Path.home().joinpath(".marlo_pg_url").read_text().strip()
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
WORKERS = 10          # ponytail: 10 threads suffisent (~25 ann/s), monter si Bien'ici tient
BATCH = 300           # lignes par UPDATE
_lock = threading.Lock()
_stats = {"ok": 0, "vides": 0, "morts": 0, "erreurs": 0}


def fetch(aid):
    """Renvoie le JSON de l'annonce, 'GONE' si retirée, None si échec réseau."""
    url = f"https://www.bienici.com/realEstateAd.json?id={urllib.parse.quote(aid)}"
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Accept": "application/json",
        "Referer": "https://www.bienici.com/"})
    for essai in range(3):
        try:
            with urllib.request.urlopen(req, timeout=25) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (404, 410):
                return "GONE"
            time.sleep(1.0 + essai)
        except Exception:
            time.sleep(1.0 + essai)
    return None


def to_details(d):
    """Mappe la réponse API sur la structure `details` d'origine (clés identiques
    à celles des annonces d'avant le 30/06, vérifiées une par une)."""
    photos = [p.get("url") for p in (d.get("photos") or []) if p.get("url")]
    district = d.get("district") or {}
    return {
        "photos": photos,
        "nb_photos": len(photos),
        "title": d.get("title"),
        "description": d.get("description"),
        "etage": d.get("floor"),
        "annee": d.get("yearOfConstruction"),
        "chauffage": d.get("heating"),
        "quartier": district.get("name"),
        "pieces": d.get("roomsQuantity"),
        "chambres": d.get("bedroomsQuantity"),
        "mandat_exclusif": d.get("isExclusiveSaleMandate"),
        "copro": d.get("isInCondominium"),
        "neuf": d.get("newProperty"),
    }


def traiter(aid):
    d = fetch(aid)
    if d is None:
        with _lock:
            _stats["erreurs"] += 1
        return None
    if d == "GONE":
        # annonce retirée : on marque traité pour ne pas la re-tenter à chaque run.
        with _lock:
            _stats["morts"] += 1
        return (aid, json.dumps({"photos": [], "nb_photos": 0, "_retiree": True}))
    det = to_details(d)
    with _lock:
        _stats["ok" if det["photos"] else "vides"] += 1
    return (aid, json.dumps(det, ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    with psycopg.connect(DSN, autocommit=True) as conn:
        sql = ("SELECT id FROM bienici_live "
               "WHERE status='active' AND details IS NULL ORDER BY first_seen DESC")
        if args.limit:
            sql += f" LIMIT {int(args.limit)}"
        ids = [r[0] for r in conn.execute(sql).fetchall()]
        total = len(ids)
        print(f"{total} annonces à enrichir", flush=True)
        if not total:
            return

        t0 = time.time()
        traites = 0
        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            lot = []
            for res in pool.map(traiter, ids):
                if res:
                    lot.append(res)
                if len(lot) >= BATCH:
                    traites += ecrire(conn, lot, args.dry_run)
                    lot = []
                    vitesse = traites / max(time.time() - t0, 1)
                    reste = (total - traites) / max(vitesse, 0.1) / 60
                    print(f"  {traites}/{total} · {vitesse:.1f}/s · reste ~{reste:.0f} min "
                          f"· {_stats}", flush=True)
            if lot:
                traites += ecrire(conn, lot, args.dry_run)

        print(f"TERMINE {traites}/{total} en {(time.time()-t0)/60:.1f} min · {_stats}", flush=True)


def ecrire(conn, lot, dry):
    if dry:
        return len(lot)
    with conn.cursor() as cur:
        cur.executemany(
            "UPDATE bienici_live SET details = %s::jsonb WHERE id = %s AND details IS NULL",
            [(d, aid) for aid, d in lot])
    return len(lot)


if __name__ == "__main__":
    main()
