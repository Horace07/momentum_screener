"""
data.py — accès aux données de marché via Alpaca (plan gratuit).

Plan gratuit Alpaca (vérifié 09/2026) :
  - flux temps réel IEX uniquement, 30 symboles max en websocket
  - historique depuis 2016, les 15 dernières minutes ne sont pas accessibles
  - 200 requêtes / minute
=> parfaitement suffisant pour un screener en barres journalières lancé
   après la clôture. Ce n'est PAS suffisant pour du scalping intraday.

Clés : créez un compte sur https://alpaca.markets, générez des clés "Paper",
puis exportez-les :
    export ALPACA_API_KEY=...
    export ALPACA_SECRET_KEY=...
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timedelta

import pandas as pd


# --------------------------------------------------------------------- clients


def _clients():
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.trading.client import TradingClient

    key = os.environ.get("ALPACA_API_KEY")
    secret = os.environ.get("ALPACA_SECRET_KEY")
    if not key or not secret:
        raise RuntimeError(
            "ALPACA_API_KEY / ALPACA_SECRET_KEY absents de l'environnement."
        )
    return (
        StockHistoricalDataClient(key, secret),
        TradingClient(key, secret, paper=True),
    )


# --------------------------------------------------------------------- univers


def get_universe(max_symbols: int | None = None) -> pd.DataFrame:
    """
    Toutes les actions US négociables chez Alpaca.
    Colonnes utiles : symbol, name, exchange, tradable, shortable.
    """
    from alpaca.trading.requests import GetAssetsRequest
    from alpaca.trading.enums import AssetClass, AssetStatus

    _, trading = _clients()
    assets = trading.get_all_assets(
        GetAssetsRequest(status=AssetStatus.ACTIVE, asset_class=AssetClass.US_EQUITY)
    )
    rows = [
        {
            "symbol": a.symbol,
            "name": a.name,
            "exchange": str(a.exchange),
            "tradable": a.tradable,
            "shortable": a.shortable,
            "fractionable": a.fractionable,
        }
        for a in assets
        if a.tradable and "/" not in a.symbol and len(a.symbol) <= 5
    ]
    df = pd.DataFrame(rows)
    # On garde les places principales : écarte OTC et pink sheets
    df = df[df["exchange"].str.contains("NASDAQ|NYSE|ARCA|AMEX", case=False, na=False)]
    return df.head(max_symbols) if max_symbols else df


# --------------------------------------------------------------------- barres


def get_daily_bars(
    symbols: list[str],
    lookback_days: int = 420,
    batch_size: int = 200,
    sleep_s: float = 0.4,
) -> dict[str, pd.DataFrame]:
    """
    Barres journalières ajustées pour une liste de symboles.
    Requêtes par lots pour rester sous la limite de 200 req/min.
    """
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame

    data_client, _ = _clients()
    end = datetime.now() - timedelta(minutes=20)  # contrainte des 15 min du plan gratuit
    start = end - timedelta(days=lookback_days)

    out: dict[str, pd.DataFrame] = {}
    for i in range(0, len(symbols), batch_size):
        batch = symbols[i : i + batch_size]
        req = StockBarsRequest(
            symbol_or_symbols=batch,
            timeframe=TimeFrame.Day,
            start=start,
            end=end,
            adjustment="all",   # splits + dividendes : indispensable
            feed="iex",
        )
        try:
            bars = data_client.get_stock_bars(req).df
        except Exception as exc:  # noqa: BLE001
            print(f"  ! lot {i//batch_size}: {exc}")
            time.sleep(2)
            continue

        if bars.empty:
            continue
        for sym, g in bars.groupby(level=0):
            g = g.droplevel(0).sort_index()
            g.index = pd.to_datetime(g.index).tz_localize(None)
            out[sym] = g[["open", "high", "low", "close", "volume"]]

        print(f"  lot {i//batch_size + 1}: {len(out)} titres récupérés")
        time.sleep(sleep_s)

    return out


# --------------------------------------------------------------------- IPO


def get_recent_ipos(days: int = 365) -> pd.DataFrame:
    """
    Introductions récentes via le calendrier IPO gratuit de Finnhub.
    Clé gratuite sur https://finnhub.io -> export FINNHUB_API_KEY=...
    Sans clé, on retombe sur une détection par ancienneté de l'historique
    de prix (voir `infer_ipos_from_bars`).
    """
    import requests

    key = os.environ.get("FINNHUB_API_KEY")
    if not key:
        return pd.DataFrame(columns=["symbol", "date", "name"])

    end = datetime.now().date()
    start = end - timedelta(days=days)
    r = requests.get(
        "https://finnhub.io/api/v1/calendar/ipo",
        params={"from": start.isoformat(), "to": end.isoformat(), "token": key},
        timeout=30,
    )
    r.raise_for_status()
    rows = r.json().get("ipoCalendar", [])
    df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame(columns=["symbol", "date", "name"])
    return df[["symbol", "date", "name"]].dropna(subset=["symbol"])


def infer_ipos_from_bars(bars: dict[str, pd.DataFrame], days: int = 365) -> set[str]:
    """
    Repli sans clé API : un titre dont la première barre disponible est
    récente est vraisemblablement une cotation récente.
    Attention : faux positifs (changement de ticker, re-listing).
    """
    cutoff = pd.Timestamp.now().normalize() - pd.Timedelta(days=days)
    return {s for s, df in bars.items() if not df.empty and df.index[0] > cutoff}
