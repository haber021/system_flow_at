#!/usr/bin/env bash
# Run Gunicorn with sensible defaults for multi-worker production
# Usage: WORKERS=4 THREADS=4 PORT=8000 ./run_gunicorn.sh

set -euo pipefail

: ${WORKERS:=$(($(nproc --ignore=1) * 2 + 1 2>/dev/null || echo 3))}
: ${THREADS:=4}
: ${PORT:=8000}

echo "Starting gunicorn with ${WORKERS} workers and ${THREADS} threads on 0.0.0.0:${PORT}"

exec gunicorn core.wsgi:application \
  --bind 0.0.0.0:${PORT} \
  --workers ${WORKERS} \
  --worker-class gthread \
  --threads ${THREADS} \
  --access-logfile - \
  --error-logfile -
