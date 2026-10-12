#!/usr/bin/env bash
set -euo pipefail
TASK_PROJECT=python-fiszki
TASK_REGION=europe-west4
TASK_SERVICE=python-fiszki
TASK_BUCKET=python-fiszki-users
TASK_IMAGE="${TASK_REGION}-docker.pkg.dev/${TASK_PROJECT}/cloud-run-source-deploy/madra-nauka/${TASK_SERVICE}:$(git rev-parse --short HEAD)"
gcloud builds submit --project="$TASK_PROJECT" --tag="$TASK_IMAGE" .
gcloud run deploy "$TASK_SERVICE" --project="$TASK_PROJECT" --region="$TASK_REGION" \
  --image="$TASK_IMAGE" --no-traffic --tag=madra-v2 \
  --update-env-vars="MADRA_STATE_BUCKET=${TASK_BUCKET},MADRA_STATE_PREFIX=madra-v2,MADRA_PUBLIC_URL=https://madranauka.online" \
  --max-instances=1 --min-instances=1 --concurrency=4 --memory=1Gi --cpu=1 \
  --no-cpu-throttling --timeout=3600
# Inspect the tagged revision before assigning production traffic.
