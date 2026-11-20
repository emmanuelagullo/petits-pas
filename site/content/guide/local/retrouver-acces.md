+++
title = "Retrouver l’accès sur cet appareil"
description = "Choisir un nouveau mot de passe avec la clé de secours, ou sans elle si l’école l’a autorisé."
fiche = true
categorie = "local"
publics = ["responsable", "associe", "contributeur", "direction"]
intentions = ["mot de passe oublié", "clé de secours", "dernier recours", "mot de passe perdu", "accès", "réinitialiser"]
prerequis = "Petits Pas fonctionne en mode local (programme ou navigateur de cet appareil) et vous avez un compte sur cette installation."
depart = "Page de connexion → Mot de passe oublié ?"
statut = "disponible"
+++

## Pourquoi une clé de secours

Sur cet appareil, Petits Pas n’envoie pas de courriel : aucun lien de
réinitialisation ne peut arriver par la messagerie. À la création de l’école, une
**clé de secours** est remise une seule fois à la personne qui installe. Elle
permet de choisir un nouveau mot de passe sans rien perdre. Elle se présente en
quatre groupes de quatre signes ; les majuscules, les espaces et les tirets ne
comptent pas.

## Avec la clé de secours

1. Sur la page de connexion, sélectionner **Mot de passe oublié ?**.
2. Saisir la clé de secours, puis deux fois un nouveau mot de passe d’au moins
   huit caractères. Un bouton propose une idée de phrase de passe (quatre mots
   courants) : **L’utiliser** la place dans les deux champs, et **afficher**
   permet de la lire.
3. Sélectionner **Choisir ce mot de passe**. Vous êtes connecté et une
   **nouvelle clé de secours** vous est remise : l’ancienne ne vaut plus.
4. Télécharger la nouvelle clé (ou la noter, ou imprimer la page), puis
   sélectionner **Continuer**.

## Sans la clé : le dernier recours

Si l’école l’a autorisé, la page **Mot de passe oublié ?** propose **Je n’ai plus ma
clé de secours**, puis **Choisir un nouveau mot de passe sans la clé**. Il suffit
de choisir son compte (il est simplement nommé quand il n’y en a qu’un) et de saisir
deux fois le nouveau mot de passe. Les données sont conservées. L’opération est
consignée dans le journal de l’école, et la direction ainsi que la personne
concernée en sont informées à leur connexion suivante.

Si le dernier recours n’est pas autorisé et que la clé est perdue, une autre
personne de la direction peut obtenir un lien (voir plus bas). Sinon, l’accès ne
peut pas être retrouvé : c’est le prix de ce choix.

## Choisir si le dernier recours est autorisé

- **À l’installation**, la case **Autoriser un dernier recours** est cochée par
  défaut. Si elle est décochée, il faut recopier la fin de la clé pour continuer :
  c’est la preuve qu’elle a bien été notée.
- **Ensuite**, la direction peut changer ce choix dans **Gérer l’école → Accès sur
  cet appareil**. Pour l’interdire, elle recopie sa clé de secours ; pour
  l’autoriser, rien d’autre n’est demandé.
- **Mon compte → Obtenir une nouvelle clé de secours** remplace la clé d’un compte,
  par exemple pour un compte créé avant cette fonction ou si la clé a été vue par
  quelqu’un d’autre.

## Aider un collègue

Quand plusieurs personnes se relaient sur l’appareil, la direction ouvre **Équipe
pédagogique**, déplie **Mot de passe de** la personne concernée et sélectionne
**Obtenir un lien de réinitialisation**. Le lien s’affiche une seule fois : il
est à lui remettre en main propre. Il expire au bout de trois jours.

## Limites et sécurité

- Les données de l’installation locale **ne sont pas chiffrées** : une personne qui
  peut ouvrir la session de l’ordinateur peut déjà lire les fichiers. Le mot de
  passe protège surtout d’un accès accidentel. C’est pourquoi le dernier recours
  est proposé par défaut sur un ordinateur personnel.
- **Sur un ordinateur partagé** avec des personnes qui ne doivent pas voir les
  carnets, décochez le dernier recours et gardez la clé hors de l’ordinateur.
- Chaque réinitialisation ferme les sessions ouvertes du compte et laisse une
  trace dans le journal de l’école ; aucune clé ni aucun mot de passe n’y figure.
- La clé de secours n’est pas incluse dans les sauvegardes ZIP : seule son
  empreinte y figure. Un ZIP ne permet pas de contourner le mot de passe.
- Le second facteur n’existe pas sur cet appareil.
