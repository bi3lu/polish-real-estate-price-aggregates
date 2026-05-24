#!/usr/bin/env sh
set -eu

SOURCE_CONFIG="${SOURCE_CONFIG:-/app/config/sources.local.yaml}"
INGESTION_INTERVAL_SECONDS="${INGESTION_INTERVAL_SECONDS:-3600}"
INGESTION_FAILURE_INTERVAL_SECONDS="${INGESTION_FAILURE_INTERVAL_SECONDS:-300}"
INGESTION_ON_START="${INGESTION_ON_START:-true}"
INGESTION_ARGS="${INGESTION_ARGS:-}"
RUN_SILVER_ETL="${RUN_SILVER_ETL:-true}"
RUN_GOLD_ETL="${RUN_GOLD_ETL:-false}"
RUN_PUBLIC_ETL="${RUN_PUBLIC_ETL:-false}"
MAX_FAILURES_BEFORE_EXIT="${MAX_FAILURES_BEFORE_EXIT:-0}"

failures=0
sleep_before_run=0

if [ "$INGESTION_ON_START" != "true" ]; then
    sleep_before_run="$INGESTION_INTERVAL_SECONDS"
fi

run_etl_stage() {
    stage="$1"
    enabled="$2"

    if [ "$enabled" = "true" ]; then
        echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Running ${stage} ETL"
        python -m "src.etl.${stage}"
    fi
}

while true; do
    if [ "$sleep_before_run" -gt 0 ]; then
        echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Waiting ${sleep_before_run}s before next ingestion run"
        sleep "$sleep_before_run"
    fi

    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Starting ingestion loop run"

    if python main.py --source-config "$SOURCE_CONFIG" $INGESTION_ARGS; then
        failures=0
        run_etl_stage "silver" "$RUN_SILVER_ETL"
        run_etl_stage "gold" "$RUN_GOLD_ETL"
        run_etl_stage "public" "$RUN_PUBLIC_ETL"
        echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Ingestion loop run finished"
        sleep_before_run="$INGESTION_INTERVAL_SECONDS"
        continue
    fi

    failures=$((failures + 1))
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Ingestion loop run failed (${failures})" >&2

    if [ "$MAX_FAILURES_BEFORE_EXIT" -gt 0 ] && [ "$failures" -ge "$MAX_FAILURES_BEFORE_EXIT" ]; then
        echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Exiting after ${failures} consecutive failures" >&2
        exit 1
    fi

    sleep_before_run="$INGESTION_FAILURE_INTERVAL_SECONDS"
done
