# Temporary Observation Window: Scrape -> Enrich -> Score

## Purpose

Run the LinkedIn pipeline every 4 hours for a short observation period to evaluate:

- scraper throughput and duplicate rate,
- enrichment coverage and stability,
- scoring throughput and relevance output quality,
- queue/worker health under repeated execution.

## Observation Window

- Start: 2026-02-20 (UTC)
- Duration: 2 to 3 days (temporary)
- Cadence: every 4 hours

## Current Scheduler (UTC)

- Scrape: minute `00`, every 4 hours
- Enrichment backup: minute `20`, every 4 hours
- Scoring backup: minute `40`, every 4 hours

These backup schedules complement task chaining already in place:

1. `scrape_linkedin_profile_set` queues enrichment for scraped job ids.
2. `enrich_unstructured_jobs_task` queues scoring when enrichments were created.

## Manual Full-Cycle Run (Baseline)

Manual run executed to confirm end-to-end behavior before observation:

- Scrape task id: `91cebcfb-614b-48be-a57f-e9a24ed9858e`
- Scrape summary:
  - profiles processed: 5
  - scraped: 25
  - created: 8
  - duplicates: 12
  - failed: 5
- Batch scoring task id: `9d612274-5015-4855-8732-0f63a94743ca`
- Batch scoring summary:
  - status: success
  - scored: 31
  - failed: 0

Post-run snapshot for newly scraped job ids `86-93`:

- enrichment rows: 7
- scored rows: 8

## What To Watch Each Cycle

1. Scrape results
   - `scraped`, `created`, `duplicates`, `failed`
2. Enrichment results
   - `enriched`, `missing`, `failed`
3. Scoring results
   - `scored`, `failed`
4. Runtime quality
   - average task duration, retry count, and queue lag
5. API behavior
   - `/api/v1/jobs?sort=relevance` returns scored jobs

## Metrics and Logs

- Worker metrics endpoint: `http://localhost:9101/metrics`
- Prometheus scrape config: `monitoring/prometheus/prometheus.yml`
- Dashboards:
  - `monitoring/grafana/dashboards/scraper-metrics.json`
  - `monitoring/grafana/dashboards/ai-scoring-metrics.json`

### Multi-Platform Monitoring Note

For LinkedIn, Seek, and Indeed monitoring, use these panels in `scraper-metrics.json`:

- `Scraped Jobs Share by Platform (24h)` for platform distribution,
- `Scraper Success Rate by Platform` for per-platform success trends,
- `Per-Platform Scraped Throughput (LinkedIn/Seek/Indeed)` for hourly volume.

## Exit Criteria (End of Temporary Window)

- At least 6 successful full cycles across the window.
- No persistent retry loops.
- Stable scoring success and acceptable enrichment coverage.
- Confirm final cadence decision (keep every 4h or revert to daily).
