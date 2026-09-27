# Reproducible local benchmarks

ControlSurface ships benchmark harnesses instead of marketing estimates. Run them only against a disposable Compose project: they create an owner, API key, synthetic traces, and ClickHouse data. Results describe one machine and one workload; they are not capacity guarantees.

## System benchmark

Start a fresh stack, set an ephemeral `CS_BENCH_OWNER_PASSWORD`, then run:

```sh
docker compose --profile benchmark build benchmark
docker compose --profile benchmark run --rm benchmark \
  --spans 10000 --batch-size 100 --concurrency 4 --sdk-iterations 20000
```

The harness measures manual SDK span creation without an exporter, authenticated OTLP acknowledgement, end-to-end visibility in the ClickHouse projection, trace-list and trace-detail API requests, deterministic failure clustering, 1K/10K-span trace detail, and measured storage growth. It refuses to run when the database contains anything other than its single `Benchmark` project.

## Browser rendering benchmark

After the system benchmark, expose the disposable API/web services on loopback and pass the two trace IDs printed under `trace_detail_scaling`:

```sh
CS_BENCH_WEB_URL=http://localhost:3000 \
CS_BENCH_OWNER_PASSWORD='<same disposable password>' \
CS_BENCH_TRACE_1000='<trace id>' \
CS_BENCH_TRACE_10000='<trace id>' \
node benchmarks/web-render.mjs
```

The browser harness uses headless Chromium at 1440×1000, signs into the real app, opens URL-addressable trace routes, waits for the execution tree to commit, fails on unexpected browser errors, and reports five warm route-to-render samples per trace. The UI renders every row for a 1K-span trace and intentionally bounds the tree to 2,000 rows for a 10K-span trace; the transcript is separately bounded to 160 events. All 10,000 spans remain accessible from the API and inspector data.

## Measured result — 2026-09-27

Environment: Python 3.13.15, Linux 6.6.87.2 under WSL2, single-node Docker Compose, local loopback, synthetic spans. The run used 10,000 throughput spans in batches of 100 with concurrency 4, plus dedicated 1K- and 10K-span detail traces.

| Measurement | p50 | p95 |
| --- | ---: | ---: |
| SDK manual span scope, no exporter (20,000 iterations) | 0.029 ms | 0.093 ms |
| OTLP HTTP acknowledgement | 48.730 ms | 105.534 ms |
| Send to ClickHouse projection | 3,370.651 ms | 5,857.643 ms |
| Trace-list API, 50 rows | 25.173 ms | 32.520 ms |
| Trace-detail API, 100-span trace | 65.717 ms | 78.677 ms |
| Trace-detail API, 1,000 spans / 1.12 MB JSON | 145.438 ms | 156.202 ms |
| Trace-detail API, 10,000 spans / 11.21 MB JSON | 1,122.591 ms | 1,257.100 ms |
| Browser route-to-render, 1,000 tree rows | 422.881 ms | 462.987 ms |
| Browser route-to-render, 10,000 source spans / 2,000 bounded tree rows | 1,555.740 ms | 1,877.091 ms |
| Deterministic clustering, 2,000 failed runs / 20 clusters | 5.646 ms | 5.769 ms |

- End-to-end throughput: **1,245.94 spans/second**.
- Dedicated trace projection time: **779.735 ms** for 1K spans and **1,290.130 ms** for 10K spans.
- Storage delta: **714,056 bytes for 21,000 measured spans**, normalized to an estimated **34,002,667 bytes per million spans**. This is a sample-derived estimate, not a one-million-span run; ClickHouse part merges and attribute cardinality materially affect it.

These numbers include a development-grade single worker and synchronous trace projection. They do not establish sustained-load capacity, high availability, multi-tenant isolation, WAN performance, or production sizing. Re-run on the intended hardware and realistic attribute payloads before setting an operational target.
