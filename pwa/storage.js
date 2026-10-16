// Façade : conserver les noms historiques des espaces Petits Pas.
import {creerStockage} from './socle/stockage.mjs';
const stockage = creerStockage({application:'petits-pas', database:'petits-pas-pwa-prototype-v1',
  repertoire:'petits-pas-prototype', base:'carnet.sqlite3', fichiers:['suivi-sauvegarde.json'], legacy:true},
  new URL('./', import.meta.url).pathname);
export const {configurerEspace, load, save, confirmedMedia, openStagedMedia, clearStagedMedia} = stockage;
