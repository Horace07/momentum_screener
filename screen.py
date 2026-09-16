#!/usr/bin/env python3
"""
screen.py — point d'entrée du screener.

Usage :
    export ALPACA_API_KEY=...  ALPACA_SECRET_KEY=...
    python screen.py                 # univers complet (~5000 titres, ~5 min)
    python screen.py --themes-only   # uniquement les listes thématiques (rapide)
    python screen.py --equity 20000  # dimensionne les positions pour 20 000 €

Sortie : candidats.csv + affichage console.
CE SCRIPT NE PASSE AUCUN ORDRE. Il propose, vous décidez.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime

import pandas as pd

from config import Config, THEMES, theme_of
import data as dta
import signals as sig


def build_candidates(
    bars: dict[str, pd.DataFrame],
    cfg: Config,
    ipo_symbols: set[str],
) -> pd.DataFrame:
    bench = bars.get(cfg.benchmark)
    bench_close = bench["close"] if bench is not None else None

    rows, rejets = [], {}
    for symbol, df in bars.items():
        if symbol == cfg.benchmark or df.empty:
            continue
        f = sig.compute_features(df, bench_close)
        ok, why = sig.passes_hard_filters(f, cfg)
        if not ok:
            rejets[why] = rejets.get(why, 0) + 1
            continue

        theme = theme_of(symbol)
        bonus = 0.0
        if theme:
            bonus += cfg.bonus_theme
        if symbol in ipo_symbols:
            bonus += cfg.bonus_recent_ipo

        rows.append({"symbol": symbol, "theme": theme or "", "is_ipo": symbol in ipo_symbols,
                     "theme_bonus": bonus, **f})

    print(f"\nRejets : {dict(sorted(rejets.items(), key=lambda x: -x[1]))}")
    if not rows:
        return pd.DataFrame()

    out = pd.DataFrame(rows).set_index("symbol")
    return sig.score_universe(out, cfg)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--themes-only", action="store_true",
                   help="ne scanner que les listes thématiques de config.py")
    p.add_argument("--equity", type=float, default=10_000.0,
                   help="capital total, pour le dimensionnement des positions")
    p.add_argument("--top", type=int, default=None)
    p.add_argument("--out", default="candidats.csv")
    args = p.parse_args()

    cfg = Config()
    if args.top:
        cfg.top_n = args.top

    # 1. univers
    if args.themes_only:
        symbols = sorted({s for lst in THEMES.values() for s in lst})
        print(f"Univers thématique : {len(symbols)} titres")
    else:
        print("Récupération de l'univers Alpaca…")
        uni = dta.get_universe()
        symbols = uni["symbol"].tolist()
        print(f"Univers : {len(symbols)} titres négociables")

    if cfg.benchmark not in symbols:
        symbols.append(cfg.benchmark)

    # 2. données
    print("Téléchargement des barres journalières…")
    bars = dta.get_daily_bars(symbols)
    print(f"{len(bars)} historiques récupérés")

    # 3. IPO récentes
    ipos = dta.get_recent_ipos(cfg.ipo_window_days)
    ipo_symbols = set(ipos["symbol"]) if not ipos.empty else set()
    ipo_symbols |= dta.infer_ipos_from_bars(bars, cfg.ipo_window_days)
    print(f"{len(ipo_symbols)} cotations récentes identifiées")

    # 4. scoring
    ranked = build_candidates(bars, cfg, ipo_symbols)
    if ranked.empty:
        print("Aucun candidat ne passe les filtres aujourd'hui. C'est un résultat valide.")
        return 0

    top = ranked.head(cfg.top_n).copy()

    # 5. dimensionnement
    sizing = [sig.position_size(args.equity, r["last_close"], r["atr_pct"], cfg)
              for _, r in top.iterrows()]
    top["shares"] = [s["shares"] for s in sizing]
    top["stop"] = [s["stop"] for s in sizing]
    top["notional"] = [s.get("notional") for s in sizing]

    cols = ["theme", "is_ipo", "score", "last_close", "ret_1m", "ret_3m", "rs_3m",
            "dist_52w_high", "vol_surge", "atr_pct", "shares", "stop", "notional"]
    view = top[cols].round(3)

    print(f"\n=== TOP {len(view)} — {datetime.now():%Y-%m-%d %H:%M} ===")
    print(view.to_string())

    top.to_csv(args.out)
    print(f"\nÉcrit dans {args.out}")
    print("Rappel : ceci est une liste de candidats à examiner, pas une recommandation.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
