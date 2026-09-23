"""Chargement et validation de la configuration publique de démonstration."""

from pathlib import Path

import yaml


TYPES_AFFECTATION = {"responsable", "enseignant_associe", "contributeur"}
PERIODES_AFFECTATION = {"active", "temporaire", "terminee"}
PARCOURS_CAPTURE = {
    "equipe_direction",
    "classe_direction",
    "contribution",
    "classe_contribution",
    "classe_suivi",
    "collaborateurs",
    "guide",
}
ACTIONS_CAPTURE_GUIDE = {"classe", "lien", "selecteur", "titre"}


def _exiger_chaine(valeur, chemin):
    if not isinstance(valeur, str) or not valeur.strip() or "\n" in valeur:
        raise ValueError(f"Configuration de démonstration invalide : {chemin}.")


def charger_configuration_demo(chemin):
    chemin = Path(chemin)
    with chemin.open(encoding="utf-8") as fichier:
        configuration = yaml.safe_load(fichier)
    if not isinstance(configuration, dict):
        raise ValueError("Configuration de démonstration invalide : racine.")

    for cle in ("url", "ecole"):
        _exiger_chaine(configuration.get(cle), cle)

    identifiants = configuration.get("identifiants")
    if not isinstance(identifiants, dict):
        raise ValueError("Configuration de démonstration invalide : identifiants.")
    for type_compte in ("enseignant", "direction"):
        compte = identifiants.get(type_compte)
        if not isinstance(compte, dict):
            raise ValueError(
                f"Configuration de démonstration invalide : identifiants.{type_compte}."
            )
        for cle in ("utilisateur", "mot_de_passe"):
            _exiger_chaine(compte.get(cle), f"identifiants.{type_compte}.{cle}")

    classes = configuration.get("classes")
    if not isinstance(classes, dict) or not classes:
        raise ValueError("Configuration de démonstration invalide : classes.")
    for identifiant, classe in classes.items():
        _exiger_chaine(identifiant, "classes.<identifiant>")
        if not isinstance(classe, dict):
            raise ValueError(
                f"Configuration de démonstration invalide : classes.{identifiant}."
            )
        for cle in ("nom", "annee_scolaire"):
            _exiger_chaine(classe.get(cle), f"classes.{identifiant}.{cle}")

    profils = configuration.get("profils")
    if not isinstance(profils, list) or not profils:
        raise ValueError("Configuration de démonstration invalide : profils.")
    ids, utilisateurs, comptes_initiaux = set(), set(), set()
    for indice, profil in enumerate(profils):
        chemin_profil = f"profils[{indice}]"
        if not isinstance(profil, dict):
            raise ValueError(f"Configuration de démonstration invalide : {chemin_profil}.")
        for cle in (
            "id",
            "utilisateur",
            "prenom",
            "nom_famille",
            "fonction",
            "nom",
            "resume",
            "pourquoi",
        ):
            _exiger_chaine(profil.get(cle), f"{chemin_profil}.{cle}")
        if profil["id"] in ids or profil["utilisateur"] in utilisateurs:
            raise ValueError(
                f"Configuration de démonstration invalide : profil dupliqué {profil['id']}."
            )
        ids.add(profil["id"])
        utilisateurs.add(profil["utilisateur"])
        compte_initial = profil.get("compte_initial")
        if compte_initial is not None:
            if compte_initial not in {"enseignant", "direction"}:
                raise ValueError(
                    f"Configuration de démonstration invalide : {chemin_profil}.compte_initial."
                )
            comptes_initiaux.add(compte_initial)
            if profil["utilisateur"] != identifiants[compte_initial]["utilisateur"]:
                raise ValueError(
                    f"Configuration de démonstration incohérente : {chemin_profil}.utilisateur."
                )
        for cle in ("peut", "ne_peut_pas"):
            valeurs = profil.get(cle)
            if not isinstance(valeurs, list) or not valeurs:
                raise ValueError(
                    f"Configuration de démonstration invalide : {chemin_profil}.{cle}."
                )
            for sous_indice, valeur in enumerate(valeurs):
                _exiger_chaine(valeur, f"{chemin_profil}.{cle}[{sous_indice}]")
        affectations = profil.get("affectations")
        if not isinstance(affectations, list):
            raise ValueError(
                f"Configuration de démonstration invalide : {chemin_profil}.affectations."
            )
        for sous_indice, affectation in enumerate(affectations):
            chemin_affectation = f"{chemin_profil}.affectations[{sous_indice}]"
            if not isinstance(affectation, dict):
                raise ValueError(
                    f"Configuration de démonstration invalide : {chemin_affectation}."
                )
            if affectation.get("classe") not in classes:
                raise ValueError(
                    f"Configuration de démonstration invalide : {chemin_affectation}.classe."
                )
            if affectation.get("type") not in TYPES_AFFECTATION:
                raise ValueError(
                    f"Configuration de démonstration invalide : {chemin_affectation}.type."
                )
            periode = affectation.get("periode")
            if periode not in PERIODES_AFFECTATION:
                raise ValueError(
                    f"Configuration de démonstration invalide : {chemin_affectation}.periode."
                )
            if periode == "temporaire" and not isinstance(
                affectation.get("duree_jours"), int
            ):
                raise ValueError(
                    f"Configuration de démonstration invalide : {chemin_affectation}.duree_jours."
                )
            if periode == "terminee" and not all(
                isinstance(affectation.get(cle), int)
                for cle in ("debut_jours_avant", "fin_jours_avant")
            ):
                raise ValueError(
                    f"Configuration de démonstration invalide : {chemin_affectation}.dates."
                )
    if comptes_initiaux != {"enseignant", "direction"}:
        raise ValueError(
            "Configuration de démonstration invalide : comptes initiaux incomplets."
        )

    scenarios = configuration.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        raise ValueError("Configuration de démonstration invalide : scenarios.")
    ids_scenarios, captures = set(), set()
    for indice, scenario in enumerate(scenarios):
        chemin_scenario = f"scenarios[{indice}]"
        if not isinstance(scenario, dict):
            raise ValueError(
                f"Configuration de démonstration invalide : {chemin_scenario}."
            )
        for cle in ("id", "profil", "parcours", "capture", "titre", "legende"):
            _exiger_chaine(scenario.get(cle), f"{chemin_scenario}.{cle}")
        if scenario["id"] in ids_scenarios or scenario["capture"] in captures:
            raise ValueError(
                f"Configuration de démonstration invalide : scénario dupliqué {scenario['id']}."
            )
        ids_scenarios.add(scenario["id"])
        captures.add(scenario["capture"])
        if scenario["profil"] not in ids:
            raise ValueError(
                f"Configuration de démonstration invalide : {chemin_scenario}.profil."
            )
        if scenario["parcours"] not in PARCOURS_CAPTURE:
            raise ValueError(
                f"Configuration de démonstration invalide : {chemin_scenario}.parcours."
            )
        capture = Path(scenario["capture"])
        if capture.is_absolute() or ".." in capture.parts or capture.suffix != ".png":
            raise ValueError(
                f"Configuration de démonstration invalide : {chemin_scenario}.capture."
            )
        capture_mobile = scenario.get("capture_mobile")
        if capture_mobile is not None:
            _exiger_chaine(capture_mobile, f"{chemin_scenario}.capture_mobile")
            chemin_mobile = Path(capture_mobile)
            if (
                chemin_mobile.is_absolute()
                or ".." in chemin_mobile.parts
                or chemin_mobile.suffix != ".png"
                or capture_mobile in captures
            ):
                raise ValueError(
                    "Configuration de démonstration invalide : "
                    f"{chemin_scenario}.capture_mobile."
                )
            captures.add(capture_mobile)
        cible = scenario.get("cible")
        if cible is not None:
            _exiger_chaine(cible, f"{chemin_scenario}.cible")
            if not cible.startswith("#"):
                raise ValueError(
                    f"Configuration de démonstration invalide : {chemin_scenario}.cible."
                )
        classe = scenario.get("classe")
        if classe is not None and classe not in classes:
            raise ValueError(
                f"Configuration de démonstration invalide : {chemin_scenario}.classe."
            )
        etapes = scenario.get("etapes")
        if scenario["parcours"] == "guide":
            if not isinstance(etapes, list) or not etapes:
                raise ValueError(
                    f"Configuration de démonstration invalide : {chemin_scenario}.etapes."
                )
            for sous_indice, etape in enumerate(etapes):
                chemin_etape = f"{chemin_scenario}.etapes[{sous_indice}]"
                if not isinstance(etape, dict):
                    raise ValueError(
                        f"Configuration de démonstration invalide : {chemin_etape}."
                    )
                action = etape.get("action")
                if action not in ACTIONS_CAPTURE_GUIDE:
                    raise ValueError(
                        f"Configuration de démonstration invalide : {chemin_etape}.action."
                    )
                if action == "classe":
                    if etape.get("classe") not in classes:
                        raise ValueError(
                            f"Configuration de démonstration invalide : {chemin_etape}.classe."
                        )
                elif action in {"lien", "titre"}:
                    _exiger_chaine(etape.get("nom"), f"{chemin_etape}.nom")
                else:
                    _exiger_chaine(
                        etape.get("selecteur"), f"{chemin_etape}.selecteur"
                    )
        elif etapes is not None:
            raise ValueError(
                f"Configuration de démonstration invalide : {chemin_scenario}.etapes."
            )
    return configuration
