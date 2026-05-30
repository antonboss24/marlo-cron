#!/usr/bin/env python3
"""
Routine quotidienne Marlo · Bien'ici → Supabase
================================================

Pour chaque département cible :
  1. Scrape via ~/Desktop/scrapegraph-test/bienici_departement.py (API publique gratuite)
  2. Pré-traite le CSV (snake_case, parse `price` listes, Int64 nullable, dates, booléens)
  3. DELETE le snapshot du jour (re-run safe) + COPY append → public.bienici_annonces
  4. Récap JSON : nb inserted par dépt, nb nouvelles vs J-1, nb sorties, nb baisses

Stdout    : JSON récap (consommé par la routine Claude Code)
Exit code : 0 si succès complet, 1 si erreur fatale (au moins un dépt KO ≠ fatal)

Dépendances : pandas (uv install ou venv ; voir UV_CMD ci-dessous).
Pré-requis  : ~/.marlo_pg_url (DSN pooler) · psql libpq · scraper Anton existant.
"""
import os, sys, subprocess, json, datetime, pathlib, ast, time

# ─── Config (env-aware : marche en local Mac et en GitHub Action Ubuntu) ──
def _norm_dept(d):
    """Normalise un code dépt : '9' → '09', '2A' stays, '971' stays."""
    d = d.strip()
    if d.isdigit() and len(d) == 1: return d.zfill(2)
    return d
DEPTS         = [_norm_dept(x) for x in os.environ.get("DEPTS", "49,44").split(",") if x.strip()]
TODAY         = datetime.date.today().isoformat()
YESTERDAY     = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
WORK          = pathlib.Path(os.environ.get("WORK_DIR", f"/tmp/bienici_routine_{TODAY}"))
WORK.mkdir(exist_ok=True, parents=True)

# DSN : env var d'abord (GitHub Actions secret), fallback ~/.marlo_pg_url (Mac local)
DSN = os.environ.get("MARLO_PG_URL")
if not DSN:
    local_dsn = pathlib.Path.home() / ".marlo_pg_url"
    if local_dsn.exists():
        DSN = local_dsn.read_text().strip()
if not DSN:
    raise SystemExit("DSN absent : set MARLO_PG_URL env var ou ~/.marlo_pg_url")

# psql : env var, fallback brew Mac, fallback PATH (Linux)
def _find_psql():
    p = os.environ.get("PSQL")
    if p and pathlib.Path(p).exists(): return p
    brew = "/opt/homebrew/Cellar/libpq/18.4/bin/psql"
    if pathlib.Path(brew).exists(): return brew
    return "psql"  # apt-installed
PSQL = _find_psql()

# scraper : à côté du script (cloud) OU ~/Desktop/scrapegraph-test (Mac local)
def _find_scraper():
    here = pathlib.Path(__file__).parent / "bienici_departement.py"
    if here.exists(): return here
    desktop = pathlib.Path.home() / "Desktop/scrapegraph-test/bienici_departement.py"
    if desktop.exists(): return desktop
    raise FileNotFoundError("bienici_departement.py introuvable (cherché à côté du script + ~/Desktop/scrapegraph-test/)")
SCRAPER = _find_scraper()

# pandas via uv si dispo (Mac local), sinon python -c avec pandas installé (GitHub Action)
def _prep_cmd():
    try:
        subprocess.run(["uv", "--version"], capture_output=True, check=True, timeout=5)
        return ["uv", "run", "--with", "pandas", "python3", "-"]
    except Exception:
        return [sys.executable, "-"]  # pandas doit être installé
UV_CMD = _prep_cmd()

# ─── Helpers ────────────────────────────────────────────────────────────────
RENAME = {
    'propertyType':'property_type', 'postalCode':'postal_code',
    'pricePerSquareMeter':'price_per_m2', 'surfaceArea':'surface_m2',
    'roomsQuantity':'rooms', 'bedroomsQuantity':'bedrooms',
    'energyClassification':'dpe', 'greenhouseGazClassification':'ges',
    'priceHasDecreased':'price_has_decreased',
    'adCreatedByPro':'ad_created_by_pro',
    'isExclusiveSaleMandate':'is_exclusive_mandate',
    'publicationDate':'publication_date', 'modificationDate':'modification_date',
}
OUT_COLS = ['id','snapshot_date','source','property_type','commune','city','postal_code','insee',
            'price','price_max','price_per_m2','surface_m2','rooms','bedrooms',
            'dpe','ges','price_has_decreased','ad_created_by_pro','is_exclusive_mandate',
            'reference','publication_date','modification_date','title','nb_photos','photo_url','url_annonce']

PREP_SCRIPT = '''
import pandas as pd, sys, ast
RENAME = {RENAME!r}
OUT = {OUT_COLS!r}
TODAY = "{TODAY}"
src, dst = sys.argv[1], sys.argv[2]

def parse_price(v):
    if v is None or (isinstance(v,float) and pd.isna(v)) or v == "": return (None, None)
    s = str(v).strip()
    if s.startswith("["):
        try:
            vals = ast.literal_eval(s)
            if isinstance(vals, list) and vals:
                nums = [float(x) for x in vals if x is not None]
                return (min(nums), max(nums)) if nums else (None, None)
        except: return (None, None)
    try: return (float(s), None)
    except: return (None, None)

def py_bool(v):
    if v is None or (isinstance(v,float) and pd.isna(v)) or v == "": return None
    s = str(v).strip()
    if s in ("True","true","1"): return True
    if s in ("False","false","0"): return False
    return None

df = pd.read_csv(src, dtype=str, na_values=[""], keep_default_na=False)
df = df.replace({{"": None, "None": None, "nan": None}})
df = df.rename(columns=RENAME)
prices = df["price"].apply(parse_price)
df["price"]     = prices.apply(lambda x: x[0])
df["price_max"] = prices.apply(lambda x: x[1])
for c in ("price_per_m2","surface_m2"): df[c] = pd.to_numeric(df[c], errors="coerce")
for c in ("rooms","bedrooms","nb_photos"): df[c] = pd.to_numeric(df[c], errors="coerce").astype("Int64")
for c in ("price_has_decreased","ad_created_by_pro","is_exclusive_mandate"): df[c] = df[c].apply(py_bool)
df["url_annonce"] = df["id"].apply(lambda x: f"https://www.bienici.com/annonce/{{x}}" if x else None)
df["snapshot_date"] = TODAY
df_out = df[OUT]
df_out.to_csv(dst, index=False, na_rep="", sep=";")
print(f"{{len(df_out)}}")
'''.format(RENAME=RENAME, OUT_COLS=OUT_COLS, TODAY=TODAY)

# ─── Steps ──────────────────────────────────────────────────────────────────
def log(msg):
    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {msg}", file=sys.stderr, flush=True)

def scrape(dept):
    """Lance le scraper. Output : $BIENICI_OUT_DIR/biens_dept_{dept}.csv (default ~/Desktop)."""
    out_dir = pathlib.Path(os.environ.get("BIENICI_OUT_DIR", str(pathlib.Path.home() / "Desktop")))
    out_dir.mkdir(parents=True, exist_ok=True)
    out_csv = out_dir / f"biens_dept_{dept}.csv"
    if out_csv.exists(): out_csv.unlink()
    log(f"  scrape dept {dept} → {out_csv}")
    env = {**os.environ, "BIENICI_OUT_DIR": str(out_dir)}
    res = subprocess.run([sys.executable, str(SCRAPER), str(dept)],
                         capture_output=True, text=True, timeout=2400, env=env)
    if res.returncode != 0:
        raise RuntimeError(f"scrape exit {res.returncode}: {res.stderr[-400:]}")
    if not out_csv.exists():
        raise FileNotFoundError(f"no output CSV for dept {dept}")
    return out_csv

def prepare(csv_in, dept):
    """Pré-traite le CSV via uv+pandas. Retourne (path, n_rows)."""
    out_clean = WORK / f"biens_{dept}_clean.csv"
    res = subprocess.run(UV_CMD + [str(csv_in), str(out_clean)],
                         input=PREP_SCRIPT, capture_output=True, text=True, timeout=120)
    if res.returncode != 0:
        raise RuntimeError(f"prep exit {res.returncode}: {res.stderr[-400:]}")
    n = int((res.stdout.strip().split('\n') or ['0'])[-1])
    log(f"  prep dept {dept} ok ({n} lignes)")
    return out_clean, n

def psql_run(sql):
    """Exécute SQL, retourne stdout strip."""
    for attempt in range(4):
        res = subprocess.run([PSQL, DSN, "-At", "-c", sql],
                             capture_output=True, text=True, timeout=300)
        if res.returncode == 0:
            return res.stdout.strip()
        if "DbHandler" in res.stderr or "FATAL" in res.stderr:
            time.sleep(3); continue   # pooler retry
        raise RuntimeError(f"psql: {res.stderr[-400:]}")
    raise RuntimeError("psql: 4 retries pooler KO")

def copy_one(clean_csv, dept):
    """COPY → table temporaire, puis INSERT ON CONFLICT DO NOTHING.
    Gère les chevauchements géographiques (une annonce dans plusieurs dépts limitrophes).
    1 transaction unique, donc rollback total si fail."""
    tbl = f"staging_bienici_{dept}_{TODAY.replace('-','')}"
    sql = f"""
BEGIN;
CREATE TEMP TABLE {tbl} (LIKE public.bienici_annonces INCLUDING DEFAULTS) ON COMMIT DROP;
\\COPY {tbl} ({','.join(OUT_COLS)}) FROM '{clean_csv}' WITH (FORMAT csv, HEADER true, DELIMITER ';', NULL '')
INSERT INTO public.bienici_annonces SELECT * FROM {tbl} ON CONFLICT (id, snapshot_date) DO NOTHING;
COMMIT;
"""
    res = subprocess.run([PSQL, DSN, "-v", "ON_ERROR_STOP=1"], input=sql, capture_output=True, text=True, timeout=300)
    if res.returncode != 0:
        raise RuntimeError(f"COPY dept {dept}: {res.stderr[-400:]}")
    log(f"  copy dept {dept} ok (via staging + ON CONFLICT)")

# ─── Main ───────────────────────────────────────────────────────────────────
def main():
    report = {'date': TODAY, 'departements': {}, 'synth': {}}

    for d in DEPTS:
        rep = {'status': 'pending'}
        try:
            raw = scrape(d)
            clean, n = prepare(raw, d)
            # idempotent par-dept : on supprime SEULEMENT le snapshot du jour de CE dept,
            # et SEULEMENT après que le scrape ait réussi → un fail ne perd jamais d'historique.
            # Le préfixe insee = len(d) chars (2 pour métropole, 3 pour DOM 971-976).
            n_pref = len(d)
            log(f"  DELETE dept {d} snapshot {TODAY} (prefix {n_pref} chars)")
            psql_run(f"DELETE FROM bienici_annonces WHERE snapshot_date = '{TODAY}' AND substring(insee, 1, {n_pref}) = '{d}'")
            copy_one(clean, d)
            rep = {'status': 'ok', 'nb_inserted': n}
        except Exception as e:
            rep = {'status': 'error', 'error': str(e)[:300]}
            log(f"  ✗ dept {d}: {e}")
        report['departements'][str(d)] = rep

    # synthèse vs J-1 (toutes les annonces de tous les dépts ingérés aujourd'hui)
    log("synth diff J-1…")
    synth_sql = f"""
      WITH j0 AS (SELECT id, price, commune, title, url_annonce, photo_url
                  FROM bienici_annonces WHERE snapshot_date = '{TODAY}'),
           j1 AS (SELECT id, price FROM bienici_annonces WHERE snapshot_date = '{YESTERDAY}'),
           top_baisses AS (
             SELECT j0.id, j0.commune, j0.title, (j1.price - j0.price)::int AS delta_eur,
                    round(100.0 * (j0.price - j1.price) / nullif(j1.price,0), 1) AS delta_pct,
                    j0.url_annonce
             FROM j0 JOIN j1 USING (id)
             WHERE j0.price < j1.price ORDER BY j1.price - j0.price DESC LIMIT 5
           )
      SELECT json_build_object(
        'nb_today',     (SELECT count(*) FROM j0),
        'nb_yesterday', (SELECT count(*) FROM j1),
        'nb_nouvelles', (SELECT count(*) FROM j0 WHERE id NOT IN (SELECT id FROM j1)),
        'nb_sorties',   (SELECT count(*) FROM j1 WHERE id NOT IN (SELECT id FROM j0)),
        'nb_baisses',   (SELECT count(*) FROM j0 a JOIN j1 b USING (id) WHERE a.price < b.price),
        'nb_hausses',   (SELECT count(*) FROM j0 a JOIN j1 b USING (id) WHERE a.price > b.price),
        'top_baisses',  coalesce((SELECT json_agg(top_baisses) FROM top_baisses), '[]'::json)
      )::text
    """
    out = psql_run(synth_sql)
    report['synth'] = json.loads(out) if out else {}

    print(json.dumps(report, ensure_ascii=False, indent=2))
    # exit 0 si au moins 1 dépt OK, 1 si tous KO
    if any(r.get('status') == 'ok' for r in report['departements'].values()):
        sys.exit(0)
    sys.exit(1)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(json.dumps({'status': 'fatal', 'error': str(e), 'date': TODAY}), file=sys.stderr)
        sys.exit(2)
