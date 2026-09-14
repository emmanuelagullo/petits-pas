#!/usr/bin/env bash
# Commande de démarrage pour Render (palier gratuit).
#
# Le disque est éphémère sur ce palier : tout redémarrage du conteneur
# (redéploiement, réveil après mise en veille) repart d'un système de
# fichiers vierge. Plutôt que de lutter contre ça pour une preuve de
# concept, ce script en profite : il reconstruit la base et la classe de
# démonstration à chaque démarrage. Sur un vrai pilote avec de vraies
# données à conserver, ce script est à jeter, pas à réparer — il faudra
# un disque persistant à la place (voir README).
set -euo pipefail

python manage.py migrate --noinput

# Idempotent par construction : sur ce palier, la base est toujours vide
# à ce stade puisqu'elle vient d'être recréée par migrate ci-dessus.
python manage.py creer_ecole "Ma Belle École" \
  --commune "Bordeaux" \
  --mdp-enseignant "${CARNET_MDP_ENSEIGNANT:-cerise-nuage-toupie}" \
  --mdp-direction "${CARNET_MDP_DIRECTION:-hibou-marelle-sirop}"

python manage.py charger_referentiel referentiel/trame-cycle1.yaml
python manage.py jeu_demo

python manage.py collectstatic --noinput

exec gunicorn carnet.wsgi:application --bind "0.0.0.0:${PORT:-8000}"
