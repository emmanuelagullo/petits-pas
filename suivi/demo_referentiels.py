"""Scénario des référentiels, réservé à la génération de l'équipe fictive."""
from django.conf import settings

from suivi.models import AdoptionReferentiel, Competence
from suivi.referentiels import contenu_origine
from suivi.services.reprise_referentiels import reprendre
from suivi.services.import_sources_referentiels import importer_source
from suivi.services.choix_bases_referentiels import publier_choix_application
from suivi.services.ajouts_referentiels import creer_ajout, reprendre_ajout
from suivi.services.adaptations_referentiels import enregistrer_adaptation
from suivi.services.correspondances_referentiels import relier_competences


def preparer_referentiels(ecole, classes, utilisateurs):
    # Après génération des observations : leur année inconnue n'est pas devinée.
    reprendre(ecole.pk)
    annee = classes["coccinelles"].annee_scolaire
    version, _, _ = importer_source(
        (settings.BASE_DIR / "referentiel/exemples/source-fictive.yaml").read_text(encoding="utf-8")
    )
    deux, _, _ = importer_source(
        (settings.BASE_DIR / "referentiel/exemples/source-fictive-v2.yaml").read_text(encoding="utf-8")
    )
    publier_choix_application(annee=annee, versions_ids=[version.pk, deux.pk],
        proposee_id=version.pk, revision_attendue=0)
    # L'autorisation ne change pas la base déjà utilisée par les classes.
    classe = classes["coccinelles"]
    adoption = AdoptionReferentiel.objects.get(classe=classe, courante=True)
    domaine_id = contenu_origine(adoption)["domaines"][0]["id"]
    commun = dict(ecole=ecole, annee=annee, domaine_id=domaine_id, niveau="PS")
    ajout = creer_ajout(utilisateur=utilisateurs["remi"], classe=classe,
        adoption_attendue=adoption.pk, libelle="Je raconte une découverte au groupe", **commun)
    masquer = creer_ajout(utilisateur=utilisateurs["remi"], classe=classe,
        adoption_attendue=adoption.pk, libelle="Je présente un objet de notre boîte à histoires", **commun)
    enregistrer_adaptation(utilisateur=utilisateurs["remi"], ecole=ecole, annee=annee,
        classe=classe, adoption_attendue=adoption.pk, competence=masquer.competence,
        libelle=None, visible=False, revision_attendue=0)
    ecole_ajout = creer_ajout(utilisateur=utilisateurs["diane"],
        libelle="Je prends soin du jardin de l’école", **commun)
    reprendre_ajout(utilisateur=utilisateurs["remi"], ecole=ecole, annee=annee,
        classe=classe, locale=ecole_ajout, adoption_attendue=adoption.pk)
    cible = contenu_origine(adoption)["competences"][0]
    enregistrer_adaptation(utilisateur=utilisateurs["diane"], ecole=ecole, annee=annee,
        competence=Competence.objects.get(pk=cible["id"]),
        libelle=cible["libelle"][:260] + " (proposition fictive de l’école)",
        visible=None, revision_attendue=0)
    relier_competences(utilisateur=utilisateurs["remi"], ecole=ecole, annee=annee,
        classe=classe, adoption_attendue=adoption.pk,
        reference_depart=f"ajout:{ajout.pk}", reference_arrivee=f"base:{adoption.version_id}:{cible['id']}",
        type_lien="lien", justification="Exemple fictif de rapprochement à discuter en équipe ; aucun acquis n’est transféré.")
