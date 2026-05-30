# marlo-cron · Bien'ici daily ingest

Routine quotidienne : scrape Bien'ici (depts dans `DEPTS`) → COPY vers Supabase `bienici_annonces` → récap synth vs J-1.

- `bienici_departement.py` — scraper API publique Bien'ici (Anton)
- `bienici_daily.py` — orchestrateur (scrape + prep + COPY + récap JSON)
- `.github/workflows/daily.yml` — cron quotidien 06:00 Paris

Secret requis : `MARLO_PG_URL` (DSN pooler Supabase).

Override : `DEPTS` (env var, default `49,44`) pour étendre à plus de départements.
