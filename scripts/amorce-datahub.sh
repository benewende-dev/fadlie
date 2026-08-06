#!/usr/bin/env bash
# Exécuté une seule fois par cloud-init, au premier démarrage de l'instance.
# Tout ce qu'il fait est journalisé dans /var/log/fadlie-install.log, parce
# qu'une installation qui échoue en silence sur une machine sans écran coûte une
# heure à diagnostiquer.
set -euxo pipefail
exec > >(tee -a /var/log/fadlie-install.log) 2>&1

echo "=== $(date -Is) — installation DataHub Core ==="

export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y ca-certificates curl gnupg python3-pip python3-venv jq

# Docker, dépôt officiel : celui d'Ubuntu 22.04 est trop ancien pour le plugin
# compose v2, dont le démarrage rapide de DataHub a besoin.
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
  | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg
echo "deb [arch=amd64 signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" \
  > /etc/apt/sources.list.d/docker.list
apt-get update -y
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
usermod -aG docker ubuntu

# 2 Go d'échange. La documentation les demande explicitement à côté des 8 Go de
# mémoire : sans eux, OpenSearch et Kafka se font tuer par le noyau au moment où
# tout démarre en même temps, et le symptôme est un conteneur qui « redémarre »
# sans jamais dire pourquoi.
fallocate -l 2G /swapfile
chmod 600 /swapfile
mkswap /swapfile
swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab

# OpenSearch refuse de démarrer sous la valeur par défaut d'Ubuntu.
sysctl -w vm.max_map_count=262144
echo 'vm.max_map_count=262144' >> /etc/sysctl.conf

# Le CLI DataHub, dans son propre environnement : le python système d'Ubuntu est
# géré par apt, et pip s'y plaint à juste titre.
python3 -m venv /opt/datahub
/opt/datahub/bin/pip install --upgrade pip wheel
/opt/datahub/bin/pip install 'acryl-datahub[datahub-rest]'
ln -sf /opt/datahub/bin/datahub /usr/local/bin/datahub

echo "=== $(date -Is) — démarrage rapide (quatorze conteneurs, patience) ==="
sudo -u ubuntu -H /opt/datahub/bin/datahub docker quickstart

echo "=== $(date -Is) — terminé ==="
docker ps --format 'table {{.Names}}\t{{.Status}}'
echo "interface sur le port 9002, identifiants datahub / datahub"
