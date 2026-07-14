#!/usr/bin/env bash
# Rafraichit la table public.credit_taux.
# BdF/MIR = automatique. Credit Logement + Empruntis = a mettre a jour A LA MAIN
# dans build_credit_taux.py (dicts CL / EMP_MOYEN / EMP_MEILLEUR) avec les valeurs du mois.
set -euo pipefail
cd "$(dirname "$0")"
echo "1/3 Telechargement Banque de France (API BCE/MIR)..."
curl -s --max-time 40 -H "Accept: text/csv" "https://data-api.ecb.europa.eu/service/data/MIR/M.FR.B.A2C.AM.R.A.2250.EUR.N?format=csvdata" -o mir_cost.csv
curl -s --max-time 40 -H "Accept: text/csv" "https://data-api.ecb.europa.eu/service/data/MIR/M.FR.B.A2C.P.R.A.2250.EUR.N?format=csvdata"  -o mir_irf10.csv
echo "2/3 Reconstruction + verification du CSV..."
python3 build_credit_taux.py
echo "3/3 Insertion (idempotente) dans Supabase..."
uv run --with "psycopg[binary]" python3 insert_credit_taux.py
