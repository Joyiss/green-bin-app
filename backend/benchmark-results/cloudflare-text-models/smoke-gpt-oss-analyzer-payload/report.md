# Cloudflare Text Model Benchmark Report

Generated: 2026-08-02T18:01:05.443991+00:00
Run directory: `C:\Users\mraja\CursorApps\green-bin-app\backend\benchmark-results\cloudflare-text-models\smoke-gpt-oss-analyzer-payload`

## Configuration

Production provider and prompts were not changed. The benchmark calls Workers AI directly with benchmark-only model overrides.

Cloudflare settings: {"account_id_present": true, "api_base_url": "https://api.cloudflare.com/client/v4", "api_token_present": true, "model": "@cf/google/gemma-4-26b-a4b-it", "provider": "cloudflare_workers_ai", "timeout_seconds": 60.0}

Runs per case/model/mode requested: `1`
Per-call timeout seconds: `20.0`
Temperature: `0.1`
Requested maximum output tokens: not set, matching current text LLM production calls.

## Fairness Notes

- Each model receives identical prompts, source excerpts, schemas, temperature, timeout, and no explicit output-token cap for the same case and mode.
- `plain` mode sends no `response_format` and relies on local JSON extraction/validation.
- `schema` mode sends the same Cloudflare `response_format` object used by Green Bin for that use case.
- Cloudflare JSON Mode docs describe `response_format`; model pages for GPT-OSS 20B and Llama 3.3 70B list function calling/reasoning/batch rather than explicitly promising JSON schema mode, so schema support is measured empirically.
- Time to first token is approximated by time to response headers because the benchmark does not request streaming tokens.

## Overall Comparison

| model_label | mode | calls | complete_rate | schema_valid_rate | hallucination_rate | timeout_rate | api_error_rate | median_latency_ms | p90_latency_ms | worst_latency_ms | estimated_cost_usd | estimated_neurons |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| gpt_oss_20b | plain | 1 | 0.000 | 0.000 | 0.000 | 0.000 | 1.000 | 1789.7 | 1789.7 | 1789.7 | 0.000 | 25.7 |

## Results By Case

| case_id | use_case | model_label | mode | run_index | complete | schema_valid | hallucination | failure_reason | latency_ms |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| analyzer_seattle_mouse_split | evidence_analysis | gpt_oss_20b | plain | 1 | False | False | False | model_response_error | 1789.7 |

## Important Successes And Failures

- `gpt_oss_20b` `plain` `analyzer_seattle_mouse_split` run 1: failure=model_response_error validation={'schema_valid': False, 'action_correct': False, 'destination_correct': False, 'evidence_exact': False, 'citation_correct': False, 'combined_evidence': False, 'unsupported_claims': False, 'hallucination': False, 'complete': False, 'manual_review': False, 'errors': ['parsed_json_missing']}

## Recommendations

This section is benchmark-derived. Review raw outputs before changing production configuration.