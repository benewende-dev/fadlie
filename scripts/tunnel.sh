#!/usr/bin/env bash
# Ouvre (ou ré-ouvre) le tunnel vers DataHub.
#
# Le port 9002 n'est pas exposé et ne le sera pas : une instance DataHub porte le
# catalogue entier d'une organisation. On passe donc par SSH.
#
# `ServerAliveInterval` n'est pas une coquetterie : sans lui le tunnel tombe en
# silence dès que la liaison reste inactive quelques minutes, et le symptôme —
# `ConnectionResetError` au milieu d'une mesure — ressemble à une panne de
# DataHub. Mesuré deux fois le 6 août 2026.
#
#   ./scripts/tunnel.sh          # ouvre s'il n'est pas déjà là
#   ./scripts/tunnel.sh --etat   # dit seulement si ça répond
set -euo pipefail

CLE="${FADLIE_CLE_SSH:-$HOME/.ssh/fadlie-datahub.pem}"
HOTE="${FADLIE_HOTE:-}"
REGION="${AWS_REGION:-eu-central-1}"

repond() { curl -s -o /dev/null --max-time 5 "http://localhost:8080/config"; }

if [ "${1:-}" = "--etat" ]; then
  repond && echo "→ DataHub répond sur localhost:8080" || echo "→ pas de réponse"
  exit 0
fi

if repond; then echo "→ tunnel déjà ouvert"; exit 0; fi

if [ -z "$HOTE" ]; then
  HOTE=$(command aws ec2 describe-instances --region "$REGION" \
         --filters "Name=tag:Name,Values=fadlie-datahub" \
                   "Name=instance-state-name,Values=running" \
         --query 'Reservations[0].Instances[0].PublicIpAddress' --output text)
  case "$HOTE" in
    None|"") echo "instance éteinte ou absente — la démarrer d'abord" >&2; exit 1 ;;
  esac
fi

pkill -f "ssh -f -N .*9002:localhost:9002" 2>/dev/null || true
ssh -f -N -o ExitOnForwardFailure=yes -o StrictHostKeyChecking=accept-new \
    -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -o TCPKeepAlive=yes \
    -i "$CLE" -L 9002:localhost:9002 -L 8080:localhost:8080 "ubuntu@$HOTE"

for _ in 1 2 3 4 5; do
  repond && { echo "→ tunnel ouvert vers $HOTE  (interface : http://localhost:9002)"; exit 0; }
  sleep 2
done
echo "tunnel ouvert mais DataHub ne répond pas — regarder les conteneurs" >&2
exit 1
