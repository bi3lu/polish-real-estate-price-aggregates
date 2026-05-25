#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd "$(dirname "$0")" && pwd)
PROJECT_ROOT=$(dirname "$SCRIPT_DIR")
STATE_DIR="${PROJECT_ROOT}/.docker"
CAFFEINATE_PID_FILE="${STATE_DIR}/ingestion-caffeinate.pid"

command_name="${1:-start}"

usage() {
    cat <<EOF
Usage: ./docker/run-ingestion.sh [start|foreground|stop|status|logs]

Commands:
  start       Start ingestion in detached Compose mode and keep macOS awake.
  foreground Run ingestion attached to the terminal under caffeinate when available.
  stop        Stop Compose services and the local keep-awake process.
  status      Show Compose status and keep-awake status.
  logs        Follow ingestion logs.

Set DISABLE_KEEP_AWAKE=true to skip macOS caffeinate management.
EOF
}

is_macos() {
    [ "$(uname -s)" = "Darwin" ]
}

has_caffeinate() {
    command -v caffeinate >/dev/null 2>&1
}

keep_awake_enabled() {
    [ "${DISABLE_KEEP_AWAKE:-false}" != "true" ] && is_macos && has_caffeinate
}

pid_is_running() {
    pid="$1"
    [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null
}

pid_is_caffeinate() {
    pid="$1"
    process_name=$(ps -p "$pid" -o comm= 2>/dev/null || true)

    case "$process_name" in
        *caffeinate)
            return 0
            ;;
        *)
            return 1
            ;;
    esac
}

read_keep_awake_pid() {
    if [ ! -f "$CAFFEINATE_PID_FILE" ]; then
        return 1
    fi

    pid=$(cat "$CAFFEINATE_PID_FILE")

    if pid_is_running "$pid" && pid_is_caffeinate "$pid"; then
        printf '%s\n' "$pid"
        return 0
    fi

    rm -f "$CAFFEINATE_PID_FILE"
    return 1
}

start_keep_awake() {
    if [ "${DISABLE_KEEP_AWAKE:-false}" = "true" ]; then
        echo "Keep-awake disabled by DISABLE_KEEP_AWAKE=true"
        return
    fi

    if ! is_macos; then
        echo "Keep-awake helper skipped: not running on macOS"
        return
    fi

    if ! has_caffeinate; then
        echo "Keep-awake helper skipped: caffeinate command not found"
        return
    fi

    if pid=$(read_keep_awake_pid); then
        echo "Keep-awake already running with PID ${pid}"
        return
    fi

    mkdir -p "$STATE_DIR"
    caffeinate -dimsu >/dev/null 2>&1 &
    pid="$!"
    printf '%s\n' "$pid" > "$CAFFEINATE_PID_FILE"
    echo "Started macOS keep-awake with PID ${pid}"
}

stop_keep_awake() {
    if ! pid=$(read_keep_awake_pid); then
        echo "Keep-awake is not running"
        return
    fi

    kill "$pid"
    rm -f "$CAFFEINATE_PID_FILE"
    echo "Stopped macOS keep-awake with PID ${pid}"
}

show_keep_awake_status() {
    if pid=$(read_keep_awake_pid); then
        echo "Keep-awake: running with PID ${pid}"
        return
    fi

    echo "Keep-awake: not running"
}

cd "$PROJECT_ROOT"

case "$command_name" in
    start)
        start_keep_awake

        if ! docker compose up -d ingestion; then
            stop_keep_awake
            exit 1
        fi

        docker compose ps ingestion
        ;;
    foreground)
        if keep_awake_enabled; then
            exec caffeinate -dimsu docker compose up ingestion
        fi

        exec docker compose up ingestion
        ;;
    stop)
        docker compose down
        stop_keep_awake
        ;;
    status)
        docker compose ps ingestion
        show_keep_awake_status
        ;;
    logs)
        exec docker compose logs -f ingestion
        ;;
    -h|--help|help)
        usage
        ;;
    *)
        usage >&2
        exit 2
        ;;
esac
