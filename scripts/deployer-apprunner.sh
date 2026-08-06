#!/usr/bin/env bash
# Construit l'image, la pousse, et met le service App Runner sur cette image-là.
#
#   set -a && . ./.env && set +a && ./scripts/deployer-apprunner.sh
#
# Il faut avoir passé `preparer-aws.sh` une fois, et avoir un démon Docker. Sur
# cette machine c'est colima, et jamais Docker Desktop en même temps.
set -euo pipefail

REGION="${AWS_REGION:-eu-central-1}"
DEPOT="${FADLIE_ECR_REPO:-fadlie}"
SERVICE="${FADLIE_SERVICE_NAME:-fadlie}"
SECRET_DATAHUB="${FADLIE_SECRET_DATAHUB:-fadlie/datahub-token}"
SECRET_API="${FADLIE_SECRET_API:-fadlie/api-token}"
ROLE_ACCES="${FADLIE_ACCESS_ROLE:-fadlie-apprunner-ecr-access}"
ROLE_INSTANCE="${FADLIE_INSTANCE_ROLE:-fadlie-apprunner-instance}"

# Pas de `: "${VAR:?message}"` : bash 3.2, celui de macOS, lit l'apostrophe du
# message comme une vraie ouverture de guillemet simple, et le fichier entier
# cesse de se parser. L'erreur tombe sur une ligne sans rapport, très loin.
exiger() {
    eval "[ -n \"\${$1:-}\" ]" || {
        echo "✗ $1 doit être dans l'environnement" >&2; exit 1; }
}
exiger DATAHUB_GMS_URL

A() { command aws --region "$REGION" "$@"; }
COMPTE="$(A sts get-caller-identity --query Account --output text)"
REGISTRE="$COMPTE.dkr.ecr.$REGION.amazonaws.com"

# Une image par commit. Une étiquette mouvante rend impossible de dire, devant
# une URL qui se comporte mal, quel code elle sert.
ETIQUETTE="$(git rev-parse --short HEAD)"
if ! git diff --quiet || ! git diff --cached --quiet; then
    ETIQUETTE="$ETIQUETTE-sale"
    echo "⚠ l'arbre de travail n'est pas propre : image étiquetée $ETIQUETTE"
fi
IMAGE="$REGISTRE/$DEPOT:$ETIQUETTE"

docker info >/dev/null 2>&1 || {
    echo "✗ pas de démon Docker. colima start --cpu 2 --memory 3" >&2; exit 1; }

# linux/amd64 explicitement : la machine de développement est arm64, et une
# image d'architecture étrangère n'échoue qu'au déploiement, après la poussée,
# avec un message sur le manifeste plutôt que sur le processeur.
echo "→ construction ($ETIQUETTE, linux/amd64)"
docker build --platform linux/amd64 -t "$IMAGE" .

echo "→ connexion au registre"
A ecr get-login-password | docker login --username AWS --password-stdin "$REGISTRE" >/dev/null

echo "→ poussée"
docker push "$IMAGE" >/dev/null
echo "✓ $DEPOT:$ETIQUETTE poussé"

ARN_DATAHUB="$(A secretsmanager describe-secret --secret-id "$SECRET_DATAHUB" --query ARN --output text)"
ARN_API="$(A secretsmanager describe-secret --secret-id "$SECRET_API" --query ARN --output text)"
ARN_ACCES="$(command aws iam get-role --role-name "$ROLE_ACCES" --query Role.Arn --output text)"
ARN_INSTANCE="$(command aws iam get-role --role-name "$ROLE_INSTANCE" --query Role.Arn --output text)"

# Les deux jetons arrivent par `RuntimeEnvironmentSecrets` : App Runner les
# résout au démarrage et ils n'apparaissent ni dans l'image, ni dans la
# configuration du service, ni dans la console.
source_json() {
cat <<FIN
{
  "ImageRepository": {
    "ImageIdentifier": "$IMAGE",
    "ImageRepositoryType": "ECR",
    "ImageConfiguration": {
      "Port": "8000",
      "RuntimeEnvironmentVariables": {
        "DATAHUB_GMS_URL": "$DATAHUB_GMS_URL",
        "AWS_REGION": "$REGION",
        "FADLIE_CACHE_SECONDS": "${FADLIE_CACHE_SECONDS:-300}"
      },
      "RuntimeEnvironmentSecrets": {
        "DATAHUB_GMS_TOKEN": "$ARN_DATAHUB",
        "FADLIE_API_TOKEN": "$ARN_API"
      }
    }
  },
  "AutoDeploymentsEnabled": false,
  "AuthenticationConfiguration": {"AccessRoleArn": "$ARN_ACCES"}
}
FIN
}

# La sonde vise `/health`, qui répond sans jeton et pendant le préchauffage. Un
# intervalle large : l'analyse initiale prend quatre minutes, et une sonde
# impatiente remplacerait le service avant qu'il ait fini de réfléchir.
SANTE='{"Protocol":"HTTP","Path":"/health","Interval":20,"Timeout":5,"HealthyThreshold":1,"UnhealthyThreshold":5}'
INSTANCE="{\"Cpu\":\"1 vCPU\",\"Memory\":\"2 GB\",\"InstanceRoleArn\":\"$ARN_INSTANCE\"}"

ARN_SERVICE="$(A apprunner list-services \
    --query "ServiceSummaryList[?ServiceName=='$SERVICE'].ServiceArn | [0]" --output text)"

if [ "$ARN_SERVICE" = "None" ] || [ -z "$ARN_SERVICE" ]; then
    echo "→ création du service $SERVICE"
    ARN_SERVICE="$(A apprunner create-service --service-name "$SERVICE" \
        --source-configuration "$(source_json)" \
        --instance-configuration "$INSTANCE" \
        --health-check-configuration "$SANTE" \
        --query 'Service.ServiceArn' --output text)"
else
    echo "→ mise à jour du service $SERVICE"
    A apprunner update-service --service-arn "$ARN_SERVICE" \
        --source-configuration "$(source_json)" \
        --instance-configuration "$INSTANCE" \
        --health-check-configuration "$SANTE" >/dev/null
fi

echo "→ attente (compter cinq à dix minutes : l'image se tire, puis l'agent préchauffe)"
for _ in $(seq 1 60); do
    sleep 20
    ETAT="$(A apprunner describe-service --service-arn "$ARN_SERVICE" \
            --query 'Service.Status' --output text)"
    echo "   $ETAT"
    case "$ETAT" in
        RUNNING) break ;;
        CREATE_FAILED|DELETE_FAILED)
            echo "✗ échec — voir les journaux CloudWatch du service" >&2; exit 1 ;;
    esac
done

DOMAINE="$(A apprunner describe-service --service-arn "$ARN_SERVICE" \
          --query 'Service.ServiceUrl' --output text)"
URL="https://$DOMAINE/mcp"

echo
echo "→ sonde"
CODE_SANTE="$(curl -s -o /dev/null -w '%{http_code}' --max-time 30 "https://$DOMAINE/health")"
CODE_NU="$(curl -s -o /dev/null -w '%{http_code}' --max-time 30 -X POST "$URL")"
echo "   /health sans jeton : $CODE_SANTE  (attendu 200)"
echo "   /mcp sans jeton    : $CODE_NU  (attendu 401)"

cat <<FIN

✓ $URL   —   image $DEPOT:$ETIQUETTE

Éprouver, avec un vrai client MCP :

    FADLIE_MCP_URL=$URL python scripts/verifier-mcp.py --distant
FIN
