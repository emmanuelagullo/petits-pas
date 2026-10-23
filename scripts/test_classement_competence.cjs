const {test} = require('node:test');
const assert = require('node:assert/strict');
const {initialiserClassement} = require('../suivi/static/suivi/classement_competence.js');

function formulaire(selection = '11', erreur = false) {
  const option = (value, domaine) => ({value, dataset: {domaine}, cloneNode() { return option(value, domaine); }});
  const domaine = {value: '1', listeners: [], addEventListener(_, fn) { this.listeners.push(fn); }};
  const sous = {value: selection, options: [option(''), option('11', '1'), option('12', '1'), option('21', '2')],
    replaceChildren(...items) { this.options = items; }, getAttribute() { return erreur ? 'true' : null; }};
  const zone = {hidden: false}, message = {textContent: ''};
  // Ces champs doivent rester intacts lors du changement de classement.
  const photo = {files: ['réalisation fictive.jpg']}, commentaire = {value: 'Texte en cours'};
  const groupe = {dataset: {}, querySelector(selector) {
    return {'[name="domaine"]': domaine, '[name="sous_domaine"]': sous,
      '[data-selecteur-sous-domaine]': zone, '[data-message-classement]': message}[selector];
  }};
  const racine = {querySelectorAll() { return [groupe]; }};
  initialiserClassement(racine);
  return {racine, domaine, sous, zone, message, photo, commentaire,
    changer(value) { domaine.value = value; domaine.listeners.forEach(fn => fn()); }};
}

test('Préremplissage conservé, changement de domaine, absence de sous-domaines et retour', () => {
  const f = formulaire();
  assert.deepEqual(f.sous.options.map(o => o.value), ['', '11', '12']);
  assert.equal(f.sous.value, '11');
  f.changer('2');
  assert.deepEqual(f.sous.options.map(o => o.value), ['', '21']);
  assert.equal(f.sous.value, '');
  assert.match(f.message.textContent, /domaine a changé/);
  f.sous.value = '21';
  f.changer('3');
  assert.equal(f.zone.hidden, true);
  assert.equal(f.sous.disabled, true);
  assert.equal(f.sous.value, '');
  assert.match(f.message.textContent, /ne comporte pas/);
  f.changer('1');
  assert.deepEqual(f.sous.options.map(o => o.value), ['', '11', '12']);
  assert.equal(f.zone.hidden, false);
  assert.equal(f.sous.disabled, false);
  assert.deepEqual(f.photo.files, ['réalisation fictive.jpg']);
  assert.equal(f.commentaire.value, 'Texte en cours');
});

test('Sans sous-domaine et initialisation répétée après un chargement HTMX', () => {
  const f = formulaire('');
  initialiserClassement(f.racine);
  assert.equal(f.domaine.listeners.length, 1);
  assert.equal(f.sous.value, '');
  f.changer('2');
  assert.equal(f.sous.value, '');
});

test('Une erreur serveur reste visible dans un domaine sans sous-domaines', () => {
  const f = formulaire('21', true);
  f.changer('3');
  assert.equal(f.zone.hidden, false);
  assert.equal(f.sous.disabled, false);
});
