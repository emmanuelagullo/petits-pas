// Garder le formulaire visible : le 403 peut arriver sur une action HTMX.
document.addEventListener('htmx:responseError', event => {
  const xhr = event.detail.xhr;
  if (xhr.status !== 403 || xhr.getResponseHeader('X-Petits-Pas-Refus') !== 'csrf') return;
  const page = new DOMParser().parseFromString(xhr.responseText, 'text/html');
  const aide = page.querySelector('#reprise-csrf');
  if (!aide) return;
  document.querySelector('#reprise-csrf')?.remove();
  const action = event.detail.elt;
  const formulaire = action?.closest('form');
  const point = formulaire || action;
  if (point?.isConnected && point !== document.body) point.before(aide);
  else document.body.prepend(aide);
  aide.focus();
});
