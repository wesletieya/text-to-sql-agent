# Résultats de l'évaluation

| Modèle | Runs | Précision | Exécution | SQL valide | Refus corrects | Latence moy. (p95) | Tokens/question | Coût/question | Pareto |
|---|---|---|---|---|---|---|---|---|---|
| qwen2.5-coder:7b | 1 | 81.3% ± 0.0% | 85.2% | 96.3% | 50.0% | 19.3 s (50.5 s) | 6,540 | $0.00000 | ✅ |

## Par catégorie

| category | qwen2.5-coder:7b |
|---|---|
| aggregation | 92% |
| ambiguous | 0% |
| filtering | 90% |
| glossary | 90% |
| join | 73% |
| out_of_scope | 100% |
| ranking | 80% |
| time | 90% |
| tpch | 100% |
| trap | 60% |

## Par difficulté

| difficulty | qwen2.5-coder:7b |
|---|---|
| easy | 95% |
| hard | 70% |
| medium | 70% |

## Échecs (17)

- `q011` (qwen2.5-coder:7b, run 1): status=answered
- `q023` (qwen2.5-coder:7b, run 1): status=failed
- `q026` (qwen2.5-coder:7b, run 1): status=answered
- `q035` (qwen2.5-coder:7b, run 1): status=failed
- `q042` (qwen2.5-coder:7b, run 1): status=failed
- `q044` (qwen2.5-coder:7b, run 1): status=answered
- `q049` (qwen2.5-coder:7b, run 1): status=answered
- `q055` (qwen2.5-coder:7b, run 1): status=answered
- `q057` (qwen2.5-coder:7b, run 1): status=answered
- `q062` (qwen2.5-coder:7b, run 1): status=answered
- `q063` (qwen2.5-coder:7b, run 1): status=answered
- `q066` (qwen2.5-coder:7b, run 1): status=answered
- `q087` (qwen2.5-coder:7b, run 1): status=answered
- `q088` (qwen2.5-coder:7b, run 1): status=answered
- `q089` (qwen2.5-coder:7b, run 1): status=answered
- `q090` (qwen2.5-coder:7b, run 1): status=answered
- `q091` (qwen2.5-coder:7b, run 1): status=answered
