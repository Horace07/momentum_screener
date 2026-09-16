"""
screen.py — Moteur de scoring et de classement Momentum.
"""
import logging
import pandas as pd
import numpy as np
from config import Config

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
cfg = Config()

def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Calcul vectorisé de l'Average True Range (ATR) pour la gestion du risque."""
    high = df['high']
    low = df['low']
    close_prev = df['close'].shift(1)
    
    tr1 = high - low
    tr2 = (high - close_prev).abs()
    tr3 = (low - close_prev).abs()
    
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(window=period).mean()

def score_asset(symbol: str, df: pd.DataFrame) -> dict | None:
    """
    Extrait les métriques mathématiques d'un DataFrame OHLCV et génère un score.
    Retourne None si l'actif est jugé trop risqué ou invalide.
    """
    # Filtre 1 : Historique minimum (63 jours = 3 mois de bourse)
    if len(df) < 63:
        return None

    current_price = df['close'].iloc[-1]
    
    # Sécurité absolue : Éviter les divisions par zéro sur des actions illiquides
    if current_price <= 0:
        return None

    price_1m_ago = df['close'].iloc[-21]
    price_3m_ago = df['close'].iloc[-63]

    # Calcul des rendements directionnels
    ret_1m = (current_price - price_1m_ago) / price_1m_ago
    ret_3m = (current_price - price_3m_ago) / price_3m_ago

    # Calcul du volume anormal (Surge) - 5 jours vs 63 jours
    vol_recent = df['volume'].tail(5).mean()
    vol_historic = df['volume'].tail(63).mean()
    vol_surge = (vol_recent / vol_historic) if vol_historic > 0 else 1.0
    
    # Plafonnement du volume surge pour éviter qu'un volume extrême d'un jour écrase le score
    vol_surge = min(vol_surge, 5.0) 

    # Filtre de volatilité extrême (Filtre anti-anomalies / anti-penny stocks délirants)
    atr_series = calculate_atr(df)
    current_atr = atr_series.iloc[-1]
    atr_pct = current_atr / current_price

    if atr_pct > 0.15:  # Si l'action bouge de plus de 15% par jour en moyenne, on rejette (Intradable en Swing)
        return None

    # Normalisation mathématique basique (Somme pondérée via config.py)
    score = (ret_1m * cfg.w_ret_1m) + (ret_3m * cfg.w_ret_3m) + (vol_surge * cfg.w_vol_surge)

    return {
        "symbol": symbol,
        "score": round(score, 4),
        "close": round(current_price, 2),
        "ret_1m_%": round(ret_1m * 100, 2),
        "ret_3m_%": round(ret_3m * 100, 2),
        "vol_surge": round(vol_surge, 2),
        "atr_pct": round(atr_pct, 4)
    }

def run_screener(bars_dict: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    Orchestrateur : Analyse tout le dictionnaire de données et renvoie le classement.
    """
    logging.info(f"Analyse quantitative de {len(bars_dict)} actifs en cours...")
    
    results = []
    for sym, df in bars_dict.items():
        res = score_asset(sym, df)
        if res:
            results.append(res)
            
    if not results:
        logging.warning("Aucun actif n'a passé les filtres mathématiques.")
        return pd.DataFrame()

    results_df = pd.DataFrame(results)
    
    # Tri descendant par score de momentum
    results_df = results_df.sort_values(by="score", ascending=False).reset_index(drop=True)
    
    logging.info(f"Screener terminé. {len(results_df)} actifs scorés avec succès.")
    return results_df

# --------------------------------------------------------------------- TEST LOCAL
if __name__ == "__main__":
    import data
    from database import DatabaseManager # <-- IMPORT DU MODULE DB
    
    print("\n--- Démarrage de la chaîne complète (Data + Screener) ---")
    
    universe = data.get_universe(max_symbols=100)
    symbols = universe["symbol"].tolist()
    
    bars = data.get_daily_bars(symbols, lookback_days=100)
    
    if bars:
        rankings = run_screener(bars)
        print("\n🏆 TOP 10 MOMENTUM :")
        print(rankings.head(10).to_string(index=False))
        
        # SAUVEGARDE EN BASE DE DONNÉES
        DatabaseManager.save_screener_results(rankings)
    else:
        print("Erreur : Aucune donnée récupérée pour le screening.")