"""
data.py — Moteur d'ingestion robuste vers Alpaca Markets (Plan gratuit).
"""
from __future__ import annotations

import os
import time
import logging
from datetime import datetime, timedelta
import pandas as pd
from dotenv import load_dotenv

# Initialisation du logger et des variables d'environnement locales
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
load_dotenv()


# --------------------------------------------------------------------- clients

def _clients():
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.trading.client import TradingClient

    key = os.environ.get("ALPACA_API_KEY")
    secret = os.environ.get("ALPACA_SECRET_KEY")
    
    if not key or not secret:
        raise RuntimeError("CRITIQUE : ALPACA_API_KEY ou ALPACA_SECRET_KEY absents. Vérifiez votre fichier .env.")
    
    return (
        StockHistoricalDataClient(key, secret),
        TradingClient(key, secret, paper=True),
    )


# --------------------------------------------------------------------- univers

def get_universe(max_symbols: int | None = None) -> pd.DataFrame:
    """
    Récupère toutes les actions US négociables (NASDAQ, NYSE, ARCA).
    Exclut l'OTC, les pink sheets et les tickers complexes.
    """
    from alpaca.trading.requests import GetAssetsRequest
    from alpaca.trading.enums import AssetClass, AssetStatus

    _, trading = _clients()
    logging.info("Récupération de l'univers des actifs...")
    
    req = GetAssetsRequest(status=AssetStatus.ACTIVE, asset_class=AssetClass.US_EQUITY)
    assets = trading.get_all_assets(req)
    
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
    
    # On garde les places principales uniquement
    df = df[df["exchange"].str.contains("NASDAQ|NYSE|ARCA|AMEX", case=False, na=False)]
    
    logging.info(f"Univers filtré : {len(df)} actifs trouvés.")
    return df.head(max_symbols) if max_symbols else df


# --------------------------------------------------------------------- barres

def get_daily_bars(
    symbols: list[str],
    lookback_days: int = 420,
    batch_size: int = 200,
    sleep_s: float = 0.5,
) -> dict[str, pd.DataFrame]:
    """
    Barres journalières ajustées avec protection Exponential Backoff 
    contre le Rate Limiting (200 req/min).
    """
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame

    data_client, _ = _clients()
    
    # Contrainte plan gratuit : on recule de 20 min pour éviter le rejet Live Data
    end = datetime.utcnow() - timedelta(minutes=20)
    start = end - timedelta(days=lookback_days)

    out: dict[str, pd.DataFrame] = {}
    
    for i in range(0, len(symbols), batch_size):
        batch = symbols[i : i + batch_size]
        req = StockBarsRequest(
            symbol_or_symbols=batch,
            timeframe=TimeFrame.Day,
            start=start,
            end=end,
            adjustment="all",   # Indispensable : ajuste pour splits/dividendes
            feed="iex",
        )
        
        # SÉCURITÉ D'EXÉCUTION : Mécanisme de Retry
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = data_client.get_stock_bars(req)
                
                # Alpaca retourne un dictionnaire de DataFrames via la propriété df
                if response.data:
                    bars = response.df
                    for sym, g in bars.groupby(level=0):
                        g = g.droplevel(0).sort_index()
                        g.index = pd.to_datetime(g.index).tz_localize(None)
                        out[sym] = g[["open", "high", "low", "close", "volume"]]
                
                logging.info(f"Lot {i//batch_size + 1} OK : {len(out)} titres cumulés en mémoire.")
                time.sleep(sleep_s)
                break  # Succès, on sort de la boucle de retry
                
            except Exception as exc:
                logging.warning(f"Rejet API sur lot {i//batch_size + 1} (Tentative {attempt+1}/{max_retries}): {exc}")
                time.sleep(5 * (attempt + 1))  # Exponential backoff (5s, 10s, 15s)
                if attempt == max_retries - 1:
                    logging.error(f"ABANDON : Lot {i//batch_size + 1} définitivement ignoré après {max_retries} échecs.")

    return out


# --------------------------------------------------------------------- IPO
# Conservés pour usage ultérieur sans modification majeure

def get_recent_ipos(days: int = 365) -> pd.DataFrame:
    import requests
    key = os.environ.get("FINNHUB_API_KEY")
    if not key:
        logging.info("Clé Finnhub absente. Module IPO via API désactivé.")
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
    cutoff = pd.Timestamp.now().normalize() - pd.Timedelta(days=days)
    return {s for s, df in bars.items() if not df.empty and df.index[0] > cutoff}


# --------------------------------------------------------------------- TEST LOCAL
if __name__ == "__main__":
    # Test d'isolation : on vérifie que le moteur fonctionne avec un petit lot (50 actions)
    print("--- Démarrage du test d'ingestion Data ---")
    df_univ = get_universe(max_symbols=50)
    
    if not df_univ.empty:
        symbols_to_fetch = df_univ["symbol"].tolist()
        bars_dict = get_daily_bars(symbols_to_fetch, lookback_days=10) # 10 jours pour tester vite
        print(f"\nTest terminé avec succès. Données récupérées pour {len(bars_dict)} actions.")
    else:
        print("Erreur : Impossible de récupérer l'univers.")