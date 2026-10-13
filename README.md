# Agent Text-to-SQL sur Lakehouse

Agent qui traduit des questions en langage naturel en SQL **validé et en lecture seule**
sur la couche gold d'un lakehouse DuckDB (données Olist + TPC-H), avec un banc d'évaluation
comparant plusieurs LLM (exactitude d'exécution, latence, coût).

> 🚧 Projet en cours de construction — voir [docs/ROADMAP.md](docs/ROADMAP.md).

## Prérequis

- [uv](https://docs.astral.sh/uv/) (installe Python 3.11+ automatiquement)
- `make`

## Démarrage

```bash
uv sync               # installe les dépendances
cp .env.example .env  # puis renseigner les clés API
make data             # construit data/lake.duckdb
make test
```

## Commandes

| Commande | Rôle |
|---|---|
| `make data` | Télécharge Olist, génère TPC-H, construit bronze → silver → gold |
| `make test` | Lance les tests |
| `make lint` | Vérifie le style (ruff) |
| `make eval MODEL=<nom>` | Lance l'évaluation d'un modèle |
| `make app` | Lance l'API et l'interface |

## Licence

Code sous licence MIT. Les jeux de données conservent leurs licences d'origine
(Olist : CC BY-NC-SA 4.0 ; TPC-H : générée localement via l'extension DuckDB).
