# Taux de crédit immobilier France → Supabase `credit_taux`

Table : `public.credit_taux` (projet Supabase `itahwnxndgcgosjfcnwy`)
Colonnes : `date · duree · taux · type_taux · source` — clé unique `(date, duree, type_taux, source)`.
Au 21/06/2026 : **630 lignes**.

## Sources (national, mensuel — en France les taux ne dépendent pas de la ville)

| source (colonne) | Ce que c'est | Durées | Historique | MAJ |
|---|---|---|---|---|
| `banque_de_france_mir` | Banque de France via **API BCE/MIR** (gratuite, sans clé) | « taux moyen (coût du crédit) » + « fixation > 10 ans » | 2000 → en cours, **mensuel continu** | **Automatique** |
| `credit_logement_csa` | **Observatoire Crédit Logement/CSA** (référence officielle) | 15 / 20 / 25 ans + « toutes durées » | 6 dates de réf. (déc-2024 → mai-2026) | Manuelle (tableau de bord mensuel ~3ᵉ semaine) |
| `barometre_empruntis` | Baromètre courtier **Empruntis** | 7 / 10 / 15 / 20 / 25 ans, `type_taux` = moyen + meilleur | mois courant (juin-2026) | Manuelle (mensuelle) |

`type_taux` : `moyen` = taux moyen de marché ; `meilleur` = meilleur dossier.

## Réalité réglementaire (FR)
- Durée **plafonnée à 25 ans** par le HCSF → **pas de taux 30 ans** (produit quasi inexistant).
- **< 7 ans** : ce ne sont pas des durées de crédit immobilier → aucun taux publié.
- Grille réaliste complète = **7 / 10 / 15 / 20 / 25 ans**.

## Rafraîchir
```bash
~/Desktop/credit-taux/refresh.sh
```
- La partie **Banque de France** se met à jour toute seule (re-télécharge l'API).
- Pour **Crédit Logement** et **Empruntis** : éditer d'abord les dictionnaires `CL`, `EMP_MOYEN`, `EMP_MEILLEUR` en haut de `build_credit_taux.py` avec les valeurs du mois, puis lancer `refresh.sh`.
- Réinsertion **idempotente** (`ON CONFLICT … DO UPDATE`) : relancer ne crée pas de doublon.

## Fichiers
- `build_credit_taux.py` — construit + vérifie `credit_taux.csv` (contrôles : continuité des dates, monotonie de la grille, plages de valeurs).
- `insert_credit_taux.py` — insère le CSV dans Supabase (via `~/.marlo_pg_url`).
- `credit_taux.csv` — export (aussi la copie « CSV sur le Desktop » demandée).
- `tdb_mai2026.pdf/.txt` — source primaire Crédit Logement (preuve des chiffres 15/20/25).
- `mir_cost.csv`, `mir_irf10.csv` — données brutes Banque de France (API BCE).
