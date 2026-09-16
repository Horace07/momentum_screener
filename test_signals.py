"""
test_signals.py — vérifie la logique sans réseau, avec des barres synthétiques.
Lancez : python test_signals.py
"""
import numpy as np
import pandas as pd

from config import Config
import signals as sig


def make_bars(n=400, drift=0.0008, vol=0.02, seed=0, vol_mult_end=1.0):
    rng = np.random.default_rng(seed)
    ret = rng.normal(drift, vol, n)
    close = 50 * np.exp(np.cumsum(ret))
    high = close * (1 + rng.uniform(0, 0.015, n))
    low = close * (1 - rng.uniform(0, 0.015, n))
    volume = rng.integers(500_000, 1_500_000, n).astype(float)
    volume[-5:] *= vol_mult_end
    idx = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=n)
    return pd.DataFrame(
        {"open": close, "high": high, "low": low, "close": close, "volume": volume},
        index=idx,
    )


def main():
    cfg = Config()

    strong = make_bars(drift=0.0025, vol=0.018, seed=1, vol_mult_end=3.0)  # tendance forte
    weak = make_bars(drift=-0.0015, vol=0.018, seed=2)                     # baissier
    bench = make_bars(drift=0.0004, vol=0.009, seed=3)                     # SPY
    ipo = make_bars(n=90, drift=0.004, vol=0.03, seed=4)                   # IPO récente

    fs = sig.compute_features(strong, bench["close"])
    fw = sig.compute_features(weak, bench["close"])
    fi = sig.compute_features(ipo, bench["close"])

    print("--- features titre haussier ---")
    for k, v in fs.items():
        print(f"  {k:16} {v}")

    assert fs["ret_3m"] > fw["ret_3m"], "le haussier doit battre le baissier"
    assert fs["rs_3m"] > 0, "force relative positive attendue"
    assert fs["above_ma50"] and fs["above_ma200"], "doit être au-dessus des MM"
    assert fs["vol_surge"] > 1.5, f"pic de volume attendu, obtenu {fs['vol_surge']}"
    assert -0.30 < fs["dist_52w_high"] <= 0, "distance au plus haut incohérente"

    ok_s, _ = sig.passes_hard_filters(fs, cfg)
    ok_w, why_w = sig.passes_hard_filters(fw, cfg)
    ok_i, why_i = sig.passes_hard_filters(fi, cfg)
    print(f"\nfiltres : haussier={ok_s}  baissier={ok_w} ({why_w})  ipo={ok_i} ({why_i})")
    assert ok_s, "le haussier doit passer les filtres"
    assert not ok_w, "le baissier doit être rejeté"

    # IPO : 90 barres > min_bars(60) mais ret_6m/12m sont NaN -> ne doit pas crasher
    assert np.isnan(fi["ret_6m"]) and np.isnan(fi["ret_12m"])

    # --- scoring transversal sur un univers factice ---
    rows = []
    for i in range(40):
        b = make_bars(drift=0.0030 - i * 0.00015, vol=0.02, seed=100 + i,
                      vol_mult_end=1 + (i % 4))
        f = sig.compute_features(b, bench["close"])
        if sig.passes_hard_filters(f, cfg)[0]:
            rows.append({"symbol": f"T{i:02d}",
                         "theme_bonus": cfg.bonus_theme if i in (5, 6) else 0.0, **f})
    uni = pd.DataFrame(rows).set_index("symbol")
    ranked = sig.score_universe(uni, cfg)
    print(f"\n{len(ranked)} titres scorés ; top 5 :")
    print(ranked[["score", "ret_3m", "rs_3m", "vol_surge"]].head().round(3).to_string())

    assert ranked["score"].is_monotonic_decreasing, "le tri doit être décroissant"
    assert ranked["score"].notna().all(), "aucun score ne doit être NaN"

    # --- dimensionnement ---
    ps = sig.position_size(10_000, 50.0, 0.03, cfg)
    print(f"\nsizing (capital 10 000 €, prix 50 $, ATR 3 %) : {ps}")
    assert ps["shares"] > 0
    assert ps["notional"] <= 10_000 * cfg.max_weight + 50, "plafond de poids non respecté"
    assert abs(ps["risk_eur"] - 10_000 * cfg.risk_per_trade) < 50, "risque hors budget"

    # ATR manquant -> pas de position, pas de crash
    assert sig.position_size(10_000, 50.0, float("nan"), cfg)["shares"] == 0

    print("\n✅ tous les tests passent")


if __name__ == "__main__":
    main()
