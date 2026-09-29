from django import template
from django.templatetags.static import static
from django.urls import reverse
from django.utils.html import format_html

from suivi.presentation import illustration_effective, reglages_du_perimetre

register = template.Library()


@register.simple_tag(takes_context=True)
def icone_liste(context, competence, classe=None):
    ecole = classe.ecole if classe else competence.domaine.ecole
    # Un seul chargement des réglages pour toutes les lignes de la page,
    # y compris lorsqu'une ligne est remplacée par HTMX.
    request = context["request"]
    if not hasattr(request, "_reglages_illustrations"):
        request._reglages_illustrations = {}
    cle = (ecole.pk, classe.pk if classe else None)
    cache = request._reglages_illustrations
    if cle not in cache:
        cache[cle] = reglages_du_perimetre(ecole, classe)
    illustration = illustration_effective(ecole, competence, classe, cache[cle])
    url = (reverse("media_presentation", args=[illustration.reglage_id]) if illustration.photo
           else static(illustration.statique) if illustration.statique else "")
    if not url:
        return ""
    return format_html('<img class="icone-liste" src="{}" alt="" loading="lazy" width="32" height="32">', url)
