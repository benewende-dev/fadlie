#!/usr/bin/env bash
# Une fois : le dépôt d'images, les deux secrets, les deux rôles.
#
#   set -a && . ./.env && set +a && ./scripts/preparer-aws.sh
#
# Idempotent : ce qui existe est laissé tel quel. Les valeurs des secrets sont
# lues depuis l'environnement et poussées directement — elles ne s'affichent
# jamais, ni ici ni dans la console.
set -euo pipefail

REGION="${AWS_REGION:-eu-central-1}"
DEPOT="${FADLIE_ECR_REPO:-fadlie}"
SECRET_DATAHUB="${FADLIE_SECRET_DATAHUB:-fadlie/datahub-token}"
SECRET_API="${FADLIE_SECRET_API:-fadlie/api-token}"
ROLE_ACCES="${FADLIE_ACCESS_ROLE:-fadlie-apprunner-ecr-access}"
ROLE_INSTANCE="${FADLIE_INSTANCE_ROLE:-fadlie-apprunner-instance}"

# Voir `deployer-apprunner.sh` : `${VAR:?message}` avec une apostrophe dans le
# message casse le parsing sous bash 3.2. Ici ça passait par chance — deux
# apostrophes qui s'apparient. On ne laisse pas une syntaxe tenir à ça.
exiger() {
    eval "[ -n \"\${$1:-}\" ]" || {
        echo "✗ $1 doit être dans l'environnement" >&2; exit 1; }
}
exiger DATAHUB_GMS_TOKEN
exiger FADLIE_API_TOKEN

A() { command aws --region "$REGION" "$@"; }
COMPTE="$(A sts get-caller-identity --query Account --output text)"

# --- le dépôt d'images --------------------------------------------------------
A ecr describe-repositories --repository-names "$DEPOT" >/dev/null 2>&1 \
  || { A ecr create-repository --repository-name "$DEPOT" \
        --image-scanning-configuration scanOnPush=true >/dev/null
       echo "→ dépôt ECR $DEPOT créé"; }
echo "✓ dépôt ECR $DEPOT"

# --- les secrets --------------------------------------------------------------
# Deux secrets séparés, pas un seul document : le jeton DataHub ouvre l'écriture
# sur tout le catalogue, celui de l'API ouvre l'agent. Les faire tourner
# séparément doit rester possible.
poser_secret() {
    local nom="$1" valeur="$2"
    if A secretsmanager describe-secret --secret-id "$nom" >/dev/null 2>&1; then
        A secretsmanager put-secret-value --secret-id "$nom" \
            --secret-string "$valeur" >/dev/null
        echo "✓ secret $nom mis à jour"
    else
        A secretsmanager create-secret --name "$nom" --secret-string "$valeur" \
            --description "Fadlie" >/dev/null
        echo "→ secret $nom créé"
    fi
}
poser_secret "$SECRET_DATAHUB" "$DATAHUB_GMS_TOKEN"
poser_secret "$SECRET_API" "$FADLIE_API_TOKEN"

ARN_DATAHUB="$(A secretsmanager describe-secret --secret-id "$SECRET_DATAHUB" --query ARN --output text)"
ARN_API="$(A secretsmanager describe-secret --secret-id "$SECRET_API" --query ARN --output text)"

# --- rôle d'accès : App Runner tire l'image ----------------------------------
creer_role() {
    local nom="$1" principal="$2"
    command aws iam get-role --role-name "$nom" >/dev/null 2>&1 && return 0
    command aws iam create-role --role-name "$nom" \
        --assume-role-policy-document "{
          \"Version\": \"2012-10-17\",
          \"Statement\": [{
            \"Effect\": \"Allow\",
            \"Principal\": {\"Service\": \"$principal\"},
            \"Action\": \"sts:AssumeRole\"}]}" >/dev/null
    echo "→ rôle $nom créé"
}

creer_role "$ROLE_ACCES" "build.apprunner.amazonaws.com"
command aws iam attach-role-policy --role-name "$ROLE_ACCES" \
    --policy-arn arn:aws:iam::aws:policy/service-role/AWSAppRunnerServicePolicyForECRAccess \
    >/dev/null 2>&1 || true
echo "✓ rôle d'accès $ROLE_ACCES"

# --- rôle d'instance : Bedrock, et les deux secrets --------------------------
# Des droits nommés, pas `bedrock:*`. Le juge n'invoque qu'un modèle ; un rôle
# qui peut tout invoquer transforme une erreur de configuration en facture.
#
# Le modèle sous-jacent n'est pas restreint à une région, et ce n'est pas un
# relâchement : un profil d'inférence *route*. Mesuré le 6 août 2026 sur le
# service déployé — appelé en eu-central-1 par `eu.amazon.nova-micro-v1:0`, le
# refus portait sur `arn:aws:bedrock:eu-west-3::foundation-model/…`. Restreindre
# la région du modèle revient à interdire au profil de faire son travail. Ce qui
# borne la dépense, c'est le nom du modèle, et il reste unique.
creer_role "$ROLE_INSTANCE" "tasks.apprunner.amazonaws.com"
command aws iam put-role-policy --role-name "$ROLE_INSTANCE" \
    --policy-name fadlie-bedrock-et-secrets \
    --policy-document "{
      \"Version\": \"2012-10-17\",
      \"Statement\": [
        {\"Effect\": \"Allow\",
         \"Action\": [\"bedrock:InvokeModel\"],
         \"Resource\": [
           \"arn:aws:bedrock:*::foundation-model/amazon.nova-micro-v1:0\",
           \"arn:aws:bedrock:*:$COMPTE:inference-profile/eu.amazon.nova-micro-v1:0\"]},
        {\"Effect\": \"Allow\",
         \"Action\": [\"secretsmanager:GetSecretValue\"],
         \"Resource\": [\"$ARN_DATAHUB\", \"$ARN_API\"]}]}" >/dev/null
echo "✓ rôle d'instance $ROLE_INSTANCE"

cat <<FIN

Prêt. Ensuite :

    ./scripts/deployer-apprunner.sh

Le service lira les deux jetons dans Secrets Manager et invoquera Bedrock par
son rôle d'instance — aucune clé d'accès ne part dans l'image ni dans la
configuration du service.
FIN
