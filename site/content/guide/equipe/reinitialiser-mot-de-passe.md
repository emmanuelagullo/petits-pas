+++
title = "Réinitialiser son mot de passe"
description = "Recevoir un lien de réinitialisation sans demander un mot de passe temporaire à la direction."
fiche = true
categorie = "equipe"
publics = ["responsable", "associe", "contributeur", "direction"]
intentions = ["mot de passe oublié", "réinitialiser", "connexion", "email", "compte"]
prerequis = "Le compte possède une adresse électronique accessible et l’envoi de courriels est configuré."
depart = "Page de connexion → Mot de passe oublié ?"
statut = "disponible"
+++

## Étapes

1. Saisir l’adresse électronique associée au compte.
2. Sélectionner **Envoyer le lien de réinitialisation**.
3. Consulter sa messagerie, y compris les courriers indésirables.
4. Ouvrir le lien reçu, saisir deux fois un nouveau mot de passe d’au moins
   douze caractères puis l’enregistrer.
5. Revenir à la connexion avec ce nouveau mot de passe.

## Résultat attendu

Le nouveau mot de passe remplace l’ancien. Le lien de réinitialisation est à
usage unique et devient également invalide après expiration.

## Limites et sécurité

- La page affiche le même message que l’adresse corresponde ou non à un compte,
  afin de ne pas révéler la liste des utilisateurs.
- Si aucun courriel n’arrive, vérifier l’adresse utilisée et demander à la
  direction de confirmer l’adresse du compte ; ne pas multiplier le partage de
  liens ou de mots de passe.
- Un lien déjà utilisé ou expiré conduit à **Lien de réinitialisation
  invalide** ; demander alors un nouveau lien.
- Ce parcours change un secret d’authentification, pas les fonctions ni les
  affectations de la personne.
