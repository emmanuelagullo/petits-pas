from django import template

from suivi.services.catalogues_externes import suggestions_catalogues_grist

register = template.Library()


@register.simple_tag(takes_context=True)
def catalogues_grist_suggeres(context):
    request = context.get("request")
    classe = context.get("classe") or context.get("classe_origine")
    ecole = classe.ecole if classe else context.get("ecole")
    if not request or not ecole:
        return []
    cache = getattr(request, "_suggestions_catalogues_grist", None)
    if cache is None:
        cache = request._suggestions_catalogues_grist = {}
    cle = (ecole.pk, classe.pk if classe else None)
    if cle not in cache:
        cache[cle] = suggestions_catalogues_grist(request.user, ecole, classe)
    return cache[cle]
