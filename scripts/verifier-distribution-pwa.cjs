#!/usr/bin/env node
// Démarrage des octets distribués, sans protocole de test et sans données réelles.
const fs = require('node:fs'), path = require('node:path'), http = require('node:http');
const assert = require('node:assert/strict');
const {createRequire} = require('node:module');
const requirePwa = createRequire(path.resolve(__dirname, '../pwa/package.json'));
const {chromium} = process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES ? require(path.join(process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES, 'playwright')) : requirePwa('playwright');
const root = path.resolve(__dirname, '../dist/pwa');
const config = JSON.parse(fs.readFileSync(path.join(root, 'config.json')));
assert.equal(config.testMode, false);
const types = {'.html':'text/html','.js':'text/javascript','.mjs':'text/javascript','.json':'application/json','.wasm':'application/wasm','.css':'text/css'};
const network = [];
const server = http.createServer((req,res)=>{
 const name = new URL(req.url,'http://localhost').pathname;
 network.push(name);
 const file = path.resolve(root, '.' + (name === '/' ? '/index.html' : name));
 if (!file.startsWith(root + path.sep)) {res.writeHead(403).end();return;}
 try {res.setHeader('Content-Type',types[path.extname(file)]||'application/octet-stream');res.end(fs.readFileSync(file));} catch {res.writeHead(404).end();}
});
let browser;
(async()=>{
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 browser = await chromium.launch({headless:true,...(process.env.PWA_CHROMIUM ? {executablePath:process.env.PWA_CHROMIUM} : {}),args:['--no-sandbox']});
 const page = await browser.newPage();
 await page.goto('http://127.0.0.1:' + server.address().port + '/');
 await page.frameLocator('#app').locator('[name="ecole_nom"]').waitFor({timeout:180000});
 assert.equal(await page.evaluate(()=>!!window.pwaTest),false);
 assert.equal(await page.locator('#version').textContent(),'Version ' + config.application_version);
 assert(!network.some(name=>name.startsWith('/app/')));
 // Même application après coupure réseau, dans ce profil fictif.
 await page.context().setOffline(true); await page.reload();
 await page.frameLocator('#app').locator('[name="ecole_nom"]').waitFor({timeout:180000});
 fs.writeFileSync(path.resolve(root,'../resultats-distribution-pwa.json'),JSON.stringify([{test:'Distribution : démarrage, version, sans hooks de test, routes locales et réouverture hors ligne',bundle:config.version,commit:config.commit}],null,2)+'\n');
 console.log('OK Distribution PWA : démarrage et réouverture hors ligne.');
})().catch(error=>{console.error(error);process.exitCode=1;}).finally(async()=>{await browser?.close();server.close();});
