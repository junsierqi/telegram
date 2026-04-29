// M124: service worker for PWA-style push notifications.
// Registered by app.js on login; survives page close so the OS can wake it
// up on incoming push (real push needs PA-008 FCM/APNs subscription —
// without that, this is a noop placeholder that documents the contract).

self.addEventListener('install', (event) => { self.skipWaiting(); });

self.addEventListener('activate', (event) => { event.waitUntil(self.clients.claim()); });

self.addEventListener('push', (event) => {
  let data = { title: 'Telegram-like', body: 'New activity' };
  try {
    if (event.data) data = Object.assign(data, event.data.json());
  } catch (e) { /* fallthrough */ }
  // Icons intentionally omitted: a designer-provided asset bundle is the
  // next deliverable. Browsers fall back to the default app icon, which is
  // fine for the dev MVP. Add `badge:` / `icon:` here once /icons/* exists.
  event.waitUntil(self.registration.showNotification(data.title, {
    body: data.body,
    data: { url: data.url || '/' },
  }));
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const target = event.notification.data && event.notification.data.url || '/';
  event.waitUntil(self.clients.matchAll({ type: 'window' }).then((wins) => {
    for (const w of wins) {
      if (w.url.endsWith(target) && 'focus' in w) return w.focus();
    }
    if (self.clients.openWindow) return self.clients.openWindow(target);
  }));
});
