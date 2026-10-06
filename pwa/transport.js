// Même budget pour la file exclusive, le démarrage et les transferts.
// Le Service Worker laisse une minute à la coque pour signaler un échec.
export const OPERATION_MS = 15 * 60 * 1000;
export function requestWorker(worker, message, {onTimeout = () => {}, timeoutMs = OPERATION_MS} = {}) {
  return new Promise((resolve, reject) => {
    const channel = new MessageChannel();
    const timer = setTimeout(() => {
      channel.port1.close();
      onTimeout();
      reject(new Error('Délai dépassé. Résultat incertain : fermez puis rouvrez Petits Pas avant de reprendre.'));
    }, timeoutMs);
    channel.port1.onmessage = event => {
      clearTimeout(timer); channel.port1.close();
      event.data.ok ? resolve(event.data.value) : reject(new Error(event.data.error));
    };
    try {
      worker.postMessage(message, [channel.port2,
        ...(message.request?.body?.buffer ? [message.request.body.buffer] : []),
        ...(message.request?.inputPort ? [message.request.inputPort] : [])]);
    } catch (error) {clearTimeout(timer); channel.port1.close(); reject(error);}
  });
}
