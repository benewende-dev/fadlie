#!/usr/bin/env bash
# Monte l'instance qui héberge DataHub Core, et rien d'autre.
#
# Pourquoi une machine distante alors que DataHub s'installe en local : le
# démarrage rapide lève **quatorze conteneurs** et la documentation exige 8 Go de
# mémoire. C'est toute la mémoire du poste de travail. La règle du projet est
# explicite là-dessus — jamais Docker et autre chose en même temps — et un gel
# complet du Mac a déjà été vécu.
#
# Pourquoi Core plutôt que l'essai Cloud : l'essai refuse les adresses gratuites,
# et il dure 21 jours. Les soumissions ferment le 10 août, la notation court
# après — l'instance mourrait pendant le jugement, avec l'URL de démonstration
# dessus. Le serveur MCP de DataHub parle aux deux de la même façon.
#
#   ./scripts/preparer-ec2.sh            # crée ce qui manque, ne touche pas au reste
#   ./scripts/preparer-ec2.sh --etat     # dit seulement où on en est
set -euo pipefail

REGION="${AWS_REGION:-eu-central-1}"
NOM="fadlie-datahub"
TYPE="${FADLIE_INSTANCE_TYPE:-t3.large}"     # 2 vCPU, 8 Go : le minimum documenté
DISQUE=40                                    # 13 Go exigés ; les images en prennent plus
CLE="$HOME/.ssh/fadlie-datahub.pem"

aws() { command aws --region "$REGION" "$@"; }

etat() {
  local ligne
  ligne=$(aws ec2 describe-instances \
        --filters "Name=tag:Name,Values=$NOM" "Name=instance-state-name,Values=pending,running,stopped" \
        --query 'Reservations[0].Instances[0].[InstanceId,State.Name,PublicIpAddress]' \
        --output text 2>/dev/null || true)
  # Sans résultat, `--output text` écrit « None » — pas une chaîne vide. Une
  # absence qui ressemble à une valeur : on exige donc la forme d'un identifiant
  # plutôt que de tester le vide, sinon le script croit l'instance déjà créée et
  # s'arrête en affichant None.
  case "$ligne" in
    i-*) echo "$ligne"; return 0 ;;
    *)   return 1 ;;
  esac
}

if [ "${1:-}" = "--etat" ]; then etat; exit $?; fi

# --- adresse d'où l'on se connecte -------------------------------------------
# Le pare-feu n'ouvre rien au monde : ni SSH, ni l'interface DataHub. Une
# instance DataHub ouverte porte le catalogue entier d'une organisation ; c'est
# précisément le genre de chose qu'on ne laisse pas traîner sur une adresse
# publique parce que c'était plus rapide.
#
# Piège mesuré le 5 août 2026 : `checkip` répond l'adresse par laquelle sort le
# **HTTPS**. Le SSH sortait par une autre — 160.155.240.163 contre 102.210.16.87.
# Le fournisseur répartit sa traduction d'adresses selon le port. Verrouiller sur
# le seul /32 rendu par checkip donne donc un pare-feu qui a l'air juste et
# refuse la connexion, sans que rien ne dise laquelle des deux adresses compte.
# On ouvre les deux : le /32 observé, et le /24 du bloc d'où sort le SSH, parce
# qu'une adresse tirée d'un pool tourne.
MOI="$(curl -fsS https://checkip.amazonaws.com | tr -d '\n')/32"
BLOC="${FADLIE_BLOC_SSH:-102.210.16.0/24}"
echo "→ ouverture réservée à $MOI et $BLOC"

# --- image Ubuntu 22.04 -------------------------------------------------------
# Prise dans le paramètre SSM public plutôt que par un identifiant écrit en dur :
# un AMI est propre à une région et change à chaque publication.
AMI=$(aws ssm get-parameter \
      --name /aws/service/canonical/ubuntu/server/22.04/stable/current/amd64/hvm/ebs-gp2/ami-id \
      --query 'Parameter.Value' --output text)
echo "→ image $AMI"

# --- clé SSH ------------------------------------------------------------------
if [ ! -f "$CLE" ]; then
  aws ec2 delete-key-pair --key-name "$NOM" >/dev/null 2>&1 || true
  aws ec2 create-key-pair --key-name "$NOM" \
      --query 'KeyMaterial' --output text > "$CLE"
  chmod 600 "$CLE"
  echo "→ clé écrite dans $CLE"
else
  echo "→ clé déjà là : $CLE"
fi

# --- groupe de sécurité -------------------------------------------------------
VPC=$(aws ec2 describe-vpcs --filters Name=isDefault,Values=true \
      --query 'Vpcs[0].VpcId' --output text)
SG=$(aws ec2 describe-security-groups --filters "Name=group-name,Values=$NOM" \
     --query 'SecurityGroups[0].GroupId' --output text 2>/dev/null || echo None)
if [ "$SG" = "None" ] || [ -z "$SG" ]; then
  SG=$(aws ec2 create-security-group --group-name "$NOM" --vpc-id "$VPC" \
       --description "Fadlie : DataHub Core, ouvert au seul poste de travail" \
       --query 'GroupId' --output text)
  echo "→ groupe $SG créé"
fi
# Seul le SSH est exposé. L'interface DataHub (9002) reste fermée et se joint par
# un tunnel : une instance DataHub porte le catalogue entier d'une organisation,
# et l'ouvrir « le temps de regarder » est exactement comme ça qu'on l'oublie
# ouverte.
for cidr in "$MOI" "$BLOC"; do
  aws ec2 authorize-security-group-ingress --group-id "$SG" \
      --protocol tcp --port 22 --cidr "$cidr" >/dev/null 2>&1 \
    && echo "→ 22 ouvert à $cidr" \
    || echo "→ 22 : $cidr déjà autorisé"
done

# --- l'instance ---------------------------------------------------------------
if etat >/dev/null 2>&1; then
  echo "→ instance déjà là :"; etat; exit 0
fi

AMORCE=$(cat "$(dirname "$0")/amorce-datahub.sh" | base64)
ID=$(aws ec2 run-instances \
      --image-id "$AMI" --instance-type "$TYPE" \
      --key-name "$NOM" --security-group-ids "$SG" \
      --block-device-mappings "DeviceName=/dev/sda1,Ebs={VolumeSize=$DISQUE,VolumeType=gp3}" \
      --user-data "$AMORCE" \
      --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=$NOM},{Key=Projet,Value=fadlie}]" \
      --query 'Instances[0].InstanceId' --output text)
echo "→ instance $ID en démarrage"
aws ec2 wait instance-running --instance-ids "$ID"
IP=$(aws ec2 describe-instances --instance-ids "$ID" \
     --query 'Reservations[0].Instances[0].PublicIpAddress' --output text)

cat <<FIN

✓ $ID  —  $IP

DataHub s'installe tout seul (compter dix à quinze minutes : quatorze images à
tirer). Pour regarder :

    ssh -i $CLE ubuntu@$IP 'tail -f /var/log/fadlie-install.log'

Puis l'interface, par un tunnel — le port n'est pas exposé :

    ssh -i $CLE -L 9002:localhost:9002 ubuntu@$IP
    open http://localhost:9002        # datahub / datahub

Éteindre le soir, rallumer le matin (le disque et l'adresse privée restent) :

    aws ec2 stop-instances  --region $REGION --instance-ids $ID
    aws ec2 start-instances --region $REGION --instance-ids $ID
FIN
