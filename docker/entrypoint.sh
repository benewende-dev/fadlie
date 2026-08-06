#!/bin/sh
# App Runner impose le port par la variable PORT et ne la garantit pas à 8000.
#
# `exec` n'est pas cosmétique : uvicorn devient PID 1 et reçoit SIGTERM
# lui-même. Un shell intermédiaire l'avalerait, et le conteneur serait tué au
# bout du délai de grâce à chaque redéploiement.
set -e
exec uvicorn --factory fadlie.serveur:application \
     --host 0.0.0.0 --port "${PORT:-8000}" --log-level info
