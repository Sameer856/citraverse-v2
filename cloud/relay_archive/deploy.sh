#!/usr/bin/env bash
# Deploy only after selecting the project, Redis network and Secret Manager entries.
set -euo pipefail
if [[ $# -ne 3 ]]; then
  echo 'Usage: deploy.sh PROJECT_ID REGION SERVICE_ACCOUNT_EMAIL' >&2
  exit 2
fi
archive_bucket=${CITRA_RADAR_BUCKET:?set CITRA_RADAR_BUCKET to the actual private radar archive bucket}
if [[ ! $archive_bucket =~ ^[a-z0-9][a-z0-9._-]{1,61}[a-z0-9]$ ]]; then
  echo 'Invalid GCS archive bucket name' >&2
  exit 2
fi
project_id=$1
region=$2
service_account=$3
env_vars="CITRA_ENV=production,GCS_RADAR_BUCKET=$archive_bucket,GCS_RADAR_PREFIX=radar"
if [[ -n ${CITRA_AUDIO_BUCKET:-} ]]; then
  if [[ ! $CITRA_AUDIO_BUCKET =~ ^[a-z0-9][a-z0-9._-]{1,61}[a-z0-9]$ ]]; then
    echo 'Invalid GCS audio archive bucket name' >&2
    exit 2
  fi
  env_vars+=",GCS_AUDIO_BUCKET=$CITRA_AUDIO_BUCKET"
fi
source_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
secret_bindings='CITRA_DEVICES_JSON=citraverse-relay-devices:latest,REDIS_URL=citraverse-relay-redis-url:latest'
if [[ ${CITRA_REDIS_CUSTOM_CA:-0} == 1 ]]; then
  secret_bindings+=',/secrets/redis-ca.pem=citraverse-relay-redis-ca:latest'
fi
args=(run deploy citraverse-pcb-route --project "$project_id" --region "$region"
  --source "$source_dir" --service-account "$service_account"
  --allow-unauthenticated --no-use-http2 --timeout 3600 --concurrency 80
  --min-instances 1 --max-instances 3 --cpu 1 --memory 512Mi --no-cpu-throttling
  --update-env-vars "$env_vars"
  --update-secrets "$secret_bindings"
  --startup-probe httpGet.path=/health,httpGet.port=8080,periodSeconds=10,failureThreshold=6
  --liveness-probe httpGet.path=/health,httpGet.port=8080,periodSeconds=10,failureThreshold=3)
if [[ -n ${CITRA_NETWORK:-} || -n ${CITRA_SUBNET:-} ]]; then
  : "${CITRA_NETWORK:?set both CITRA_NETWORK and CITRA_SUBNET}"
  : "${CITRA_SUBNET:?set both CITRA_NETWORK and CITRA_SUBNET}"
  args+=(--network "$CITRA_NETWORK" --subnet "$CITRA_SUBNET" --vpc-egress private-ranges-only)
fi
gcloud "${args[@]}"
