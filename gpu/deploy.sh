#!/usr/bin/env bash
# Build in Azure Container Registry (az acr build). Requires: az, az login.
#
# Usage:
#   ./deploy.sh --reg <acr> --sub <subscription-guid> --rg <resource-group> [--image extraction]

set -euo pipefail

REGISTRY_NAME=""
SUBSCRIPTION_ID=""
RESOURCE_GROUP=""
IMAGE_NAME="extraction"
CONTEXT="."

usage() {
  echo "Usage: $0 --reg <acr-name> --sub <subscription-id> --rg <resource-group> [--image <name>] [--context <path>]" >&2
  exit 1
}

usage_help() {
  echo "Usage: $0 --reg <acr-name> --sub <subscription-id> --rg <resource-group> [--image <name>] [--context <path>]" >&2
  exit 0
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --reg)
      [[ $# -ge 2 ]] || usage
      REGISTRY_NAME="$2"
      shift 2
      ;;
    --sub)
      [[ $# -ge 2 ]] || usage
      SUBSCRIPTION_ID="$2"
      shift 2
      ;;
    --rg)
      [[ $# -ge 2 ]] || usage
      RESOURCE_GROUP="$2"
      shift 2
      ;;
    --image)
      [[ $# -ge 2 ]] || usage
      IMAGE_NAME="$2"
      shift 2
      ;;
    --context)
      [[ $# -ge 2 ]] || usage
      CONTEXT="$2"
      shift 2
      ;;
    -h|--help)
      usage_help
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage
      ;;
  esac
done

if [[ -z "$REGISTRY_NAME" || -z "$SUBSCRIPTION_ID" || -z "$RESOURCE_GROUP" ]]; then
  echo "Required: --reg, --sub, --rg" >&2
  usage
fi

LOGIN_SERVER="${REGISTRY_NAME}.azurecr.io"
FULL_IMAGE="${LOGIN_SERVER}/${IMAGE_NAME}:latest"

echo "Subscription: ${SUBSCRIPTION_ID}"
echo "Registry:     ${LOGIN_SERVER} (RG: ${RESOURCE_GROUP})"
echo "Image:        ${FULL_IMAGE}"
echo ""

command -v az >/dev/null || { echo "Install Azure CLI: https://learn.microsoft.com/cli/azure/install-azure-cli" >&2; exit 1; }

az account set --subscription "${SUBSCRIPTION_ID}"

az acr build \
  --registry "${REGISTRY_NAME}" \
  --image "${IMAGE_NAME}:latest" \
  --file Dockerfile \
  "${CONTEXT}"

echo ""
echo "Built and pushed: ${FULL_IMAGE}"
