# Green Bin Reliability Benchmark

The deterministic benchmark replays recorded open-VLM responses through the
same parser, normalization, retrieval, and guidance code used by the app. It is
the required regression test:

```powershell
python -m benchmarks.reliability_benchmark
```

The optional live benchmark sends the eight representative images in
`backend/benchmark_images` to the configured open VLM. Live output is useful for
prompt comparisons but is not deterministic:

```powershell
python -m benchmarks.reliability_benchmark --mode live --output benchmark-results/live.json
```

Use `--case CASE_ID` to run a subset. Live mode reports regressions without a
failing exit code unless `--strict-live` is supplied. Recorded-fixture mode
always fails for unexpected regressions; documented current gaps remain visible
as expected failures until their owning reliability phase fixes them.

