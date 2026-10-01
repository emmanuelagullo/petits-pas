const assert = require('node:assert/strict');
const {normaliser, mots, score} = require('../suivi/static/suivi/recherche_referentiel.js');
const chercher = (texte, recherche) => score(normaliser(texte), mots(normaliser(recherche)));
assert.equal(chercher('Je reconnais mon prénom', 'prenom reconnais'), 0);
assert.equal(chercher('Je reconnais mon prénom', 'prneom'), 1);
assert.equal(chercher('Je reconnais mon prénom', 'prenom papier'), Infinity);
assert.equal(chercher('Je reconnais mon prénom', 'xyz'), Infinity);
assert.equal(chercher('Je reconnais mon prénom', ''), 0);
assert.equal(chercher('Je classe', 'chasse'), 1);
assert.equal(chercher('Je chasse', 'chasse'), 0);
console.log('Recherche locale : accents, mots multiples, fautes, inversions et refus vérifiés.');

// Vérifier les événements et la pagination sans serveur ni réseau.
const fs = require('node:fs'), vm = require('node:vm');
const element = () => ({children: [], handlers: {}, hidden: false,
  append(...items) { this.children.push(...items); },
  replaceChildren(item) { this.children = item.children; },
  addEventListener(type, handler) { this.handlers[type] = handler; }});
const form = element(); form.dataset = {lecture: 'source'};
form.elements = {q: {...element(), value: ''}, domaine: {...element(), value: ''}, niveau: {...element(), value: ''}};
const liste = element(), compteur = element(), nav = element(), avant = element(), apres = element(), position = element();
nav.querySelector = selecteur => ({'[data-precedent]': avant, '[data-suivant]': apres, '[data-position]': position})[selecteur];
const serveur = element(), aide = element();
const catalogue = Array.from({length: 61}, (_, i) => ({libelle: `Je reconnais mon prénom ${i}`, domaine: i === 60 ? 'Langage' : 'Autre', niveau: 'MS', active: true}));
const document = {
  getElementById: () => ({textContent: JSON.stringify(catalogue)}),
  createElement: element, createDocumentFragment: element,
  querySelector: selecteur => ({'[data-recherche-referentiel]': form, '[data-resultats-referentiel]': liste,
    '[data-compteur-referentiel]': compteur, '[data-pagination-locale]': nav, '[data-aide-instantanee]': aide})[selecteur],
  querySelectorAll: () => [serveur]
};
vm.runInNewContext(fs.readFileSync(require.resolve('../suivi/static/suivi/recherche_referentiel.js'), 'utf8'),
  {document, location: {href: 'https://example.test/consulter/'}, URL});
assert.equal(liste.children.length, 60);
assert.equal(position.textContent, 'Page 1 sur 2');
apres.handlers.click(); assert.equal(liste.children.length, 1);
form.elements.q.value = 'prneom'; form.elements.q.handlers.input();
assert.equal(compteur.textContent, '61 résultats.');
form.elements.domaine.value = 'Langage'; form.elements.domaine.handlers.change();
assert.equal(liste.children.length, 1); assert.equal(nav.hidden, true);
form.elements.q.value = 'introuvable'; form.elements.q.handlers.input();
assert.equal(compteur.textContent, '0 résultat.');
assert.equal(serveur.hidden, true);
console.log('Recherche locale : frappe, filtres, compteur et pagination vérifiés sans réseau.');
