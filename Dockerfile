FROM python:3.11-slim
WORKDIR /app

# Installation des dépendances système requises pour compiler la connexion base de données
RUN apt-get update && apt-get install -y libpq-dev gcc && rm -rf /var/lib/apt/lists/*

# Installation des librairies de trading (bypasse Windows)
RUN pip install psycopg2-binary pandas python-dotenv alpaca-py

# Copie de tout ton code dans le conteneur
COPY . .

# Commande par défaut lors du lancement
CMD ["python", "screen.py"]