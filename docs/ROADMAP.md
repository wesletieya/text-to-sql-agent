# Roadmap — Agent Text-to-SQL

Chaque phase se termine par : `make lint` et `make test` au vert, puis un commit.
Cocher les cases seulement quand le critère de fin est vérifié.

## Phase 0 — Squelette du projet
- [x] `pyproject.toml` (uv), dépendances, config ruff et pytest
- [x] `Makefile` avec `data`, `test`, `lint`, `eval`, `app`
- [x] `.gitignore` (data/, *.duckdb, .env, kaggle.json, eval/results/*.jsonl)
- [x] `.env.example`, `README.md` minimal, licence MIT
- [x] CI GitHub Actions : lint + tests
- **Fin** : `make lint && make test` passent sur un repo vide de logique.

## Phase 1 — Données et lakehouse
- [ ] `scripts/download_olist.py` (kagglehub ou CLI Kaggle, message clair si pas de jeton)
- [ ] `scripts/generate_tpch.py` (`CALL dbgen(sf = 0.1)` dans un schéma `tpch`)
- [ ] `scripts/build_lakehouse.py` : schémas `bronze`, `silver`, `gold`
- [ ] Gold Olist : dim_customer, dim_seller, dim_product, dim_date, fact_orders,
      fact_order_items, fact_payments, fact_reviews (+ colonnes dérivées delivery_days, is_late, category_en)
- [ ] Tests de qualité : clés uniques, pas de clés étrangères orphelines, nombre de lignes attendu
- [ ] `tests/fixtures/` : mini-échantillons commités pour la CI
- **Fin** : `make data` reconstruit tout depuis zéro ; les tests de qualité passent.

## Phase 2 — Catalogue sémantique
- [ ] `scripts/build_catalog.py` : lit `information_schema`, ajoute valeurs d'exemple
      des colonnes catégorielles, fusionne avec les descriptions manuelles
- [ ] `semantic/catalog.yaml` : descriptions, clés de jointure, glossaire métier (CA, client actif, retard…)
- [ ] `semantic/fewshot.yaml` : 5 à 8 exemples question → SQL vérifiés
- **Fin** : le catalogue se régénère sans perdre les descriptions manuelles.

## Phase 3 — Validateur et exécuteur (le cœur sécurité)
- [ ] `agent/validator.py` (AST sqlglot, voir règles du CLAUDE.md)
- [ ] `agent/executor.py` : connexion read_only, timeout via `con.interrupt()`, plafond de lignes
- [ ] Tests d'attaque : `DROP`, `DELETE`, multi-instructions, `COPY`, `ATTACH`, `read_csv('/etc/passwd')`,
      CTE piégée, table inconnue, colonne inventée, commentaire SQL cachant une instruction
- [ ] Tests positifs : CTE, fenêtres, UNION, sous-requêtes légitimes passent
- **Fin** : 100 % des attaques bloquées, 100 % des requêtes légitimes acceptées.

## Phase 4 — Agent
- [ ] `agent/llm.py` : interface + adaptateurs (Anthropic, OpenAI-compatible/Ollama), comptage tokens et latence
- [ ] `agent/schema_retriever.py` (tout le catalogue d'abord ; récupération top-k ensuite)
- [ ] `agent/generator.py` : sortie structurée pydantic (`needs_clarification`, `out_of_scope`, `sql`, `reasoning`)
- [ ] `agent/pipeline.py` : génération → validation → exécution → auto-correction (max 2) → réponse
- [ ] CLI : `uv run python -m agent.pipeline "question"`
- **Fin** : 10 questions variées répondues correctement à la main.

## Phase 5 — Évaluation
- [ ] `eval/dataset.jsonl` : 80–150 questions, catégories et difficultés (voir README)
- [ ] Script qui vérifie que chaque `gold_sql` s'exécute et ne figure pas dans `fewshot.yaml`
- [ ] `eval/metrics.py` : execution match (ordre, arrondis, NULL), taux de SQL valide, refus corrects
- [ ] `eval/run.py` : N exécutions, résultats JSONL horodatés
- [ ] `eval/pricing.yaml` (tarifs datés et sourcés) ; `eval/report.py` : tableau + Pareto précision/coût
- **Fin** : baseline mesurée pour un premier modèle.

## Phase 6 — Comparaison de modèles
- [ ] 3 modèles (frontière, rapide, open-weights local) dans les mêmes conditions
- [ ] Ablations : sans glossaire / sans few-shot / sans auto-correction
- [ ] `docs/error_analysis.md` : 20–30 échecs classés par cause
- [ ] Bonus : routage petit modèle → gros modèle en cas d'échec
- **Fin** : tableau de résultats et graphiques dans le README.

## Phase 7 — API, UI, observabilité
- [ ] `app/api.py` : `POST /ask` → `{answer, sql, rows, latency_ms, cost_usd, attempts}`
- [ ] `app/ui.py` : question, SQL repliable, tableau, graphique auto, 👍/👎
- [ ] Logs JSON structurés ; traçage optionnel (Langfuse ou MLflow)
- [ ] `docker-compose.yml`
- **Fin** : démo complète en local via `make app`.

## Phase 8 — CI d'évaluation et valorisation
- [ ] Job CI : sous-ensemble de 20 questions sur TPC-H, échec si la précision baisse
- [ ] README final : architecture, garde-fous, résultats, limites, données et licences
- [ ] GIF de démo, article
