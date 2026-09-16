"""
database.py — Gestionnaire de pool de connexions et d'écritures asynchrones.
"""
import os
import logging
from datetime import datetime
import pandas as pd
from dotenv import load_dotenv
import psycopg2
from psycopg2.pool import ThreadedConnectionPool
from psycopg2.extras import execute_values

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
load_dotenv()

class DatabaseManager:
    _pool = None

    @classmethod
    def get_pool(cls):
        """Initialise le pool de connexions (Singleton) pour éviter de surcharger PostgreSQL."""
        if cls._pool is None:
            try:
                cls._pool = ThreadedConnectionPool(
                    minconn=1,
                    maxconn=10,
                    host=os.getenv('DB_HOST', '127.0.0.1'),
                    port=os.getenv('DB_PORT', '5433'),
                    database=os.getenv('DB_NAME', 'trading_db'),
                    user=os.getenv('DB_USER', 'horace_quant'),
                    password=os.getenv('DB_PASS')
                )
                logging.info("Connection Pool PostgreSQL initialisé avec succès.")
            except psycopg2.Error as e:
                logging.error(f"CRITIQUE : Impossible de se connecter à la DB : {e}")
                raise
        return cls._pool

    @classmethod
    def save_screener_results(cls, df: pd.DataFrame):
        """
        Insère le DataFrame de résultats dans momentum_scores_daily.
        Vérifie et met à jour automatiquement le référentiel 'assets' pour éviter
        les erreurs de Foreign Key (Tickers manquants).
        """
        if df.empty:
            logging.warning("DataFrame vide, aucune insertion DB.")
            return

        pool = cls.get_pool()
        conn = pool.getconn()
        current_date = datetime.utcnow().date()
        
        # 1. Préparation des données pour le référentiel (Table: assets)
        # On utilise current_date comme ipo_date par défaut si l'action n'existe pas encore
        assets_tuples = [
            (row['symbol'], row['symbol'], current_date, True) 
            for _, row in df.iterrows()
        ]

        # 2. Préparation des données pour les métriques (Table: momentum_scores_daily)
        scores_tuples = [
            (
                current_date,
                row['symbol'],
                row['score'],
                row['close'],
                row['ret_1m_%'],
                row['ret_3m_%'],
                row['vol_surge'],
                row['atr_pct']
            ) for _, row in df.iterrows()
        ]

        # Requête A : Injecte les symboles inconnus (Ignore ceux qui existent déjà)
        query_assets = """
            INSERT INTO assets (ticker, name, ipo_date, is_active)
            VALUES %s
            ON CONFLICT (ticker) DO NOTHING;
        """

        # Requête B : Mise à jour des scores
        query_scores = """
            INSERT INTO momentum_scores_daily 
                (date, symbol, score, close_price, ret_1m_pct, ret_3m_pct, vol_surge, atr_pct)
            VALUES %s
            ON CONFLICT (date, symbol) DO UPDATE SET
                score = EXCLUDED.score,
                close_price = EXCLUDED.close_price,
                ret_1m_pct = EXCLUDED.ret_1m_pct,
                ret_3m_pct = EXCLUDED.ret_3m_pct,
                vol_surge = EXCLUDED.vol_surge,
                atr_pct = EXCLUDED.atr_pct,
                created_at = CURRENT_TIMESTAMP;
        """

        try:
            with conn.cursor() as cur:
                # L'ordre est strict : Parent (assets) PUIS Enfant (scores)
                execute_values(cur, query_assets, assets_tuples)
                execute_values(cur, query_scores, scores_tuples)
                
            conn.commit()
            logging.info(f"Succès : {len(df)} scores journaliers stockés en base.")
        except Exception as e:
            conn.rollback()
            logging.error(f"Erreur lors de l'insertion en base : {e}")
        finally:
            pool.putconn(conn)

# --------------------------------------------------------------------- TEST LOCAL
if __name__ == "__main__":
    # Test d'initiation du pool
    db = DatabaseManager()
    pool = db.get_pool()
    if pool:
        print("Test de la couche Base de Données OK.")