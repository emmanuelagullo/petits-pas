"""Phrases de passe proposées sur l'appareil local : quatre mots courants.

Une courte liste de mots français usuels, sans accent ni ambiguïté, écrite
pour ce projet (aucune liste externe, donc aucune licence à vérifier). Quatre
mots tirés au hasard parmi 256 donnent 32 bits : assez pour un mot de passe qui
protège surtout d'un accès accidentel à l'appareil, bien plus facile à retenir
qu'une suite de signes.
"""
import secrets

MOTS = tuple("""
abeille abricot agenda aigle ananas arbre argent avion bague balcon
ballon banane barque bassin bateau berger bijou biscuit blanc bleu bocal
boite bonbon bosse bouchon boule bravo brosse bruit cabane cactus cadeau
cafe cahier camion canard canne carnet carotte carte casque ceinture
cerise chaise champ chanson chapeau chat chaton chemin cheval chien ciel
cirque citron classe cloche clou cocotte colline coquille corde coton
crayon crepe cuisine dauphin dentelle dessin dimanche dragon dune eau
echelle ecole ecureuil elephant encre enfant epice escargot etage etoile
fanfare farine fenetre ferme feuille fleur flute fontaine foret
fourchette fourmi fraise fromage fusee galet gants gateau girafe glace
gomme gourde grenier grotte guitare hamac herbe hibou histoire horloge
hotte igloo ile image jardin jaune jouet journal jungle kiwi lac laine
lampe lapin lavande legume lentille lettre lierre lion livre loupe
lumiere lune lutin maison manege marche marron melon meuble miel miroir
mouche moulin mouton musique navire neige nid noisette noix nuage ocean
oeuf olive ongle orage orange ours outil page palmier panier papier
parapluie parc pate pecheur peigne peinture pelle perle perroquet piano
pinceau pingouin pirate pivoine plage plante plume poire poisson pomme
pont porte poule prairie prise prune puzzle quille radio radis raisin
rameur raquette renard rideau riviere robe rocher rose rouge route ruban
rue sable salade salon sapin savon scie seau sentier serpent sieste
singe sirop soleil sonnette sorbet soupe souris stylo sucre table
tableau tambour tapis tarte tasse tente tigre tissu tomate tortue train
tulipe vague valise velo vent verre vert village violet voile voiture
volcan wagon yaourt zebre
""".split())

NOMBRE_DE_MOTS = 4


def proposer_phrase():
    """Quatre mots séparés par des tirets, par exemple « pomme-lac-vent-jaune »."""
    return "-".join(secrets.choice(MOTS) for _ in range(NOMBRE_DE_MOTS))
