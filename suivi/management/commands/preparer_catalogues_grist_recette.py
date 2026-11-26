"""Publier des catalogues fictifs reproductibles dans des documents dédiés."""
from uuid import NAMESPACE_URL, uuid5

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from suivi.services.catalogues_externes import adresse_grist, enregistrer_nom_catalogue_grist, requete_api
from suivi.services.import_sources_referentiels import lire_source
from suivi.services.publications_grist import destination_grist, publier_edition_grist
from pwa.partage_grist import empreinte, texte_json


SCENARIOS = {
    "demo": ("Démo · École des Tilleuls", ("Mésanges", "Hirondelles", "Chardonnerets")),
    "temporaire": ("Temporaire · Éditions de recette", ("Merles", "Pinsons")),
    "attention": ("Attention · Adaptations et conflits", ("Rouges-gorges", "Aigrettes")),
}


def uuid_recette(cle):
    return str(uuid5(NAMESPACE_URL, f"petits-pas/recette-grist/{cle}"))


def editions_recette(scenario):
    _, classes = SCENARIOS[scenario]
    for position, classe in enumerate(classes, start=1):
        identite = f"{scenario}-{position}"
        reference = f"grist-recette-{identite}"
        cle_competence = scenario if scenario == "attention" else identite
        libelle = "Je décris les étapes de mon activité"
        if scenario == "attention" and position == 2:
            libelle = "Je raconte dans l’ordre ce que j’ai fait"
        for edition in range(1, 3 if scenario == "temporaire" and position == 1 else 2):
            yield reference, edition, {
                "format": 2, "version": str(edition),
                "source": {
                    "identifiant": reference, "titre": f"Référentiel des {classe}",
                    "provenance": "Catalogue fictif de recette Petits Pas", "licence": "CC-BY-SA-4.0",
                    "provisoire": True,
                },
                "domaines": [{
                    "code": "LANG", "nom": "Langage",
                    "competences": [{
                        "code": "LANG1", "identite": uuid_recette(cle_competence),
                        "libelle": libelle if edition == 1 else "J’explique les étapes de mon activité",
                        "niveau": "MS",
                    }],
                }],
            }


def remplir_espace(url, nom, editions):
    prefixe, document = adresse_grist(url)
    tables = {table["id"] for table in requete_api(prefixe, document, "/tables")["tables"]}
    for table, champs in (
        ("PetitsPasEspace", ("Nom",)), ("PetitsPasClasses", ("Nom", "Empreinte")),
        ("PetitsPasContenus", ("Contenu",)),
    ):
        if table not in tables:
            requete_api(prefixe, document, "/tables", methode="POST", corps=texte_json({"tables": [{
                "id": table, "columns": [{"id": cle, "fields": {"type": "Text"}}
                                          for cle in ("Identifiant", *champs)],
            }]}).encode())

    def ecrire(table, cle, champs):
        requete_api(prefixe, document, f"/tables/{table}/records?noparse=true&onmany=none",
                    corps=texte_json({"records": [{"require": {"Identifiant": cle}, "fields": champs}]}).encode())

    ecrire("PetitsPasEspace", "espace", {"Nom": nom})
    dernieres = {reference: source for reference, _, source in editions}
    for reference, source in dernieres.items():
        identifiant = uuid_recette(reference)
        contenu = texte_json(source)
        ecrire("PetitsPasContenus", identifiant, {"Contenu": contenu})
        ecrire("PetitsPasClasses", identifiant, {"Nom": source["source"]["titre"], "Empreinte": empreinte(contenu)})


class Command(BaseCommand):
    help = "Préparer trois documents Grist fictifs dédiés à la recette des catalogues."

    def add_arguments(self, parser):
        for scenario in SCENARIOS:
            parser.add_argument(f"--{scenario}", required=True, metavar="LIEN_GRIST")
        parser.add_argument("--ecrire", action="store_true", help="Écrire dans les trois documents de recette indiqués.")

    def handle(self, *args, **options):
        try:
            documents = [adresse_grist(options[scenario])[1] for scenario in SCENARIOS]
            if len(set(documents)) != len(SCENARIOS):
                raise ValidationError("Indiquez trois documents Grist distincts.")
            for scenario, (nom, _) in SCENARIOS.items():
                url = options[scenario]
                editions = list(editions_recette(scenario))
                for _, _, source in editions:
                    lire_source(texte_json(source))
                if options["ecrire"]:
                    destination = destination_grist(url, preparer_vierge=True)
                    nom_actuel = enregistrer_nom_catalogue_grist(url, nom)
                    if nom_actuel != nom:
                        raise ValidationError(f"Un autre catalogue existe dans le document « {scenario} ».")
                    for reference, edition, source in editions:
                        publier_edition_grist(destination, reference, source["source"]["titre"], edition, source)
                    if scenario == "demo":
                        remplir_espace(url, nom, editions)
                self.stdout.write(f"{nom} · {len(editions)} éditions · {url}")
        except ValidationError as erreur:
            raise CommandError(" ".join(erreur.messages)) from erreur
        if not options["ecrire"]:
            self.stdout.write("Simulation. Ajoutez --ecrire pour publier dans ces documents de recette.")
