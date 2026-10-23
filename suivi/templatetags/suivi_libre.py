from django import template
register = template.Library()


@register.simple_tag
def groupes_suivi(domaine, lignes):
    groupes = {None: []}
    noms = {None: ""}
    for s in getattr(domaine, "sous_domaines_lus", []):
        groupes[s.pk] = []
        noms[s.pk] = s.nom
    for ligne in lignes:
        c = ligne[0] if isinstance(ligne, tuple) else ligne
        cle = c.sous_domaine_id
        groupes.setdefault(cle, []).append(ligne)
        if cle not in noms:
            noms[cle] = c.sous_domaine.nom if c.sous_domaine else ""
    return [(cle, noms[cle], valeurs) for cle, valeurs in groupes.items()]
