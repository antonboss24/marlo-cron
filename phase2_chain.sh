#!/bin/bash
# Chaîne complète : phase 1 (en cours) → phase 2 (arr) → phase 3b (re-scrape complet parallèle 5×)
# Phase 3a (villes denses isolées) est skippée car englobée dans 3b qui re-scrape tout avec les fixes.

LOG=/tmp/phases.log
echo "[$(date)] === Phase 2 — attente fin phase 1 ===" >> "$LOG"
while pgrep -f "bienici_daily.py" > /dev/null; do
  sleep 30
done

echo "[$(date)] === Phase 2 — arrondissements Paris/Lyon/Marseille ===" >> "$LOG"
DEPTS='75,69,13' python3 /Users/antontriou/Desktop/marlo-routines/bienici_daily.py >> "$LOG" 2>&1

echo "[$(date)] === Phase 3b — re-scrape COMPLET 101 dépts en 5 process parallèles ===" >> "$LOG"
echo "[$(date)] Code chargé : 5 slices d'origine + INSEE strict + arrondissements + binary split adaptatif" >> "$LOG"

DEPTS='01,02,03,04,05,06,07,08,09,10,11,12,13,14,15,16,17,18,19,2A' \
  BIENICI_OUT_DIR=/tmp/p3b_1 \
  python3 /Users/antontriou/Desktop/marlo-routines/bienici_daily.py >> /tmp/p3b_1.log 2>&1 &
PID1=$!

DEPTS='2B,21,22,23,24,25,26,27,28,29,30,31,32,33,34,35,36,37,38,39' \
  BIENICI_OUT_DIR=/tmp/p3b_2 \
  python3 /Users/antontriou/Desktop/marlo-routines/bienici_daily.py >> /tmp/p3b_2.log 2>&1 &
PID2=$!

DEPTS='40,41,42,43,44,45,46,47,48,49,50,51,52,53,54,55,56,57,58,59' \
  BIENICI_OUT_DIR=/tmp/p3b_3 \
  python3 /Users/antontriou/Desktop/marlo-routines/bienici_daily.py >> /tmp/p3b_3.log 2>&1 &
PID3=$!

DEPTS='60,61,62,63,64,65,66,67,68,70,71,72,73,74,76,77,78,79' \
  BIENICI_OUT_DIR=/tmp/p3b_4 \
  python3 /Users/antontriou/Desktop/marlo-routines/bienici_daily.py >> /tmp/p3b_4.log 2>&1 &
PID4=$!

DEPTS='80,81,82,83,84,85,86,87,88,89,90,91,92,93,94,95,971,972,973,974,976' \
  BIENICI_OUT_DIR=/tmp/p3b_5 \
  python3 /Users/antontriou/Desktop/marlo-routines/bienici_daily.py >> /tmp/p3b_5.log 2>&1 &
PID5=$!

echo "[$(date)] 5 process parallèles lancés : PIDs $PID1 $PID2 $PID3 $PID4 $PID5" >> "$LOG"
wait $PID1 $PID2 $PID3 $PID4 $PID5

echo "[$(date)] === PHASE 3b TERMINÉE. EXHAUSTIVITÉ ATTEINTE. ===" >> "$LOG"
echo "[$(date)] === Reste : Claude Code Routine cron 04:00 pour les jours suivants ===" >> "$LOG"
