#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Insere credit_taux.csv dans Supabase (table public.credit_taux), idempotent."""
import csv, pathlib, psycopg

url = pathlib.Path.home().joinpath('.marlo_pg_url').read_text().strip()

with open('credit_taux.csv', newline='', encoding='utf-8') as f:
    r = csv.DictReader(f)
    data = [(row['date'], row['duree'], float(row['taux']), row['type_taux'], row['source']) for row in r]

print(f"Lignes a inserer : {len(data)}")
SQL = """insert into public.credit_taux (date, duree, taux, type_taux, source)
values (%s,%s,%s,%s,%s)
on conflict (date, duree, type_taux, source) do update set taux = excluded.taux"""

with psycopg.connect(url, connect_timeout=20) as conn:
    with conn.cursor() as cur:
        cur.executemany(SQL, data)
        conn.commit()
        cur.execute("select count(*), min(date), max(date) from public.credit_taux")
        print("Apres insert -> count, min(date), max(date) =", cur.fetchone())
print("OK insert termine.")
