"""Import contrôlé d'un paquet local, sans écran ni remplacement sur le service."""
import json
from getpass import getpass
from pathlib import Path
from zipfile import BadZipFile

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError

from comptes.forms import InitialisationEcoleForm
from comptes.models import Utilisateur
from suivi.imports_ecole import verifier_zip, verifier_serveur
from suivi.models import Ecole


class Command(BaseCommand):
    help = "Vérifie un ZIP local puis, sur confirmation, crée une nouvelle école serveur."

    def add_arguments(self, parser):
        parser.add_argument('archive', type=Path)
        parser.add_argument('--travail', type=Path, required=True,
                            help="Dossier temporaire privé, hors médias/statiques et de tout chemin HTTP.")
        parser.add_argument('--confirmer', action='store_true')
        parser.add_argument('--sha256', help="Empreinte affichée lors de la vérification préalable.")
        parser.add_argument('--ecole', help="Nom obligatoire de la nouvelle école lors de l'import.")
        parser.add_argument('--commune', default='')
        parser.add_argument('--direction', help="Identifiant du compte serveur choisi explicitement.")
        parser.add_argument('--operateur', help="Compte technique actif qui réalise l'import.")
        parser.add_argument('--creer-direction', action='store_true',
                            help="Crée ce compte personnel avec un nouveau mot de passe saisi au terminal.")
        parser.add_argument('--prenom')
        parser.add_argument('--nom')

    def handle(self, *args, **options):
        try:
            verifier_serveur()
            travail = Path(options['travail']).resolve()
            from django.conf import settings
            if not Path(options['travail']).is_absolute() or not travail.is_dir():
                raise CommandError("--travail doit désigner un dossier privé existant et absolu.")
            if travail.stat().st_mode & 0o077:
                raise CommandError("Le dossier de travail doit être privé (permissions 0700).")
            for interdit in (settings.MEDIA_ROOT, settings.STATIC_ROOT, settings.BASE_DIR):
                if interdit and travail.is_relative_to(Path(interdit).resolve()):
                    raise CommandError("Le dossier de travail doit être hors du code, des médias et des statiques.")
            if options['confirmer']:
                if not all(options[c] for c in ('sha256', 'ecole', 'direction', 'operateur')):
                    raise CommandError("La confirmation exige --sha256, --ecole, --direction et --operateur.")
            elif any(options[c] for c in ('sha256', 'direction', 'operateur', 'creer_direction', 'prenom', 'nom')):
                raise CommandError("Ces options exigent --confirmer ; lancer d'abord la vérification seule.")
            with verifier_zip(options['archive'], travail) as projection:
                self.stdout.write(json.dumps(projection.rapport, ensure_ascii=False, indent=2))
                self.stdout.write("Nouvelle école uniquement ; classes en préparation ; auteurs inactifs ; aucun droit local repris.")
                if not options['confirmer']:
                    self.stdout.write("Vérification terminée. Aucune donnée du service n'a été modifiée.")
                    return
                if options['sha256'] != projection.rapport['sha256']:
                    raise CommandError("L'empreinte diffère : consulter et confirmer à nouveau le ZIP.")
                nom, commune = options['ecole'].strip(), options['commune'].strip()
                if not nom or len(nom) > 200 or len(commune) > 200:
                    raise CommandError("Nom d'école ou commune invalide.")
                if Ecole.objects.filter(nom__iexact=nom, commune__iexact=commune).exists():
                    raise CommandError("Une école de même nom et commune existe déjà : aucun remplacement.")
                operateur = Utilisateur.objects.filter(username=options['operateur'], is_active=True, is_staff=True).first()
                if operateur is None:
                    raise CommandError("L'opérateur doit être un compte technique actif.")
                if options['creer_direction']:
                    if not options['prenom'] or not options['nom']:
                        raise CommandError("--creer-direction exige --prenom et --nom.")
                    mot_de_passe = getpass("Nouveau mot de passe du compte de direction : ")
                    confirmation = getpass("Confirmer le nouveau mot de passe : ")
                    formulaire = InitialisationEcoleForm(dict(
                        ecole_nom=nom, commune=commune, username=options['direction'],
                        first_name=options['prenom'], last_name=options['nom'],
                        password1=mot_de_passe, password2=confirmation))
                    if not formulaire.is_valid():
                        raise CommandError("Compte refusé : " + str(formulaire.errors.as_text()))
                    direction = formulaire.save(commit=False)
                else:
                    if options['prenom'] or options['nom']:
                        raise CommandError("--prenom et --nom exigent --creer-direction.")
                    direction = Utilisateur.objects.filter(username=options['direction'], is_active=True).first()
                    if direction is None:
                        raise CommandError("Compte de direction actif introuvable ; utiliser --creer-direction pour en créer un.")
                ecole = projection.importer(direction, nom, commune, operateur)
                self.stdout.write(self.style.SUCCESS(
                    f"Nouvelle école créée (id {ecole.pk}) ; direction : {direction.username}. "
                    "Affecter les responsables puis activer les classes depuis l'équipe pédagogique."))
        except CommandError:
            raise
        except (ValidationError, ValueError, DatabaseError, OSError, BadZipFile,
                TypeError, KeyError, AttributeError) as erreur:
            # Ne pas imprimer une requête SQL, un chemin privé ou les secrets du ZIP.
            if isinstance(erreur, ValidationError):
                message = '; '.join(erreur.messages)
            elif isinstance(erreur, ValueError):
                message = "Structure ou contenu du ZIP invalide."
            else:
                message = "Erreur de lecture, de stockage ou de base ; import annulé."
            raise CommandError("Import refusé : " + message) from None
