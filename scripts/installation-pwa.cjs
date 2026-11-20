// Parcours commun d’installation pour les deux bancs navigateur.
async function creerEcole(frame) {
  // Les anciens bundles ne proposent pas la récupération d’accès.
  const dernierRecours = frame.locator('[name="dernier_recours"]');
  const avecCle = await dernierRecours.count() > 0;
  await frame.getByRole('button', {name: /Créer (l’école et mon compte|et commencer)/}).click();
  if (!avecCle) return;

  await frame.getByRole('heading', {name: 'Votre clé de secours', exact: true}).waitFor();
  await frame.locator('#cle-secours').waitFor();
  await frame.getByRole('button', {name: 'Continuer', exact: true}).click();
}

module.exports = {creerEcole};
