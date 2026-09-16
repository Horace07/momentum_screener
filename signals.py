"""
signals.py — calcul des indicateurs et du score composite.

Pure pandas : aucune dépendance réseau, donc testable hors ligne.
Entrée : un DataFrame de barres journalières par ticker
         (index = date, colonnes = open/high/low/close/volume)
Sortie : un dict de features + un score.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# ---------------------------------------------------------------- indicateurs


def pct_return(close: pd.Series, lookback: int) -> float:
    """Rendement simple sur `lookback` séances."""
    if len(close) <= lookback:
        return np.nan
    return float(close.iloc[-1] / close.iloc[-1 - lookback] - 1.0)


def dist_to_high(close: pd.Series, window: int = 252) -> float:
    """Distance au plus haut des `window` dernières séances (0 = sur le plus haut)."""
    w = close.iloc[-window:]
    if w.empty:
        return np.nan
    return float(w.iloc[-1] / w.max() - 1.0)


def volume_surge(volume: pd.Series, fast: int = 5, slow: int = 60) -> float:
    """Ratio volume moyen court terme / long terme. > 1.5 = afflux d'acheteurs."""
    if len(volume) < slow:
        return np.nan
    return float(volume.iloc[-fast:].mean() / volume.iloc[-slow:].mean())


def atr_pct(df: pd.DataFrame, window: int = 14) -> float:
    """ATR en % du prix — sert au dimensionnement de position, pas au signal."""
    if len(df) < window + 1:
        return np.nan
    prev_close = df["close"].shift(1)
    tr = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return float(tr.rolling(window).mean().iloc[-1] / df["close"].iloc[-1])


def above_ma(close: pd.Series, window: int) -> bool:
    if len(close) < window:
        return False
    return bool(close.iloc[-1] > close.rolling(window).mean().iloc[-1])


def dollar_volume(df: pd.DataFrame, window: int = 20) -> float:
    """Liquidité moyenne en $ / jour. Filtre anti-illiquidité indispensable."""
    if len(df) < window:
        return np.nan
    return float((df["close"] * df["volume"]).iloc[-window:].mean())


def max_drawdown(close: pd.Series, window: int = 252) -> float:
    w = close.iloc[-window:]
    if w.empty:
        return np.nan
    return float((w / w.cummax() - 1.0).min())


# ---------------------------------------------------------------- extraction


def compute_features(df: pd.DataFrame, bench_close: pd.Series | None = None) -> dict:
    """Calcule toutes les features d'un titre. `df` doit être trié par date."""
    close = df["close"]
    feats = {
        "last_close": float(close.iloc[-1]),
        "n_bars": int(len(df)),
        "ret_1m": pct_return(close, 21),
        "ret_3m": pct_return(close, 63),
        "ret_6m": pct_return(close, 126),
        "ret_12m": pct_return(close, 252),
        "dist_52w_high": dist_to_high(close, 252),
        "vol_surge": volume_surge(df["volume"]),
        "atr_pct": atr_pct(df),
        "above_ma50": above_ma(close, 50),
        "above_ma200": above_ma(close, 200),
        "dollar_vol_20d": dollar_volume(df),
        "max_dd_12m": max_drawdown(close, 252),
    }

    # Force relative vs indice de référence (SPY) sur 3 mois
    if bench_close is not None and len(bench_close) > 63:
        bench_ret = pct_return(bench_close, 63)
        feats["rs_3m"] = (
            feats["ret_3m"] - bench_ret if not np.isnan(feats["ret_3m"]) else np.nan
        )
    else:
        feats["rs_3m"] = np.nan

    return feats


# ---------------------------------------------------------------- filtres


def passes_hard_filters(f: dict, cfg) -> tuple[bool, str]:
    """Filtres éliminatoires. Retourne (ok, raison_du_rejet)."""
    if f["n_bars"] < cfg.min_bars:
        return False, "historique insuffisant"
    if f["last_close"] < cfg.min_price:
        return False, f"prix < {cfg.min_price}$"
    if not np.isnan(f["dollar_vol_20d"]) and f["dollar_vol_20d"] < cfg.min_dollar_vol:
        return False, "illiquide"
    if not f["above_ma50"]:
        return False, "sous la MM50"
    if not np.isnan(f["atr_pct"]) and f["atr_pct"] > cfg.max_atr_pct:
        return False, "volatilité excessive"
    if not np.isnan(f["dist_52w_high"]) and f["dist_52w_high"] < -cfg.max_dist_high:
        return False, "trop loin du plus haut 52s"
    return True, ""


# ---------------------------------------------------------------- score


def zscore(s: pd.Series) -> pd.Series:
    """Z-score robuste : winsorisé pour ne pas laisser un outlier écraser le reste."""
    s = s.astype(float)
    lo, hi = s.quantile(0.02), s.quantile(0.98)
    s = s.clip(lo, hi)
    sd = s.std()
    if sd == 0 or np.isnan(sd):
        return pd.Series(0.0, index=s.index)
    return (s - s.mean()) / sd


def score_universe(df: pd.DataFrame, cfg) -> pd.DataFrame:
    """
    Score composite calculé EN COUPE TRANSVERSALE (chaque titre comparé aux autres
    du jour), ce qui évite d'avoir à calibrer des seuils absolus arbitraires.
    """
    out = df.copy()
    components = {
        "ret_1m": cfg.w_ret_1m,
        "ret_3m": cfg.w_ret_3m,
        "ret_6m": cfg.w_ret_6m,
        "rs_3m": cfg.w_rs_3m,
        "dist_52w_high": cfg.w_dist_high,  # proche de 0 = mieux, donc plus est haut mieux c'est
        "vol_surge": cfg.w_vol_surge,
    }
    score = pd.Series(0.0, index=out.index)
    total_w = 0.0
    for col, w in components.items():
        if col not in out.columns:
            continue
        z = zscore(out[col].fillna(out[col].median()))
        out[f"z_{col}"] = z
        score += w * z
        total_w += abs(w)

    out["score"] = score / total_w if total_w else score

    # Bonus thématique : secteur porteur, IPO récente
    out["score"] = out["score"] + out.get("theme_bonus", 0.0)

    return out.sort_values("score", ascending=False)


# ---------------------------------------------------------------- risque


def position_size(equity: float, price: float, atr_pct_val: float, cfg) -> dict:
    """
    Dimensionnement par le risque : on ne mise jamais un % fixe du capital,
    on risque un % fixe du capital jusqu'au stop.
    Stop = k * ATR sous le prix d'entrée.
    """
    if np.isnan(atr_pct_val) or atr_pct_val <= 0:
        return {"shares": 0, "stop": np.nan, "reason": "ATR indisponible"}

    stop_dist_pct = cfg.atr_stop_mult * atr_pct_val
    risk_per_share = price * stop_dist_pct
    risk_budget = equity * cfg.risk_per_trade
    shares = int(risk_budget // risk_per_share)

    # plafond d'exposition par ligne
    max_shares_by_weight = int((equity * cfg.max_weight) // price)
    shares = min(shares, max_shares_by_weight)

    return {
        "shares": max(shares, 0),
        "stop": round(price * (1 - stop_dist_pct), 2),
        "notional": round(shares * price, 2),
        "risk_eur": round(shares * risk_per_share, 2),
    }
