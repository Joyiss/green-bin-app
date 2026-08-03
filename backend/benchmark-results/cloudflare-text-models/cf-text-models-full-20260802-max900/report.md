# Cloudflare Text Model Benchmark Report

Generated: 2026-08-02T18:36:33.548856+00:00
Run directory: `C:\Users\mraja\CursorApps\green-bin-app\backend\benchmark-results\cloudflare-text-models\cf-text-models-full-20260802-max900`

## Configuration

Production provider and prompts were not changed. The benchmark calls Workers AI directly with benchmark-only model overrides.

Cloudflare settings: {"account_id_present": true, "api_base_url": "https://api.cloudflare.com/client/v4", "api_token_present": true, "model": "@cf/google/gemma-4-26b-a4b-it", "provider": "cloudflare_workers_ai", "timeout_seconds": 60.0}

Runs per case/model/mode requested: `3`
Per-call timeout seconds: `35.0`
Temperature: `0.1`
Requested maximum output tokens: `900` for every model/mode.

## Fairness Notes

- Each model receives identical prompts, source excerpts, schemas, temperature, timeout, and output-token cap for the same case and mode.
- `plain` mode sends no `response_format` and relies on local JSON extraction/validation.
- `schema` mode sends the same Cloudflare `response_format` object used by Green Bin for that use case.
- Cloudflare JSON Mode docs describe `response_format`; model pages for GPT-OSS 20B and Llama 3.3 70B list function calling/reasoning/batch rather than explicitly promising JSON schema mode, so schema support is measured empirically.
- Time to first token is approximated by time to response headers because the benchmark does not request streaming tokens.

## Overall Comparison

| model_label | mode | calls | complete_rate | schema_valid_rate | hallucination_rate | timeout_rate | api_error_rate | quota_exhausted_rate | median_latency_ms | p90_latency_ms | worst_latency_ms | estimated_cost_usd | estimated_neurons |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| gemma_configured | plain | 45 | 0.044 | 0.044 | 0.000 | 0.022 | 0.933 | 0.244 | 10768.3 | 12635.1 | 13443.0 | 0.012 | 1088.0 |
| gemma_configured | schema | 45 | 0.044 | 0.044 | 0.000 | 0.022 | 0.933 | 0.244 | 11135.8 | 12702.1 | 16661.4 | 0.012 | 1107.0 |
| gpt_oss_20b | plain | 45 | 0.244 | 0.356 | 0.111 | 0.000 | 0.533 | 0.267 | 3795.7 | 9495.8 | 11769.9 | 0.013 | 1192.4 |
| gpt_oss_20b | schema | 45 | 0.289 | 0.333 | 0.044 | 0.000 | 0.533 | 0.267 | 4916.1 | 7436.7 | 9130.1 | 0.014 | 1237.0 |
| llama_3_3_70b_fast | plain | 45 | 0.444 | 0.578 | 0.000 | 0.044 | 0.267 | 0.267 | 1991.2 | 3679.4 | 8013.2 | 0.019 | 1755.9 |
| llama_3_3_70b_fast | schema | 45 | 0.467 | 0.556 | 0.044 | 0.089 | 0.356 | 0.267 | 7632.4 | 21135.1 | 25882.8 | 0.019 | 1740.7 |

## Results By Case

| case_id | use_case | model_label | mode | run_index | complete | schema_valid | hallucination | failure_reason | latency_ms |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| analyzer_seattle_mouse_split | evidence_analysis | gemma_configured | plain | 1 | False | False | False | model_response_error | 8174.6 |
| analyzer_seattle_mouse_split | evidence_analysis | gemma_configured | schema | 1 | False | False | False | model_response_error | 10696.2 |
| analyzer_seattle_mouse_split | evidence_analysis | gpt_oss_20b | plain | 1 | True | True | False |  | 7203.6 |
| analyzer_seattle_mouse_split | evidence_analysis | gpt_oss_20b | schema | 1 | True | True | False |  | 8078.2 |
| analyzer_seattle_mouse_split | evidence_analysis | llama_3_3_70b_fast | plain | 1 | True | True | False |  | 4939.3 |
| analyzer_seattle_mouse_split | evidence_analysis | llama_3_3_70b_fast | schema | 1 | True | True | False |  | 14571.3 |
| analyzer_austin_mouse_municipal | evidence_analysis | gemma_configured | plain | 1 | False | False | False | model_response_error | 10546.7 |
| analyzer_austin_mouse_municipal | evidence_analysis | gemma_configured | schema | 1 | False | False | False | model_response_error | 10962.2 |
| analyzer_austin_mouse_municipal | evidence_analysis | gpt_oss_20b | plain | 1 | False | False | False | model_response_error | 8902.4 |
| analyzer_austin_mouse_municipal | evidence_analysis | gpt_oss_20b | schema | 1 | False | False | False | model_response_error | 6779.0 |
| analyzer_austin_mouse_municipal | evidence_analysis | llama_3_3_70b_fast | plain | 1 | False | True | False |  | 1675.6 |
| analyzer_austin_mouse_municipal | evidence_analysis | llama_3_3_70b_fast | schema | 1 | True | True | False |  | 14151.3 |
| analyzer_aa_battery_no_lead_acid | evidence_analysis | gemma_configured | plain | 1 | False | False | False | model_response_error | 9763.5 |
| analyzer_aa_battery_no_lead_acid | evidence_analysis | gemma_configured | schema | 1 | False | False | False | model_response_error | 10508.0 |
| analyzer_aa_battery_no_lead_acid | evidence_analysis | gpt_oss_20b | plain | 1 | False | False | False | model_response_error | 4957.8 |
| analyzer_aa_battery_no_lead_acid | evidence_analysis | gpt_oss_20b | schema | 1 | False | False | False | model_response_error | 6195.1 |
| analyzer_aa_battery_no_lead_acid | evidence_analysis | llama_3_3_70b_fast | plain | 1 | True | True | False |  | 3399.5 |
| analyzer_aa_battery_no_lead_acid | evidence_analysis | llama_3_3_70b_fast | schema | 1 | True | True | False |  | 9729.2 |
| analyzer_lead_acid_special_handling | evidence_analysis | gemma_configured | plain | 1 | False | False | False | model_response_error | 11769.5 |
| analyzer_lead_acid_special_handling | evidence_analysis | gemma_configured | schema | 1 | False | False | False | model_response_error | 9803.6 |
| analyzer_lead_acid_special_handling | evidence_analysis | gpt_oss_20b | plain | 1 | True | True | False |  | 5474.4 |
| analyzer_lead_acid_special_handling | evidence_analysis | gpt_oss_20b | schema | 1 | False | False | False | model_response_error | 9130.1 |
| analyzer_lead_acid_special_handling | evidence_analysis | llama_3_3_70b_fast | plain | 1 | True | True | False |  | 2960.5 |
| analyzer_lead_acid_special_handling | evidence_analysis | llama_3_3_70b_fast | schema | 1 | True | True | False |  | 9136.8 |
| analyzer_compost_banana_peel | evidence_analysis | gemma_configured | plain | 1 | False | False | False | model_response_error | 10533.6 |
| analyzer_compost_banana_peel | evidence_analysis | gemma_configured | schema | 1 | False | False | False | model_response_error | 10775.8 |
| analyzer_compost_banana_peel | evidence_analysis | gpt_oss_20b | plain | 1 | False | False | False | model_response_error | 5098.1 |
| analyzer_compost_banana_peel | evidence_analysis | gpt_oss_20b | schema | 1 | True | True | False |  | 5205.8 |
| analyzer_compost_banana_peel | evidence_analysis | llama_3_3_70b_fast | plain | 1 | False | True | False |  | 2602.0 |
| analyzer_compost_banana_peel | evidence_analysis | llama_3_3_70b_fast | schema | 1 | True | True | False |  | 10501.7 |
| analyzer_plastic_bag_store_takeback | evidence_analysis | gemma_configured | plain | 1 | False | False | False | model_response_error | 10619.8 |
| analyzer_plastic_bag_store_takeback | evidence_analysis | gemma_configured | schema | 1 | False | False | False | model_response_error | 11947.5 |
| analyzer_plastic_bag_store_takeback | evidence_analysis | gpt_oss_20b | plain | 1 | False | False | False | model_response_error | 6238.3 |
| analyzer_plastic_bag_store_takeback | evidence_analysis | gpt_oss_20b | schema | 1 | False | False | False | model_response_error | 5329.3 |
| analyzer_plastic_bag_store_takeback | evidence_analysis | llama_3_3_70b_fast | plain | 1 | True | True | False |  | 3679.4 |
| analyzer_plastic_bag_store_takeback | evidence_analysis | llama_3_3_70b_fast | schema | 1 | True | True | False |  | 23225.3 |
| analyzer_paint_hhw | evidence_analysis | gemma_configured | plain | 1 | False | False | False | model_response_error | 12340.5 |
| analyzer_paint_hhw | evidence_analysis | gemma_configured | schema | 1 | False | False | False | model_response_error | 12627.4 |
| analyzer_paint_hhw | evidence_analysis | gpt_oss_20b | plain | 1 | True | True | False |  | 4575.0 |
| analyzer_paint_hhw | evidence_analysis | gpt_oss_20b | schema | 1 | True | True | False |  | 6410.9 |
| analyzer_paint_hhw | evidence_analysis | llama_3_3_70b_fast | plain | 1 | True | True | False |  | 3105.3 |
| analyzer_paint_hhw | evidence_analysis | llama_3_3_70b_fast | schema | 1 | True | True | False |  | 18510.0 |
| analyzer_reuse_winter_coat | evidence_analysis | gemma_configured | plain | 1 | False | False | False | model_response_error | 10439.9 |
| analyzer_reuse_winter_coat | evidence_analysis | gemma_configured | schema | 1 | False | False | False | model_response_error | 10999.3 |
| analyzer_reuse_winter_coat | evidence_analysis | gpt_oss_20b | plain | 1 | True | True | False |  | 5999.8 |
| analyzer_reuse_winter_coat | evidence_analysis | gpt_oss_20b | schema | 1 | True | True | False |  | 7436.7 |
| analyzer_reuse_winter_coat | evidence_analysis | llama_3_3_70b_fast | plain | 1 | True | True | False |  | 3037.7 |
| analyzer_reuse_winter_coat | evidence_analysis | llama_3_3_70b_fast | schema | 1 | True | True | False |  | 20044.2 |
| analyzer_conflicting_curbside | conflict_handling | gemma_configured | plain | 1 | False | False | False | model_response_error | 11308.1 |
| analyzer_conflicting_curbside | conflict_handling | gemma_configured | schema | 1 | False | False | False | model_response_error | 11979.4 |
| analyzer_conflicting_curbside | conflict_handling | gpt_oss_20b | plain | 1 | False | False | False | model_response_error | 9495.8 |
| analyzer_conflicting_curbside | conflict_handling | gpt_oss_20b | schema | 1 | False | False | False | model_response_error | 5691.4 |
| analyzer_conflicting_curbside | conflict_handling | llama_3_3_70b_fast | plain | 1 | False | True | False |  | 1291.4 |
| analyzer_conflicting_curbside | conflict_handling | llama_3_3_70b_fast | schema | 1 | False | True | False |  | 25882.8 |
| analyzer_insufficient_similar_item | insufficient_evidence | gemma_configured | plain | 1 | False | False | False | model_response_error | 11615.7 |
| analyzer_insufficient_similar_item | insufficient_evidence | gemma_configured | schema | 1 | False | False | False | model_response_error | 11272.2 |
| analyzer_insufficient_similar_item | insufficient_evidence | gpt_oss_20b | plain | 1 | False | True | True |  | 4815.4 |
| analyzer_insufficient_similar_item | insufficient_evidence | gpt_oss_20b | schema | 1 | False | False | False | model_response_error | 6100.7 |
| analyzer_insufficient_similar_item | insufficient_evidence | llama_3_3_70b_fast | plain | 1 | True | True | False |  | 2458.0 |
| analyzer_insufficient_similar_item | insufficient_evidence | llama_3_3_70b_fast | schema | 1 | False | False | False | http_error | 17497.2 |
| guidance_mouse_no_fee_claim | guidance_generation | gemma_configured | plain | 1 | False | False | False | model_response_error | 10349.9 |
| guidance_mouse_no_fee_claim | guidance_generation | gemma_configured | schema | 1 | False | False | False | timeout | 35075.8 |
| guidance_mouse_no_fee_claim | guidance_generation | gpt_oss_20b | plain | 1 | False | False | False |  | 2712.0 |
| guidance_mouse_no_fee_claim | guidance_generation | gpt_oss_20b | schema | 1 | False | False | False |  | 4444.4 |
| guidance_mouse_no_fee_claim | guidance_generation | llama_3_3_70b_fast | plain | 1 | True | True | False |  | 1991.2 |
| guidance_mouse_no_fee_claim | guidance_generation | llama_3_3_70b_fast | schema | 1 | False | False | False | timeout | 35279.9 |
| guidance_aa_battery_no_ev_restrictions | guidance_generation | gemma_configured | plain | 1 | False | False | False | model_response_error | 11775.0 |
| guidance_aa_battery_no_ev_restrictions | guidance_generation | gemma_configured | schema | 1 | False | False | False | model_response_error | 10398.8 |
| guidance_aa_battery_no_ev_restrictions | guidance_generation | gpt_oss_20b | plain | 1 | False | False | True |  | 2407.8 |
| guidance_aa_battery_no_ev_restrictions | guidance_generation | gpt_oss_20b | schema | 1 | False | False | False |  | 1705.6 |
| guidance_aa_battery_no_ev_restrictions | guidance_generation | llama_3_3_70b_fast | plain | 1 | False | False | False |  | 1753.2 |
| guidance_aa_battery_no_ev_restrictions | guidance_generation | llama_3_3_70b_fast | schema | 1 | False | False | False | timeout | 35084.0 |
| guidance_exclusion_not_positive | guidance_generation | gemma_configured | plain | 1 | False | False | False | model_response_error | 11476.8 |
| guidance_exclusion_not_positive | guidance_generation | gemma_configured | schema | 1 | False | False | False | model_response_error | 11642.6 |
| guidance_exclusion_not_positive | guidance_generation | gpt_oss_20b | plain | 1 | False | False | False |  | 3622.6 |
| guidance_exclusion_not_positive | guidance_generation | gpt_oss_20b | schema | 1 | False | False | False |  | 3394.8 |
| guidance_exclusion_not_positive | guidance_generation | llama_3_3_70b_fast | plain | 1 | False | False | False |  | 2488.2 |
| guidance_exclusion_not_positive | guidance_generation | llama_3_3_70b_fast | schema | 1 | False | False | False | timeout | 35068.3 |
| classify_aa_alkaline | item_normalization_classification | gemma_configured | plain | 1 | True | True | False |  | 5225.5 |
| classify_aa_alkaline | item_normalization_classification | gemma_configured | schema | 1 | True | True | False |  | 10884.7 |
| classify_aa_alkaline | item_normalization_classification | gpt_oss_20b | plain | 1 | True | True | False |  | 816.7 |
| classify_aa_alkaline | item_normalization_classification | gpt_oss_20b | schema | 1 | True | True | False |  | 1070.0 |
| classify_aa_alkaline | item_normalization_classification | llama_3_3_70b_fast | plain | 1 | True | True | False |  | 831.4 |
| classify_aa_alkaline | item_normalization_classification | llama_3_3_70b_fast | schema | 1 | True | True | False |  | 3216.0 |
| classify_computer_mouse | item_normalization_classification | gemma_configured | plain | 1 | False | False | False | model_response_error | 10832.1 |
| classify_computer_mouse | item_normalization_classification | gemma_configured | schema | 1 | False | False | False | model_response_error | 11678.7 |
| classify_computer_mouse | item_normalization_classification | gpt_oss_20b | plain | 1 | False | True | True |  | 5168.3 |
| classify_computer_mouse | item_normalization_classification | gpt_oss_20b | schema | 1 | True | True | False |  | 7606.8 |
| classify_computer_mouse | item_normalization_classification | llama_3_3_70b_fast | plain | 1 | True | True | False |  | 704.6 |
| classify_computer_mouse | item_normalization_classification | llama_3_3_70b_fast | schema | 1 | False | True | True |  | 1896.2 |
| analyzer_seattle_mouse_split | evidence_analysis | gemma_configured | plain | 2 | False | False | False | model_response_error | 10704.4 |
| analyzer_seattle_mouse_split | evidence_analysis | gemma_configured | schema | 2 | False | False | False | model_response_error | 10847.3 |
| analyzer_seattle_mouse_split | evidence_analysis | gpt_oss_20b | plain | 2 | True | True | False |  | 3108.7 |
| analyzer_seattle_mouse_split | evidence_analysis | gpt_oss_20b | schema | 2 | True | True | False |  | 5209.0 |
| analyzer_seattle_mouse_split | evidence_analysis | llama_3_3_70b_fast | plain | 2 | True | True | False |  | 4383.8 |
| analyzer_seattle_mouse_split | evidence_analysis | llama_3_3_70b_fast | schema | 2 | True | True | False |  | 11370.3 |
| analyzer_austin_mouse_municipal | evidence_analysis | gemma_configured | plain | 2 | False | False | False | model_response_error | 12635.1 |
| analyzer_austin_mouse_municipal | evidence_analysis | gemma_configured | schema | 2 | False | False | False | model_response_error | 10964.8 |
| analyzer_austin_mouse_municipal | evidence_analysis | gpt_oss_20b | plain | 2 | False | False | False | model_response_error | 5470.0 |
| analyzer_austin_mouse_municipal | evidence_analysis | gpt_oss_20b | schema | 2 | False | True | False |  | 4803.0 |
| analyzer_austin_mouse_municipal | evidence_analysis | llama_3_3_70b_fast | plain | 2 | False | True | False |  | 1512.3 |
| analyzer_austin_mouse_municipal | evidence_analysis | llama_3_3_70b_fast | schema | 2 | True | True | False |  | 7632.4 |
| analyzer_aa_battery_no_lead_acid | evidence_analysis | gemma_configured | plain | 2 | False | False | False | model_response_error | 13443.0 |
| analyzer_aa_battery_no_lead_acid | evidence_analysis | gemma_configured | schema | 2 | False | False | False | model_response_error | 11860.8 |
| analyzer_aa_battery_no_lead_acid | evidence_analysis | gpt_oss_20b | plain | 2 | True | True | False |  | 6592.3 |
| analyzer_aa_battery_no_lead_acid | evidence_analysis | gpt_oss_20b | schema | 2 | False | False | False | model_response_error | 6944.3 |
| analyzer_aa_battery_no_lead_acid | evidence_analysis | llama_3_3_70b_fast | plain | 2 | True | True | False |  | 3301.7 |
| analyzer_aa_battery_no_lead_acid | evidence_analysis | llama_3_3_70b_fast | schema | 2 | True | True | False |  | 7475.9 |
| analyzer_lead_acid_special_handling | evidence_analysis | gemma_configured | plain | 2 | False | False | False | model_response_error | 12811.8 |
| analyzer_lead_acid_special_handling | evidence_analysis | gemma_configured | schema | 2 | False | False | False | model_response_error | 16661.4 |
| analyzer_lead_acid_special_handling | evidence_analysis | gpt_oss_20b | plain | 2 | False | False | False | model_response_error | 8437.8 |
| analyzer_lead_acid_special_handling | evidence_analysis | gpt_oss_20b | schema | 2 | True | True | False |  | 4916.1 |
| analyzer_lead_acid_special_handling | evidence_analysis | llama_3_3_70b_fast | plain | 2 | True | True | False |  | 2489.0 |
| analyzer_lead_acid_special_handling | evidence_analysis | llama_3_3_70b_fast | schema | 2 | True | True | False |  | 17325.6 |
| analyzer_compost_banana_peel | evidence_analysis | gemma_configured | plain | 2 | False | False | False | model_response_error | 12232.2 |
| analyzer_compost_banana_peel | evidence_analysis | gemma_configured | schema | 2 | False | False | False | model_response_error | 12320.0 |
| analyzer_compost_banana_peel | evidence_analysis | gpt_oss_20b | plain | 2 | True | True | False |  | 10025.8 |
| analyzer_compost_banana_peel | evidence_analysis | gpt_oss_20b | schema | 2 | True | True | False |  | 8212.9 |
| analyzer_compost_banana_peel | evidence_analysis | llama_3_3_70b_fast | plain | 2 | False | False | False | timeout | 35090.2 |
| analyzer_compost_banana_peel | evidence_analysis | llama_3_3_70b_fast | schema | 2 | True | True | False |  | 6963.4 |
| analyzer_plastic_bag_store_takeback | evidence_analysis | gemma_configured | plain | 2 | False | False | False | model_response_error | 8639.6 |
| analyzer_plastic_bag_store_takeback | evidence_analysis | gemma_configured | schema | 2 | False | False | False | model_response_error | 12539.5 |
| analyzer_plastic_bag_store_takeback | evidence_analysis | gpt_oss_20b | plain | 2 | False | False | False | model_response_error | 7448.1 |
| analyzer_plastic_bag_store_takeback | evidence_analysis | gpt_oss_20b | schema | 2 | False | False | False | model_response_error | 7363.6 |
| analyzer_plastic_bag_store_takeback | evidence_analysis | llama_3_3_70b_fast | plain | 2 | True | True | False |  | 4041.4 |
| analyzer_plastic_bag_store_takeback | evidence_analysis | llama_3_3_70b_fast | schema | 2 | True | True | False |  | 11919.4 |
| analyzer_paint_hhw | evidence_analysis | gemma_configured | plain | 2 | False | False | False | model_response_error | 12264.8 |
| analyzer_paint_hhw | evidence_analysis | gemma_configured | schema | 2 | False | False | False | model_response_error | 13010.7 |
| analyzer_paint_hhw | evidence_analysis | gpt_oss_20b | plain | 2 | False | False | False | model_response_error | 10377.4 |
| analyzer_paint_hhw | evidence_analysis | gpt_oss_20b | schema | 2 | False | False | False | model_response_error | 6600.5 |
| analyzer_paint_hhw | evidence_analysis | llama_3_3_70b_fast | plain | 2 | False | False | False | timeout | 35057.5 |
| analyzer_paint_hhw | evidence_analysis | llama_3_3_70b_fast | schema | 2 | True | True | False |  | 7599.8 |
| analyzer_reuse_winter_coat | evidence_analysis | gemma_configured | plain | 2 | False | False | False | model_response_error | 12670.2 |
| analyzer_reuse_winter_coat | evidence_analysis | gemma_configured | schema | 2 | False | False | False | model_response_error | 12621.8 |
| analyzer_reuse_winter_coat | evidence_analysis | gpt_oss_20b | plain | 2 | False | False | False | model_response_error | 7280.2 |
| analyzer_reuse_winter_coat | evidence_analysis | gpt_oss_20b | schema | 2 | True | True | False |  | 5454.6 |
| analyzer_reuse_winter_coat | evidence_analysis | llama_3_3_70b_fast | plain | 2 | True | True | False |  | 2610.7 |
| analyzer_reuse_winter_coat | evidence_analysis | llama_3_3_70b_fast | schema | 2 | True | True | False |  | 7382.7 |
| analyzer_conflicting_curbside | conflict_handling | gemma_configured | plain | 2 | False | False | False | model_response_error | 11889.0 |
| analyzer_conflicting_curbside | conflict_handling | gemma_configured | schema | 2 | False | False | False | model_response_error | 13426.8 |
| analyzer_conflicting_curbside | conflict_handling | gpt_oss_20b | plain | 2 | False | True | False |  | 8181.6 |
| analyzer_conflicting_curbside | conflict_handling | gpt_oss_20b | schema | 2 | False | False | False | model_response_error | 6035.1 |
| analyzer_conflicting_curbside | conflict_handling | llama_3_3_70b_fast | plain | 2 | False | True | False |  | 2570.6 |
| analyzer_conflicting_curbside | conflict_handling | llama_3_3_70b_fast | schema | 2 | False | True | False |  | 10352.8 |
| analyzer_insufficient_similar_item | insufficient_evidence | gemma_configured | plain | 2 | False | False | False | model_response_error | 13394.2 |
| analyzer_insufficient_similar_item | insufficient_evidence | gemma_configured | schema | 2 | False | False | False | model_response_error | 11922.2 |
| analyzer_insufficient_similar_item | insufficient_evidence | gpt_oss_20b | plain | 2 | False | True | True |  | 3795.7 |
| analyzer_insufficient_similar_item | insufficient_evidence | gpt_oss_20b | schema | 2 | True | True | False |  | 5503.4 |
| analyzer_insufficient_similar_item | insufficient_evidence | llama_3_3_70b_fast | plain | 2 | True | True | False |  | 2233.1 |
| analyzer_insufficient_similar_item | insufficient_evidence | llama_3_3_70b_fast | schema | 2 | False | False | False | http_error | 21135.1 |
| guidance_mouse_no_fee_claim | guidance_generation | gemma_configured | plain | 2 | False | False | False | timeout | 35062.3 |
| guidance_mouse_no_fee_claim | guidance_generation | gemma_configured | schema | 2 | False | False | False | model_response_error | 12062.0 |
| guidance_mouse_no_fee_claim | guidance_generation | gpt_oss_20b | plain | 2 | False | False | False |  | 3315.9 |
| guidance_mouse_no_fee_claim | guidance_generation | gpt_oss_20b | schema | 2 | False | False | False |  | 3722.1 |
| guidance_mouse_no_fee_claim | guidance_generation | llama_3_3_70b_fast | plain | 2 | False | False | False |  | 1500.4 |
| guidance_mouse_no_fee_claim | guidance_generation | llama_3_3_70b_fast | schema | 2 | False | False | False | http_error | 21969.1 |
| guidance_aa_battery_no_ev_restrictions | guidance_generation | gemma_configured | plain | 2 | False | False | False | model_response_error | 12131.1 |
| guidance_aa_battery_no_ev_restrictions | guidance_generation | gemma_configured | schema | 2 | False | False | False | model_response_error | 11592.2 |
| guidance_aa_battery_no_ev_restrictions | guidance_generation | gpt_oss_20b | plain | 2 | True | True | False |  | 1536.6 |
| guidance_aa_battery_no_ev_restrictions | guidance_generation | gpt_oss_20b | schema | 2 | False | False | True |  | 1800.9 |
| guidance_aa_battery_no_ev_restrictions | guidance_generation | llama_3_3_70b_fast | plain | 2 | False | False | False |  | 2011.2 |
| guidance_aa_battery_no_ev_restrictions | guidance_generation | llama_3_3_70b_fast | schema | 2 | False | False | False | http_error | 24286.2 |
| guidance_exclusion_not_positive | guidance_generation | gemma_configured | plain | 2 | False | False | False | model_response_error | 12629.6 |
| guidance_exclusion_not_positive | guidance_generation | gemma_configured | schema | 2 | False | False | False | model_response_error | 12149.0 |
| guidance_exclusion_not_positive | guidance_generation | gpt_oss_20b | plain | 2 | False | False | False |  | 1860.1 |
| guidance_exclusion_not_positive | guidance_generation | gpt_oss_20b | schema | 2 | False | False | False |  | 4386.0 |
| guidance_exclusion_not_positive | guidance_generation | llama_3_3_70b_fast | plain | 2 | False | False | False |  | 2387.6 |
| guidance_exclusion_not_positive | guidance_generation | llama_3_3_70b_fast | schema | 2 | False | False | False | timeout | 35075.0 |
| classify_aa_alkaline | item_normalization_classification | gemma_configured | plain | 2 | True | True | False |  | 5411.0 |
| classify_aa_alkaline | item_normalization_classification | gemma_configured | schema | 2 | True | True | False |  | 9093.4 |
| classify_aa_alkaline | item_normalization_classification | gpt_oss_20b | plain | 2 | True | True | False |  | 897.7 |
| classify_aa_alkaline | item_normalization_classification | gpt_oss_20b | schema | 2 | True | True | False |  | 875.8 |
| classify_aa_alkaline | item_normalization_classification | llama_3_3_70b_fast | plain | 2 | True | True | False |  | 849.1 |
| classify_aa_alkaline | item_normalization_classification | llama_3_3_70b_fast | schema | 2 | True | True | False |  | 1424.5 |
| classify_computer_mouse | item_normalization_classification | gemma_configured | plain | 2 | False | False | False | model_response_error | 11895.5 |
| classify_computer_mouse | item_normalization_classification | gemma_configured | schema | 2 | False | False | False | model_response_error | 11381.2 |
| classify_computer_mouse | item_normalization_classification | gpt_oss_20b | plain | 2 | False | True | True |  | 2505.9 |
| classify_computer_mouse | item_normalization_classification | gpt_oss_20b | schema | 2 | False | True | True |  | 1397.0 |
| classify_computer_mouse | item_normalization_classification | llama_3_3_70b_fast | plain | 2 | True | True | False |  | 746.8 |
| classify_computer_mouse | item_normalization_classification | llama_3_3_70b_fast | schema | 2 | False | True | True |  | 1207.2 |
| analyzer_seattle_mouse_split | evidence_analysis | gemma_configured | plain | 3 | False | False | False | model_response_error | 12621.8 |
| analyzer_seattle_mouse_split | evidence_analysis | gemma_configured | schema | 3 | False | False | False | model_response_error | 14462.4 |
| analyzer_seattle_mouse_split | evidence_analysis | gpt_oss_20b | plain | 3 | True | True | False |  | 10024.0 |
| analyzer_seattle_mouse_split | evidence_analysis | gpt_oss_20b | schema | 3 | False | False | False | model_response_error | 6934.1 |
| analyzer_seattle_mouse_split | evidence_analysis | llama_3_3_70b_fast | plain | 3 | True | True | False |  | 8013.2 |
| analyzer_seattle_mouse_split | evidence_analysis | llama_3_3_70b_fast | schema | 3 | True | True | False |  | 13748.6 |
| analyzer_austin_mouse_municipal | evidence_analysis | gemma_configured | plain | 3 | False | False | False | model_response_error | 12057.4 |
| analyzer_austin_mouse_municipal | evidence_analysis | gemma_configured | schema | 3 | False | False | False | model_response_error | 11565.1 |
| analyzer_austin_mouse_municipal | evidence_analysis | gpt_oss_20b | plain | 3 | False | False | False | model_response_error | 11769.9 |
| analyzer_austin_mouse_municipal | evidence_analysis | gpt_oss_20b | schema | 3 | False | False | False | model_response_error | 7113.7 |
| analyzer_austin_mouse_municipal | evidence_analysis | llama_3_3_70b_fast | plain | 3 | False | True | False |  | 2129.9 |
| analyzer_austin_mouse_municipal | evidence_analysis | llama_3_3_70b_fast | schema | 3 | True | True | False |  | 13418.7 |
| analyzer_aa_battery_no_lead_acid | evidence_analysis | gemma_configured | plain | 3 | False | False | False | model_response_error | 12389.5 |
| analyzer_aa_battery_no_lead_acid | evidence_analysis | gemma_configured | schema | 3 | False | False | False | model_response_error | 11535.7 |
| analyzer_aa_battery_no_lead_acid | evidence_analysis | gpt_oss_20b | plain | 3 | False | False | False | model_response_error | 8355.9 |
| analyzer_aa_battery_no_lead_acid | evidence_analysis | gpt_oss_20b | schema | 3 | True | True | False |  | 5888.4 |
| analyzer_aa_battery_no_lead_acid | evidence_analysis | llama_3_3_70b_fast | plain | 3 | True | True | False |  | 2700.5 |
| analyzer_aa_battery_no_lead_acid | evidence_analysis | llama_3_3_70b_fast | schema | 3 | True | True | False |  | 7973.3 |
| analyzer_lead_acid_special_handling | evidence_analysis | gemma_configured | plain | 3 | False | False | False | model_response_error | 11825.6 |
| analyzer_lead_acid_special_handling | evidence_analysis | gemma_configured | schema | 3 | False | False | False | model_response_error | 12702.1 |
| analyzer_lead_acid_special_handling | evidence_analysis | gpt_oss_20b | plain | 3 | False | False | False | quota_exhausted | 176.7 |
| analyzer_lead_acid_special_handling | evidence_analysis | gpt_oss_20b | schema | 3 | False | False | False | quota_exhausted | 146.8 |
| analyzer_lead_acid_special_handling | evidence_analysis | llama_3_3_70b_fast | plain | 3 | False | False | False | quota_exhausted | 157.2 |
| analyzer_lead_acid_special_handling | evidence_analysis | llama_3_3_70b_fast | schema | 3 | False | False | False | quota_exhausted | 382.3 |
| analyzer_compost_banana_peel | evidence_analysis | gemma_configured | plain | 3 | False | False | False | quota_exhausted | 115.1 |
| analyzer_compost_banana_peel | evidence_analysis | gemma_configured | schema | 3 | False | False | False | quota_exhausted | 120.3 |
| analyzer_compost_banana_peel | evidence_analysis | gpt_oss_20b | plain | 3 | False | False | False | quota_exhausted | 128.6 |
| analyzer_compost_banana_peel | evidence_analysis | gpt_oss_20b | schema | 3 | False | False | False | quota_exhausted | 135.3 |
| analyzer_compost_banana_peel | evidence_analysis | llama_3_3_70b_fast | plain | 3 | False | False | False | quota_exhausted | 112.9 |
| analyzer_compost_banana_peel | evidence_analysis | llama_3_3_70b_fast | schema | 3 | False | False | False | quota_exhausted | 312.8 |
| analyzer_plastic_bag_store_takeback | evidence_analysis | gemma_configured | plain | 3 | False | False | False | quota_exhausted | 121.5 |
| analyzer_plastic_bag_store_takeback | evidence_analysis | gemma_configured | schema | 3 | False | False | False | quota_exhausted | 136.1 |
| analyzer_plastic_bag_store_takeback | evidence_analysis | gpt_oss_20b | plain | 3 | False | False | False | quota_exhausted | 125.9 |
| analyzer_plastic_bag_store_takeback | evidence_analysis | gpt_oss_20b | schema | 3 | False | False | False | quota_exhausted | 207.2 |
| analyzer_plastic_bag_store_takeback | evidence_analysis | llama_3_3_70b_fast | plain | 3 | False | False | False | quota_exhausted | 118.7 |
| analyzer_plastic_bag_store_takeback | evidence_analysis | llama_3_3_70b_fast | schema | 3 | False | False | False | quota_exhausted | 320.7 |
| analyzer_paint_hhw | evidence_analysis | gemma_configured | plain | 3 | False | False | False | quota_exhausted | 308.1 |
| analyzer_paint_hhw | evidence_analysis | gemma_configured | schema | 3 | False | False | False | quota_exhausted | 138.1 |
| analyzer_paint_hhw | evidence_analysis | gpt_oss_20b | plain | 3 | False | False | False | quota_exhausted | 139.0 |
| analyzer_paint_hhw | evidence_analysis | gpt_oss_20b | schema | 3 | False | False | False | quota_exhausted | 126.8 |
| analyzer_paint_hhw | evidence_analysis | llama_3_3_70b_fast | plain | 3 | False | False | False | quota_exhausted | 110.8 |
| analyzer_paint_hhw | evidence_analysis | llama_3_3_70b_fast | schema | 3 | False | False | False | quota_exhausted | 304.7 |
| analyzer_reuse_winter_coat | evidence_analysis | gemma_configured | plain | 3 | False | False | False | quota_exhausted | 136.6 |
| analyzer_reuse_winter_coat | evidence_analysis | gemma_configured | schema | 3 | False | False | False | quota_exhausted | 139.4 |
| analyzer_reuse_winter_coat | evidence_analysis | gpt_oss_20b | plain | 3 | False | False | False | quota_exhausted | 150.2 |
| analyzer_reuse_winter_coat | evidence_analysis | gpt_oss_20b | schema | 3 | False | False | False | quota_exhausted | 712.8 |
| analyzer_reuse_winter_coat | evidence_analysis | llama_3_3_70b_fast | plain | 3 | False | False | False | quota_exhausted | 139.0 |
| analyzer_reuse_winter_coat | evidence_analysis | llama_3_3_70b_fast | schema | 3 | False | False | False | quota_exhausted | 312.5 |
| analyzer_conflicting_curbside | conflict_handling | gemma_configured | plain | 3 | False | False | False | quota_exhausted | 148.7 |
| analyzer_conflicting_curbside | conflict_handling | gemma_configured | schema | 3 | False | False | False | quota_exhausted | 131.6 |
| analyzer_conflicting_curbside | conflict_handling | gpt_oss_20b | plain | 3 | False | False | False | quota_exhausted | 118.3 |
| analyzer_conflicting_curbside | conflict_handling | gpt_oss_20b | schema | 3 | False | False | False | quota_exhausted | 146.5 |
| analyzer_conflicting_curbside | conflict_handling | llama_3_3_70b_fast | plain | 3 | False | False | False | quota_exhausted | 138.8 |
| analyzer_conflicting_curbside | conflict_handling | llama_3_3_70b_fast | schema | 3 | False | False | False | quota_exhausted | 348.7 |
| analyzer_insufficient_similar_item | insufficient_evidence | gemma_configured | plain | 3 | False | False | False | quota_exhausted | 118.8 |
| analyzer_insufficient_similar_item | insufficient_evidence | gemma_configured | schema | 3 | False | False | False | quota_exhausted | 333.0 |
| analyzer_insufficient_similar_item | insufficient_evidence | gpt_oss_20b | plain | 3 | False | False | False | quota_exhausted | 116.4 |
| analyzer_insufficient_similar_item | insufficient_evidence | gpt_oss_20b | schema | 3 | False | False | False | quota_exhausted | 169.2 |
| analyzer_insufficient_similar_item | insufficient_evidence | llama_3_3_70b_fast | plain | 3 | False | False | False | quota_exhausted | 129.8 |
| analyzer_insufficient_similar_item | insufficient_evidence | llama_3_3_70b_fast | schema | 3 | False | False | False | quota_exhausted | 337.4 |
| guidance_mouse_no_fee_claim | guidance_generation | gemma_configured | plain | 3 | False | False | False | quota_exhausted | 153.8 |
| guidance_mouse_no_fee_claim | guidance_generation | gemma_configured | schema | 3 | False | False | False | quota_exhausted | 141.1 |
| guidance_mouse_no_fee_claim | guidance_generation | gpt_oss_20b | plain | 3 | False | False | False | quota_exhausted | 108.9 |
| guidance_mouse_no_fee_claim | guidance_generation | gpt_oss_20b | schema | 3 | False | False | False | quota_exhausted | 134.9 |
| guidance_mouse_no_fee_claim | guidance_generation | llama_3_3_70b_fast | plain | 3 | False | False | False | quota_exhausted | 106.7 |
| guidance_mouse_no_fee_claim | guidance_generation | llama_3_3_70b_fast | schema | 3 | False | False | False | quota_exhausted | 400.3 |
| guidance_aa_battery_no_ev_restrictions | guidance_generation | gemma_configured | plain | 3 | False | False | False | quota_exhausted | 123.6 |
| guidance_aa_battery_no_ev_restrictions | guidance_generation | gemma_configured | schema | 3 | False | False | False | quota_exhausted | 160.5 |
| guidance_aa_battery_no_ev_restrictions | guidance_generation | gpt_oss_20b | plain | 3 | False | False | False | quota_exhausted | 124.9 |
| guidance_aa_battery_no_ev_restrictions | guidance_generation | gpt_oss_20b | schema | 3 | False | False | False | quota_exhausted | 119.3 |
| guidance_aa_battery_no_ev_restrictions | guidance_generation | llama_3_3_70b_fast | plain | 3 | False | False | False | quota_exhausted | 117.2 |
| guidance_aa_battery_no_ev_restrictions | guidance_generation | llama_3_3_70b_fast | schema | 3 | False | False | False | quota_exhausted | 360.2 |
| guidance_exclusion_not_positive | guidance_generation | gemma_configured | plain | 3 | False | False | False | quota_exhausted | 150.8 |
| guidance_exclusion_not_positive | guidance_generation | gemma_configured | schema | 3 | False | False | False | quota_exhausted | 324.3 |
| guidance_exclusion_not_positive | guidance_generation | gpt_oss_20b | plain | 3 | False | False | False | quota_exhausted | 140.6 |
| guidance_exclusion_not_positive | guidance_generation | gpt_oss_20b | schema | 3 | False | False | False | quota_exhausted | 120.4 |
| guidance_exclusion_not_positive | guidance_generation | llama_3_3_70b_fast | plain | 3 | False | False | False | quota_exhausted | 102.0 |
| guidance_exclusion_not_positive | guidance_generation | llama_3_3_70b_fast | schema | 3 | False | False | False | quota_exhausted | 351.7 |
| classify_aa_alkaline | item_normalization_classification | gemma_configured | plain | 3 | False | False | False | quota_exhausted | 159.9 |
| classify_aa_alkaline | item_normalization_classification | gemma_configured | schema | 3 | False | False | False | quota_exhausted | 138.5 |
| classify_aa_alkaline | item_normalization_classification | gpt_oss_20b | plain | 3 | False | False | False | quota_exhausted | 135.7 |
| classify_aa_alkaline | item_normalization_classification | gpt_oss_20b | schema | 3 | False | False | False | quota_exhausted | 113.5 |
| classify_aa_alkaline | item_normalization_classification | llama_3_3_70b_fast | plain | 3 | False | False | False | quota_exhausted | 117.7 |
| classify_aa_alkaline | item_normalization_classification | llama_3_3_70b_fast | schema | 3 | False | False | False | quota_exhausted | 368.9 |
| classify_computer_mouse | item_normalization_classification | gemma_configured | plain | 3 | False | False | False | quota_exhausted | 130.2 |
| classify_computer_mouse | item_normalization_classification | gemma_configured | schema | 3 | False | False | False | quota_exhausted | 103.6 |
| classify_computer_mouse | item_normalization_classification | gpt_oss_20b | plain | 3 | False | False | False | quota_exhausted | 134.4 |
| classify_computer_mouse | item_normalization_classification | gpt_oss_20b | schema | 3 | False | False | False | quota_exhausted | 145.3 |
| classify_computer_mouse | item_normalization_classification | llama_3_3_70b_fast | plain | 3 | False | False | False | quota_exhausted | 161.7 |
| classify_computer_mouse | item_normalization_classification | llama_3_3_70b_fast | schema | 3 | False | False | False | quota_exhausted | 331.3 |

## Important Successes And Failures

- `gemma_configured` `plain` `analyzer_seattle_mouse_split` run 1: failure=model_response_error validation={'schema_valid': False, 'action_correct': False, 'destination_correct': False, 'evidence_exact': False, 'citation_correct': False, 'combined_evidence': False, 'unsupported_claims': False, 'hallucination': False, 'complete': False, 'manual_review': False, 'errors': ['parsed_json_missing']}
- `gemma_configured` `schema` `analyzer_seattle_mouse_split` run 1: failure=model_response_error validation={'schema_valid': False, 'action_correct': False, 'destination_correct': False, 'evidence_exact': False, 'citation_correct': False, 'combined_evidence': False, 'unsupported_claims': False, 'hallucination': False, 'complete': False, 'manual_review': False, 'errors': ['parsed_json_missing']}
- `gemma_configured` `plain` `analyzer_austin_mouse_municipal` run 1: failure=model_response_error validation={'schema_valid': False, 'action_correct': False, 'destination_correct': False, 'evidence_exact': False, 'citation_correct': False, 'combined_evidence': False, 'unsupported_claims': False, 'hallucination': False, 'complete': False, 'manual_review': False, 'errors': ['parsed_json_missing']}
- `gemma_configured` `schema` `analyzer_austin_mouse_municipal` run 1: failure=model_response_error validation={'schema_valid': False, 'action_correct': False, 'destination_correct': False, 'evidence_exact': False, 'citation_correct': False, 'combined_evidence': False, 'unsupported_claims': False, 'hallucination': False, 'complete': False, 'manual_review': False, 'errors': ['parsed_json_missing']}
- `gpt_oss_20b` `plain` `analyzer_austin_mouse_municipal` run 1: failure=model_response_error validation={'schema_valid': False, 'action_correct': False, 'destination_correct': False, 'evidence_exact': False, 'citation_correct': False, 'combined_evidence': False, 'unsupported_claims': False, 'hallucination': False, 'complete': False, 'manual_review': False, 'errors': ['parsed_json_missing']}
- `gpt_oss_20b` `schema` `analyzer_austin_mouse_municipal` run 1: failure=model_response_error validation={'schema_valid': False, 'action_correct': False, 'destination_correct': False, 'evidence_exact': False, 'citation_correct': False, 'combined_evidence': False, 'unsupported_claims': False, 'hallucination': False, 'complete': False, 'manual_review': False, 'errors': ['parsed_json_missing']}
- `llama_3_3_70b_fast` `plain` `analyzer_austin_mouse_municipal` run 1: failure=None validation={'schema_valid': True, 'action_correct': False, 'destination_correct': False, 'evidence_exact': False, 'citation_correct': False, 'combined_evidence': False, 'unsupported_claims': False, 'hallucination': False, 'complete': False, 'manual_review': False, 'errors': [], 'validation_issues': [{'path': '$', 'reason': 'no_supported_route_or_usable_evidence'}], 'removed': [], 'status_correct': False, 'evidence_gaps_correct': False}
- `gemma_configured` `plain` `analyzer_aa_battery_no_lead_acid` run 1: failure=model_response_error validation={'schema_valid': False, 'action_correct': False, 'destination_correct': False, 'evidence_exact': False, 'citation_correct': False, 'combined_evidence': False, 'unsupported_claims': False, 'hallucination': False, 'complete': False, 'manual_review': False, 'errors': ['parsed_json_missing']}
- `gemma_configured` `schema` `analyzer_aa_battery_no_lead_acid` run 1: failure=model_response_error validation={'schema_valid': False, 'action_correct': False, 'destination_correct': False, 'evidence_exact': False, 'citation_correct': False, 'combined_evidence': False, 'unsupported_claims': False, 'hallucination': False, 'complete': False, 'manual_review': False, 'errors': ['parsed_json_missing']}
- `gpt_oss_20b` `plain` `analyzer_aa_battery_no_lead_acid` run 1: failure=model_response_error validation={'schema_valid': False, 'action_correct': False, 'destination_correct': False, 'evidence_exact': False, 'citation_correct': False, 'combined_evidence': False, 'unsupported_claims': False, 'hallucination': False, 'complete': False, 'manual_review': False, 'errors': ['parsed_json_missing']}
- `gpt_oss_20b` `schema` `analyzer_aa_battery_no_lead_acid` run 1: failure=model_response_error validation={'schema_valid': False, 'action_correct': False, 'destination_correct': False, 'evidence_exact': False, 'citation_correct': False, 'combined_evidence': False, 'unsupported_claims': False, 'hallucination': False, 'complete': False, 'manual_review': False, 'errors': ['parsed_json_missing']}
- `gemma_configured` `plain` `analyzer_lead_acid_special_handling` run 1: failure=model_response_error validation={'schema_valid': False, 'action_correct': False, 'destination_correct': False, 'evidence_exact': False, 'citation_correct': False, 'combined_evidence': False, 'unsupported_claims': False, 'hallucination': False, 'complete': False, 'manual_review': False, 'errors': ['parsed_json_missing']}
- `gemma_configured` `schema` `analyzer_lead_acid_special_handling` run 1: failure=model_response_error validation={'schema_valid': False, 'action_correct': False, 'destination_correct': False, 'evidence_exact': False, 'citation_correct': False, 'combined_evidence': False, 'unsupported_claims': False, 'hallucination': False, 'complete': False, 'manual_review': False, 'errors': ['parsed_json_missing']}
- `gpt_oss_20b` `schema` `analyzer_lead_acid_special_handling` run 1: failure=model_response_error validation={'schema_valid': False, 'action_correct': False, 'destination_correct': False, 'evidence_exact': False, 'citation_correct': False, 'combined_evidence': False, 'unsupported_claims': False, 'hallucination': False, 'complete': False, 'manual_review': False, 'errors': ['parsed_json_missing']}
- `gemma_configured` `plain` `analyzer_compost_banana_peel` run 1: failure=model_response_error validation={'schema_valid': False, 'action_correct': False, 'destination_correct': False, 'evidence_exact': False, 'citation_correct': False, 'combined_evidence': False, 'unsupported_claims': False, 'hallucination': False, 'complete': False, 'manual_review': False, 'errors': ['parsed_json_missing']}
- `gemma_configured` `schema` `analyzer_compost_banana_peel` run 1: failure=model_response_error validation={'schema_valid': False, 'action_correct': False, 'destination_correct': False, 'evidence_exact': False, 'citation_correct': False, 'combined_evidence': False, 'unsupported_claims': False, 'hallucination': False, 'complete': False, 'manual_review': False, 'errors': ['parsed_json_missing']}
- `gpt_oss_20b` `plain` `analyzer_compost_banana_peel` run 1: failure=model_response_error validation={'schema_valid': False, 'action_correct': False, 'destination_correct': False, 'evidence_exact': False, 'citation_correct': False, 'combined_evidence': False, 'unsupported_claims': False, 'hallucination': False, 'complete': False, 'manual_review': False, 'errors': ['parsed_json_missing']}
- `llama_3_3_70b_fast` `plain` `analyzer_compost_banana_peel` run 1: failure=None validation={'schema_valid': True, 'action_correct': False, 'destination_correct': False, 'evidence_exact': False, 'citation_correct': False, 'combined_evidence': True, 'unsupported_claims': False, 'hallucination': False, 'complete': False, 'manual_review': False, 'errors': [], 'validation_issues': [{'path': 'primary_route.action', 'reason': 'invalid_action'}, {'path': 'primary_route', 'reason': 'missing_supported_route'}, {'path': '$', 'reason': 'no_supported_route_or_usable_evidence'}], 'removed': [{'path': 'primary_route', 'reason': 'invalid_action', 'value': {'action': 'curbside_compost', 'destination_name': 'Green Compost Cart', 'confidence': 'high', 'supporting_claims': [{'claim': 'Banana peels are accepted for composting in Portland.', 'source_id': 'portland', 'evidence_text': 'Portland residents may place fruit and vegetable scraps, including banana peels, in the green compost cart.'}]}}], 'status_correct': False}
- `gemma_configured` `plain` `analyzer_plastic_bag_store_takeback` run 1: failure=model_response_error validation={'schema_valid': False, 'action_correct': False, 'destination_correct': False, 'evidence_exact': False, 'citation_correct': False, 'combined_evidence': False, 'unsupported_claims': False, 'hallucination': False, 'complete': False, 'manual_review': False, 'errors': ['parsed_json_missing']}
- `gemma_configured` `schema` `analyzer_plastic_bag_store_takeback` run 1: failure=model_response_error validation={'schema_valid': False, 'action_correct': False, 'destination_correct': False, 'evidence_exact': False, 'citation_correct': False, 'combined_evidence': False, 'unsupported_claims': False, 'hallucination': False, 'complete': False, 'manual_review': False, 'errors': ['parsed_json_missing']}

## Recommendations

This section is benchmark-derived. Review raw outputs before changing production configuration.