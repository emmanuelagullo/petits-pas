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

1. Sur la page de connexion, sélectionner **Mot de passe oublié ?**, puis saisir
   l’adresse électronique associée au compte.
2. Sélectionner **Envoyer le lien de réinitialisation**.
3. Consulter sa messagerie, y compris les courriers indésirables.
4. Ouvrir le lien reçu, saisir deux fois un nouveau mot de passe d’au moins
   douze caractères puis sélectionner **Enregistrer le mot de passe**.
5. Sélectionner **Se connecter** et utiliser ce nouveau mot de passe.

## Résultat attendu

Le nouveau mot de passe remplace l’ancien. **Toutes les sessions ouvertes avec
l’ancien mot de passe sont fermées**, y compris sur d’autres appareils : c’est
utile si l’on soupçonne qu’une autre personne a eu accès au compte. Le lien de
réinitialisation est à usage unique et expire au bout de trois jours.

## Limites et sécurité

- La page affiche le même message que l’adresse corresponde ou non à un compte,
  afin de ne pas révéler la liste des utilisateurs.
- Si aucun courriel n’arrive, vérifier l’adresse utilisée et demander à la
  direction de confirmer l’adresse du compte ; ne pas multiplier le partage de
  liens ou de mots de passe.
- Un lien déjà utilisé ou expiré conduit à **Lien de réinitialisation
  invalide** ; demander alors un nouveau lien.
- Le nombre de demandes est limité : au-delà de quelques demandes par heure
  depuis une même adresse, la page indique « Trop de demandes de
  réinitialisation depuis cette adresse » ; patienter avant de réessayer.
- Si l’installation n’envoie pas de courriels, la page l’indique (« La
  réinitialisation par courriel n’est pas disponible sur cette installation ») et
  renvoie vers la direction de l’école.
- Réinitialiser son mot de passe ne supprime pas le
  [second facteur]({{< relref "/guide/equipe/second-facteur/" >}}) : le code
  reste demandé à la connexion.
- Ce parcours change un secret d’authentification, pas les fonctions ni les
  affectations de la personne.

Pour changer son mot de passe en étant connecté, sans l’avoir oublié, voir
[Changer son mot de passe]({{< relref "changer-mot-de-passe.md" >}}).
