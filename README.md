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

## Modèles

Le projet fonctionne sans frais avec un modèle local via [Ollama](https://ollama.com) :

```bash
ollama pull qwen2.5-coder:7b
```

Le prompt (schéma + glossaire + exemples) fait environ 6 000 tokens, alors qu'Ollama
charge les modèles avec une fenêtre de 4 096 tokens par défaut et **tronque le prompt en silence**.
Définir la variable d'environnement `OLLAMA_CONTEXT_LENGTH=8192` puis redémarrer Ollama.
L'agent détecte la troncature et affiche une erreur explicite si ce réglage manque.

Autres modèles : `groq/<modèle>` (`GROQ_API_KEY`), `gemini/<modèle>` (`GEMINI_API_KEY`),
`claude-<modèle>` (`ANTHROPIC_API_KEY`).

## Commandes

| Commande | Rôle |
|---|---|
| `make ask Q="Combien de commandes en 2017 ?"` | Pose une question à l'agent |
| `make data` | Télécharge Olist, génère TPC-H, construit bronze → silver → gold |
| `make catalog` | Régénère le catalogue sémantique |
| `make test` | Lance les tests |
| `make lint` | Vérifie le style (ruff) |
| `make eval MODEL=<nom>` | Lance l'évaluation d'un modèle |
| `make app` | Lance l'API (http://localhost:8000/docs) et l'interface (http://localhost:8501) |
| `docker compose up --build` | Même chose dans des conteneurs (Ollama reste sur la machine hôte) |

## Licence

Code sous licence MIT. Les jeux de données conservent leurs licences d'origine
(Olist : CC BY-NC-SA 4.0 ; TPC-H : générée localement via l'extension DuckDB).
