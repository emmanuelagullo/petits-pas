+++
title = "Le projet"
description = "Pourquoi Petits Pas existe et comment le projet se construit."
+++

Petits Pas cherche à préserver un outil simple, durable et maîtrisable par les
équipes pédagogiques et les structures qui les accompagnent. Il couvre le
chemin qui va de l'observation quotidienne en classe au carnet individuel
partagé avec la famille.

## Pourquoi ce projet ?

Le point de départ de Petits Pas est l'annonce de l'arrêt du support
d'Iticarnet. Pour les équipes qui s'appuient sur cet outil, elle soulève une
question très concrète : comment poursuivre cet usage lorsque le service ne
peut plus évoluer ?

Cette situation n'efface en rien les services rendus par Iticarnet. Petits Pas
ne présume ni de sa réussite ni de sa longévité. Le projet part simplement
d'une hypothèse : publier librement le logiciel et documenter son déploiement
peuvent faciliter sa reprise, son adaptation et son hébergement auprès du
prestataire choisi par ses utilisateurs. [Lire la genèse du
projet]({{< relref "/projet/genese/" >}}).

## Partir des gestes de la classe

L'outil doit rester au service de pratiques pédagogiques, pas leur imposer une
administration supplémentaire. Le parcours visé tient en quelques gestes :

1. retrouver une classe, un élève ou un petit groupe ;
2. repérer un apprentissage dans le référentiel ;
3. noter une acquisition ou un apprentissage en cours ;
4. joindre, lorsque c'est utile, un commentaire ou une trace ;
5. relire les progrès et préparer un carnet compréhensible par la famille.

La [présentation destinée aux équipes pédagogiques]({{< relref "/equipes-pedagogiques/" >}})
montre ce parcours en images. Une
[démonstration publique]({{< relref "/demonstration/" >}}) permet également de
l'essayer avec des données entièrement fictives.

## Des principes simples

- **Construire avec le terrain.** Le cahier des charges doit être confronté aux
  usages réels des enseignantes, enseignants et directions d'école.
- **Rester sobre.** Une action fréquente doit demander peu d'étapes et rester
  praticable sur les équipements disponibles dans les écoles.
- **Garder la maîtrise des données.** Les photos et observations concernant les
  enfants ne doivent jamais être confondues avec les données fictives des
  démonstrations.
- **Permettre la reprise.** Le code, la documentation et les procédures de
  déploiement doivent rendre possible un changement d'hébergeur ou de
  prestataire.
- **Partager les améliorations.** Petits Pas est développé comme un bien commun
  sous licence libre.

## Où en est Petits Pas ?

Une première application fonctionnelle permet déjà de créer une école et ses
classes, charger un référentiel, suivre les acquisitions, associer des traces,
prévisualiser un carnet et produire son PDF. Une démonstration jetable et un
profil d'atelier pédagogique persistant sont distingués des futurs
déploiements utilisant des données réelles.

Cette base n'est pas encore présentée comme un service de production. Le
modèle d'habilitation, l'exploitation dans la durée, l'accessibilité, la
sécurité et le cadre de traitement des données doivent notamment être éprouvés
avant tout pilote réel. La [présentation destinée aux DSI et aux
hébergeurs]({{< relref "/dsi/" >}}) expose les choix techniques et leurs limites.

## Les prochaines étapes

Le projet avance par petits jalons vérifiables :

1. consolider le cahier des charges avec des équipes pédagogiques ;
2. éprouver le parcours quotidien de saisie et la forme des carnets ;
3. renforcer les habilitations et les garanties adaptées aux données réelles ;
4. documenter et tester le déploiement, les sauvegardes et la reprise ;
5. préparer un pilote seulement lorsque ces conditions seront réunies.

Cette feuille de route restera révisable : les retours du terrain doivent
pouvoir remettre en cause une interface ou une priorité avant qu'elle ne se
fige.

## Un développement ouvert

Le code source est publié sous licence `AGPL-3.0-or-later`. Cette licence
autorise l'étude, la modification, la redistribution et l'auto-hébergement ;
elle demande également que les utilisateurs d'une version modifiée proposée
comme service puissent accéder au code source correspondant.

La documentation publique originale est placée sous licence `CC-BY-SA-4.0`.
Le [dépôt GitLab](https://gitlab.inria.fr/petits-pas/petits-pas) permet de suivre
le développement et la page [Contribuer]({{< relref "/contribuer/" >}})
présente les premières manières de participer.
