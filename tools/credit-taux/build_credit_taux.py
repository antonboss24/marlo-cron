#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Construit credit_taux.csv depuis 3 sources reelles (zero valeur inventee).
Schema : date, duree, taux, type_taux ('moyen'|'meilleur'), source.
  1) Banque de France via API BCE/MIR  -> serie mensuelle continue (mir_cost.csv, mir_irf10.csv)
  2) Observatoire Credit Logement/CSA  -> grille officielle 15/20/25 (TDB mai 2026, source primaire)
  3) Barometre courtier Empruntis      -> grille pratique 7..25 (moyen + meilleur), juin 2026
Verifie : continuite des dates, plages de valeurs, trous, monotonie de la grille.
"""
import csv
from collections import defaultdict

rows = []  # (date, duree, taux, type_taux, source)

# ---------- 1) Banque de France / MIR (CSV de l'API BCE, mensuel continu) ----------
def load_mir(path, duree_label):
    out = []
    with open(path, newline='', encoding='utf-8') as f:
        r = csv.reader(f); header = next(r)
        ti, vi = header.index('TIME_PERIOD'), header.index('OBS_VALUE')
        for line in r:
            if len(line) <= vi: continue
            period, val = line[ti].strip(), line[vi].strip()
            if not period or not val: continue
            out.append((period + '-01', duree_label, float(val), 'moyen', 'banque_de_france_mir'))
    return out

bdf_cost  = load_mir('mir_cost.csv',  'taux moyen (cout du credit)')
bdf_irf10 = load_mir('mir_irf10.csv', 'fixation > 10 ans')
rows += bdf_cost + bdf_irf10

# ---------- 2) Credit Logement / CSA (TDB mensuel mai 2026, source primaire) ----------
CL = {  # date : (toutes durees, 15 ans, 20 ans, 25 ans)
    '2024-12-01': (3.31, 3.24, 3.26, 3.34),
    '2025-05-01': (3.09, 3.05, 3.09, 3.17),
    '2025-12-01': (3.16, 3.09, 3.17, 3.25),
    '2026-03-01': (3.22, 3.04, 3.21, 3.27),
    '2026-04-01': (3.23, 3.06, 3.27, 3.31),
    '2026-05-01': (3.25, 3.12, 3.34, 3.37),
}
for d, (moy, q15, q20, q25) in CL.items():
    rows.append((d, 'toutes durees', moy, 'moyen', 'credit_logement_csa'))
    rows.append((d, '15 ans', q15, 'moyen', 'credit_logement_csa'))
    rows.append((d, '20 ans', q20, 'moyen', 'credit_logement_csa'))
    rows.append((d, '25 ans', q25, 'moyen', 'credit_logement_csa'))

# ---------- 3) Barometre Empruntis (grille pratique 7..25, juin 2026, maj 21/06/2026) ----------
# France : duree plafonnee a 25 ans (HCSF) -> pas de 30 ans publie.
EMP_MOYEN    = {'7 ans': 3.20, '10 ans': 3.25, '15 ans': 3.35, '20 ans': 3.45, '25 ans': 3.55}
EMP_MEILLEUR = {'7 ans': 2.70, '10 ans': 2.70, '15 ans': 2.85, '20 ans': 3.00, '25 ans': 3.20}
for duree, taux in EMP_MOYEN.items():
    rows.append(('2026-06-01', duree, taux, 'moyen', 'barometre_empruntis'))
for duree, taux in EMP_MEILLEUR.items():
    rows.append(('2026-06-01', duree, taux, 'meilleur', 'barometre_empruntis'))

# ---------- Ecriture CSV ----------
rows.sort(key=lambda x: (x[4], x[3], x[1], x[0]))
with open('credit_taux.csv', 'w', newline='', encoding='utf-8') as f:
    w = csv.writer(f); w.writerow(['date', 'duree', 'taux', 'type_taux', 'source'])
    w.writerows(rows)

# ====================== VERIFICATION ======================
def months_between(a, b):
    return (int(b[:4]) - int(a[:4])) * 12 + (int(b[5:7]) - int(a[5:7]))

print(f"=== RESUME ===\nTotal lignes : {len(rows)}\n")
print("=== PAR SERIE (source | type | duree) : n, plage, min-max, continuite ===")
ser = defaultdict(list)
for d, duree, taux, typ, src in rows:
    ser[(src, typ, duree)].append((d, taux))
for (src, typ, duree), pts in sorted(ser.items()):
    pts.sort(); dates = [p[0] for p in pts]; tx = [p[1] for p in pts]
    gaps = [f"{dates[i-1]}->{dates[i]}" for i in range(1, len(dates)) if months_between(dates[i-1], dates[i]) != 1] if src == 'banque_de_france_mir' else []
    flag = "CONTINU OK" if (src == 'banque_de_france_mir' and not gaps) else ("TROUS:%s" % gaps if gaps else "ponctuel")
    print(f"  [{src:<20}|{typ:<8}|{duree:<27}] n={len(pts):>3}  {dates[0]}->{dates[-1]}  {min(tx):.2f}-{max(tx):.2f}%  {flag}")

print("\n=== COHERENCE ===")
g = [EMP_MOYEN[k] for k in ['7 ans','10 ans','15 ans','20 ans','25 ans']]
b = [EMP_MEILLEUR[k] for k in ['7 ans','10 ans','15 ans','20 ans','25 ans']]
print(f"  Grille MOYEN    juin26 : 7={g[0]} 10={g[1]} 15={g[2]} 20={g[3]} 25={g[4]}  (croissant->{'OK' if all(g[i]<=g[i+1] for i in range(4)) else 'KO'})")
print(f"  Grille MEILLEUR juin26 : 7={b[0]} 10={b[1]} 15={b[2]} 20={b[3]} 25={b[4]}  (croissant->{'OK' if all(b[i]<=b[i+1] for i in range(4)) else 'KO'})")
print(f"  meilleur < moyen partout -> {'OK' if all(b[i]<=g[i] for i in range(5)) else 'KO'}")
print(f"  Credit Logement mai26 : 15={CL['2026-05-01'][1]} 20={CL['2026-05-01'][2]} 25={CL['2026-05-01'][3]}  (20 ans 3-4% -> {'OK' if 3<=CL['2026-05-01'][2]<=4 else 'KO'})")
allv = [r[2] for r in rows]
print(f"  Plage globale : {min(allv):.2f}-{max(allv):.2f}%  ({'plausible' if 0<min(allv) and max(allv)<7 else 'A VERIFIER'})")

print("\n=== APERCU grille pratique Empruntis (ce que tu as demande) ===")
for typ in ('moyen', 'meilleur'):
    line = "  %-9s : " % typ + "  ".join(f"{k}={v}%" for k, v in (EMP_MOYEN if typ=='moyen' else EMP_MEILLEUR).items())
    print(line)
