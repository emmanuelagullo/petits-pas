"""Composition publique des accueils ; aucune configuration de transport ici.

Les instructions essentielles voyagent avec le code. Le Guide public est
évolutif : il n'est pas une documentation figée de la version déployée.
"""
from urllib.parse import urlsplit

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from comptes.models import AffectationClasse

GUIDE = "https://petits-pas.gitlabpages.inria.fr/petits-pas/guide/"
PARCOURS = {
    "direction": "service/preparer-ecole/",
    "invitation": "service/premiers-pas/",
    "import": "service/importer-zip/",
}
PREMIERS_PAS = {
    AffectationClasse.RESPONSABLE: (
        "Ouvrez votre classe, puis Gérer les enfants pour vérifier l’effectif. "
        "Ouvrez un élève, choisissez + à droite d’une compétence, écrivez une "
        "observation et sélectionnez Ajouter la trace. Vous pouvez aussi décider "
        "des acquisitions et préparer les carnets."
    ),
    AffectationClasse.ENSEIGNANT_ASSOCIE: (
        "Ouvrez votre classe puis un élève. Choisissez + à droite d’une compétence, "
        "écrivez une observation et sélectionnez Ajouter la trace. Vous pouvez "
        "consulter le suivi ; les décisions d’acquisition et les carnets finaux "
        "restent au responsable."
    ),
    AffectationClasse.CONTRIBUTEUR: (
        "Ouvrez votre classe puis un élève actif : la page Ajouter une contribution "
        "pour cet élève s’ouvre. Choisissez une compétence. Écrivez une observation et sélectionnez Ajouter la trace. "
        "Cette fonction n’ouvre pas le suivi pédagogique complet ni les carnets."
    ),
}


def composer_accueil(*, ecole, lien, destinataire, compte=None, invitation=None,
                     preattributions=None, mode_test=False, apres_import=False):
    """Construit texte et HTML depuis les mêmes paragraphes, sans envoyer."""
    origine = urlsplit(lien)
    connexion = f"{origine.scheme}://{origine.netloc}" + reverse("connexion")
    if compte is not None:
        sujet = "Votre premier compte Petits Pas"
        debut = (
            f"Bonjour {compte.get_full_name()},\n\nVotre compte personnel "
            f"{compte.username} ({destinataire}) est préparé pour {ecole.nom}. "
            "Vous avez les droits de gestion de l’école : équipe, classes, élèves "
            "et réglages. Ils ne donnent pas automatiquement accès aux observations "
            "et aux carnets : une fonction dans chaque classe est nécessaire."
        )
        action = "Choisir mon mot de passe"
        paragraphes = [
            "1. Ouvrez le lien ci-dessus, renseignez deux fois votre mot de passe "
            "personnel, puis sélectionnez Enregistrer le mot de passe.",
            f"2. Sélectionnez Se connecter, puis Entrer avec le nom d’utilisateur "
            f"{compte.username} et ce mot de passe. Connexion : {connexion}",
            f"Le lien est à usage unique et valable {settings.PASSWORD_RESET_TIMEOUT // 3600} "
            "heure(s). S’il a expiré ou déjà servi, utilisez Mot de passe oublié ? "
            "sur la page de connexion avec l’adresse ci-dessus. Si vous avez déjà "
            "choisi votre mot de passe pour ce compte, connectez-vous directement. "
            "Si vous possédez un autre compte, demandez à la direction de vérifier "
            "le compte à utiliser ; ce lien ne rattache pas un compte existant.",
            "3. Dans Gérer l’école → Référentiels de l’école, choisissez ou validez les "
            "propositions pour l’année avec Voir les conséquences puis Enregistrer "
            "ces choix pour l’année. La trame de départ est prête ; choisir une autre "
            "proposition reste facultatif. Si une offre "
            "manque, consultez Pourquoi un référentiel manque-t-il ? Les classes "
            "déjà préparées gardent leur base.",
            "4. Dans Gérer l’école → Créer une classe, créez les classes en préparation. "
            "Utiliser le référentiel proposé par l’école est sélectionné par défaut : "
            "la base sera prête à la création, sans confirmation séparée. "
            "Puis, dans Équipe pédagogique → Inviter une personne, invitez l’équipe. "
            "Attribuez "
            "ensuite un Responsable de classe à chaque classe dans Équipe pédagogique "
            "→ Ajouter une personne à cette classe → Attribuer ; attendez son "
            "acceptation si vous avez préparé sa fonction dans une invitation. "
            "Revenez à Gérer l’école → Activer la classe et confirmez.",
            "5. Le responsable peut vérifier le référentiel de sa classe et ajouter "
            "les élèves. Vous pouvez aussi préparer l’effectif. Pour votre propre "
            "classe, attribuez-vous explicitement la fonction Responsable de classe "
            "avant de l’activer, puis ouvrez Gérer les enfants. Pour déléguer la "
            "gestion de l’école, accordez séparément les droits de gestion à un "
            "membre après son acceptation.",
        ]
        parcours = "direction"
        if apres_import:
            sujet = "Votre compte Petits Pas après le transfert de l’école"
            debut += (
                " L’école a été créée sur ce service à partir d’une copie ZIP. "
                "Les mots de passe et les droits de la copie locale ne sont pas repris."
            )
            paragraphes[3:] = [
                "3. Les classes, élèves et données transférés sont déjà présents. "
                "Les classes non archivées sont en préparation. Les noms des auteurs "
                "restent dans l’historique, avec des comptes inactifs ; ils ne "
                "donnent pas accès au service. Ne recréez pas les classes ni les élèves transférés.",
                "4. Dans Équipe pédagogique → Inviter une personne, invitez les "
                "collègues. Attribuez ensuite un Responsable de classe à chaque "
                "classe dans Équipe pédagogique → Ajouter une personne à cette "
                "classe → Attribuer ; attendez son acceptation si vous avez préparé "
                "sa fonction dans une invitation. Revenez à Gérer l’école → Activer "
                "la classe et confirmez. Pour votre propre classe, attribuez-vous "
                "explicitement la fonction Responsable de classe.",
                "5. Le responsable vérifie l’effectif et le référentiel de sa classe "
                "avant de reprendre les saisies. Les classes closes restent closes. "
                "Les copies locale et serveur évoluent indépendamment : aucune "
                "saisie ultérieure dans la copie locale n’est synchronisée ici. "
                "Les nouveaux choix de bases suivent les règles du service.",
            ]
            parcours = "import"
    else:
        sujet = f"Invitation à rejoindre {ecole.nom} sur Petits Pas"
        debut = f"Bonjour,\n\n{ecole.nom} vous invite à rejoindre Petits Pas avec l’adresse {destinataire}."
        action = "Rejoindre l’école"
        expiration = timezone.localtime(invitation.expire_le).strftime("%d/%m/%Y à %H:%M %Z")
        paragraphes = [
            "1. Ouvrez le lien ci-dessus. Sans compte pour cette adresse, choisissez "
            "votre nom d’utilisateur et votre mot de passe, renseignez votre identité, "
            "puis sélectionnez Créer mon compte et rejoindre l’école. Si un compte "
            "existe pour cette adresse, saisissez ses identifiants et sélectionnez "
            "Accepter l’invitation : vous gardez le même compte.",
            f"2. Sélectionnez Revenir à la connexion, puis Entrer avec vos identifiants. "
            f"Connexion : {connexion}\nEn cas d’oubli, utilisez Mot de passe oublié ? "
            "avec l’adresse de votre compte, puis revenez au lien d’invitation.",
            f"Ce lien est à usage unique et expire le {expiration}. S’il n’est plus "
            "utilisable et que vous n’avez pas rejoint l’école, demandez une nouvelle "
            "invitation à la direction. Ne communiquez pas votre mot de passe.",
        ]
        aujourd_hui = timezone.localdate()
        fonctions = list(preattributions) if preattributions is not None else list(
            invitation.affectations_classes.filter(
                appartenance__isnull=True, etat=AffectationClasse.ACTIVE,
            ).select_related("classe").order_by("classe__annee_scolaire", "classe__nom", "pk")
        )
        fonctions = [f for f in fonctions if not f.date_fin or f.date_fin >= aujourd_hui]
        if fonctions:
            lignes = ["Fonctions préparées au moment de cet envoi :"]
            for fonction in fonctions:
                dates = f"à partir du {fonction.date_debut:%d/%m/%Y}"
                if fonction.date_fin:
                    dates += f", jusqu’au {fonction.date_fin:%d/%m/%Y} inclus"
                historique = " ; accès historique attribué" if fonction.acces_historique else ""
                lignes.append(f"• {fonction.get_type_display()} — {fonction.classe.libelle_avec_annee}, {dates}{historique}.")
            paragraphes.append("\n".join(lignes))
            for type_fonction in dict.fromkeys(f.type for f in fonctions):
                paragraphes.append(PREMIERS_PAS[type_fonction])
            paragraphes.append(
                "Ces étapes sont accessibles pendant les dates de votre fonction, "
                "une fois la classe activée (ou avec un accès historique attribué). "
                "Si la classe n’apparaît pas, contactez la direction."
            )
        else:
            paragraphes.append(
                "Aucune fonction de classe n’est préparée à cet envoi. Accepter vous "
                "rend membre de l’école ; cette appartenance seule n’ouvre pas "
                "l’application pédagogique. Demandez à la direction une fonction "
                "dans votre classe, ou les droits de gestion si c’est votre mission. "
                "Vous pourrez ensuite vous connecter selon les droits attribués."
            )
        paragraphes.append(
            "Les fonctions peuvent changer entre cet envoi et votre acceptation. "
            "Une fonction retirée, suspendue ou terminée n’ouvre aucun droit ; une "
            "fonction future attend sa date de début. L’application vérifie toujours "
            "vos droits actuels. L’invitation ne donne pas les droits de direction."
        )
        parcours = "invitation"
    paragraphes.extend([
        "Si un second facteur est demandé à la connexion, suivez les instructions "
        "pour le configurer avant de poursuivre.",
        f"Parcours détaillé : {GUIDE}{PARCOURS[parcours]}\n"
        f"Instructions pour Petits Pas {settings.VERSION_APPLICATION}. Le Guide en "
        "ligne évolue et peut décrire une version plus récente. En cas de différence, "
        "suivez les étapes de ce courriel et demandez conseil à la direction.",
    ])
    contexte = {"debut": debut, "action": action, "lien": lien,
                "paragraphes": paragraphes, "sujet": sujet, "mode_test": mode_test}
    message = EmailMultiAlternatives(
        subject=("[TEST] " if mode_test else "") + sujet, to=[destinataire],
        body=render_to_string("suivi/emails/accueil_compte.txt", contexte),
    )
    message.attach_alternative(
        render_to_string("suivi/emails/accueil_compte.html", contexte), "text/html"
    )
    return message
