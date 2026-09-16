# Momentum Screener US — squelette V1

Screener quotidien d'actions américaines en forte hausse, avec bonus pour les
secteurs porteurs (défense, quantique, spatial, infra IA) et les cotations récentes.

**Il ne passe aucun ordre.** Il produit une liste de candidats classés + un
dimensionnement de position suggéré. La décision reste humaine.

## Installation

```bash
pip install -r requirements.txt
export ALPACA_API_KEY=...        # clés "Paper" sur alpaca.markets
export ALPACA_SECRET_KEY=...
export FINNHUB_API_KEY=...       # optionnel, pour le calendrier IPO
```

## Utilisation

```bash
python test_signals.py            # vérifie la logique, sans réseau
python screen.py --themes-only    # scan rapide des listes thématiques
python screen.py --equity 20000   # scan complet, sizing pour 20 000 €
```

## Fichiers

| Fichier | Rôle |
|---|---|
| `config.py` | tous les paramètres + les listes thématiques à maintenir |
| `data.py` | accès Alpaca (univers, barres journalières) et calendrier IPO |
| `signals.py` | indicateurs, filtres éliminatoires, score composite, sizing |
| `screen.py` | orchestration, sortie CSV |
| `test_signals.py` | tests sur données synthétiques |

## Logique du score

1. **Filtres éliminatoires** — prix > 5 $, liquidité > 5 M$/j, au-dessus de la
   MM50, ATR < 12 %, moins de 25 % sous le plus haut 52 semaines.
2. **Score composite** — z-scores transversaux (chaque titre comparé aux autres
   du jour) sur : rendement 1/3/6 mois, force relative vs SPY, proximité du plus
   haut, pic de volume. Les seuils absolus sont évités volontairement.
3. **Bonus** — +0,30 secteur thématique, +0,20 cotation < 1 an.
4. **Sizing** — risque fixe de 0,5 % du capital par position, stop à 2,5 × ATR,
   8 % maximum du capital par ligne.

## Limites connues

- Le plan gratuit Alpaca utilise le flux **IEX** (~2 % du volume US) : les prix
  journaliers sont fiables, l'intraday l'est beaucoup moins.
- La détection d'IPO sans clé Finnhub repose sur l'ancienneté de l'historique :
  elle produit des faux positifs (changements de ticker, re-listings).
- Les listes thématiques sont statiques. C'est un choix : un classifieur
  automatique de secteur est bruité et non auditable.
- **Rien ici n'a été backtesté.** C'est l'étape suivante, avant tout argent réel.
"# momentum_screener" 
"# momentum_screener" 
"# momentum_screener" 
"# momentum_screener" 
"# momentum_screener" 
"# momentum_screener" 
"# momentum_screener" 
"# momentum_screener" 
"# momentum_screener" 
"# momentum_screener" 
