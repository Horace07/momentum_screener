"""
config.py — tous les paramètres au même endroit.

Règle : aucun nombre magique ailleurs dans le code. Un backtest = un jeu de
paramètres, et vous devez pouvoir en changer sans toucher à la logique.
"""

from dataclasses import dataclass, field


@dataclass
class Config:
    # ---- univers -------------------------------------------------------
    min_price: float = 5.0            # écarte les penny stocks (manipulables)
    min_dollar_vol: float = 5_000_000  # $ échangés / jour en moyenne sur 20j
    min_bars: int = 60                 # historique minimum (une IPO de 3 mois passe)
    max_atr_pct: float = 0.12          # au-delà, le titre est intradable en swing
    max_dist_high: float = 0.25        # rejet si > 25 % sous le plus haut 52 sem.

    # ---- pondérations du score (somme des |w| normalisée) ---------------
    w_ret_1m: float = 0.20
    w_ret_3m: float = 0.30
    w_ret_6m: float = 0.15
    w_rs_3m: float = 0.20              # surperformance vs SPY
    w_dist_high: float = 0.10          # proche du plus haut = mieux
    w_vol_surge: float = 0.05

    # ---- bonus thématiques ---------------------------------------------
    bonus_theme: float = 0.30          # secteur porteur (défense, quantique…)
    bonus_recent_ipo: float = 0.20     # cotation < ipo_window_days
    ipo_window_days: int = 365

    # ---- risque ---------------------------------------------------------
    risk_per_trade: float = 0.005      # 0,5 % du capital risqué par position
    atr_stop_mult: float = 2.5         # stop = 2,5 x ATR sous l'entrée
    max_weight: float = 0.08           # 8 % max du capital sur une ligne
    max_positions: int = 12

    # ---- sortie ----------------------------------------------------------
    top_n: int = 25
    benchmark: str = "SPY"


# ---------------------------------------------------------------------------
# Listes thématiques. À maintenir à la main : c'est le seul endroit où votre
# conviction "secteur porteur" entre dans l'algo, et c'est mieux ainsi —
# un classifieur automatique de secteur est bruité et non auditable.
# ---------------------------------------------------------------------------

THEMES: dict[str, list[str]] = {
    "defense": [
        "LMT", "RTX", "NOC", "GD", "LHX", "HII", "LDOS", "BA", "TXT", "KTOS",
        "AVAV", "RKLB", "PLTR", "DRS", "CW", "MOG-A", "HEI", "TDG", "AXON",
    ],
    "quantum": [
        "IONQ", "RGTI", "QBTS", "QUBT", "ARQQ", "IBM", "HON", "NVDA",
    ],
    "space": [
        "RKLB", "ASTS", "LUNR", "RDW", "PL", "SPCE",
    ],
    "ai_infra": [
        "NVDA", "AMD", "AVGO", "VRT", "SMCI", "CRDO", "ALAB", "MRVL", "ANET",
    ],
}


def theme_of(symbol: str) -> str | None:
    for name, syms in THEMES.items():
        if symbol in syms:
            return name
    return None
