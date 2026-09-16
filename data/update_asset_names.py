"""
update_asset_names.py — Met à jour les vrais noms d'entreprises depuis Alpaca.
"""
import os
import logging
from dotenv import load_dotenv
import psycopg2
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import GetAssetsRequest
from alpaca.trading.enums import AssetClass, AssetStatus

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
load_dotenv()

def update_company_names():
    # 1. Connexion Alpaca
    trading_client = TradingClient(
        os.getenv('ALPACA_API_KEY'), 
        os.getenv('ALPACA_SECRET_KEY'), 
        paper=True
    )
    
    logging.info("Récupération du référentiel officiel des actifs depuis Alpaca...")
    assets = trading_client.get_all_assets(
        GetAssetsRequest(status=AssetStatus.ACTIVE, asset_class=AssetClass.US_EQUITY)
    )
    
    # Création d'un dictionnaire {symbol: company_name}
    symbol_to_name = {asset.symbol: asset.name for asset in assets if asset.name}
    logging.info(f"{len(symbol_to_name)} actifs récupérés auprès d'Alpaca.")

    # 2. Connexion PostgreSQL
    conn = psycopg2.connect(
        host=os.getenv('DB_HOST', '127.0.0.1'),
        database=os.getenv('DB_NAME', 'trading_db'),
        user=os.getenv('DB_USER', 'horace_quant'),
        password=os.getenv('DB_PASS')
    )
    cur = conn.cursor()

    # 3. Récupération des tickers présents dans ta base locale
    cur.execute("SELECT ticker FROM assets;")
    local_tickers = [row[0] for row in cur.fetchall()]
    logging.info(f"Mise à jour des noms pour {len(local_tickers)} tickers locaux...")

    updated_count = 0
    for ticker in local_tickers:
        real_name = symbol_to_name.get(ticker)
        if real_name:
            cur.execute(
                "UPDATE assets SET name = %s WHERE ticker = %s;",
                (real_name, ticker)
            )
            updated_count += 1

    conn.commit()
    cur.close()
    conn.close()
    logging.info(f"Succès : {updated_count} noms d'entreprises mis à jour dans PostgreSQL.")

if __name__ == "__main__":
    update_company_names()