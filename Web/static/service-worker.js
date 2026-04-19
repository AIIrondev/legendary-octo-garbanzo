/**
 * Service Worker for Web Push Notifications
 * Handles incoming push events and displays notifications
 */

const CACHE_NAME = 'inventarsystem-v1';
const ASSETS_TO_CACHE = [
    '/',
    '/static/css/styles.css',
    '/static/js/scripts.js',
    '/offline.html'
];

// Install event - cache assets
self.addEventListener('install', (event) => {
    console.log('[Service Worker] Installing...');
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) => {
            return cache.addAll(ASSETS_TO_CACHE).catch((err) => {
                console.warn('[Service Worker] Cache add error:', err);
                // Don't fail the installation
                return Promise.resolve();
            });
        })
    );
    self.skipWaiting();
});

// Activate event - clean up old caches
self.addEventListener('activate', (event) => {
    console.log('[Service Worker] Activating...');
    event.waitUntil(
        caches.keys().then((cacheNames) => {
            return Promise.all(
                cacheNames.map((cacheName) => {
                    if (cacheName !== CACHE_NAME) {
                        console.log('[Service Worker] Deleting old cache:', cacheName);
                        return caches.delete(cacheName);
                    }
                })
            );
        })
    );
    self.clients.claim();
});

// Push event - handle incoming push notifications
self.addEventListener('push', (event) => {
    console.log('[Service Worker] Push notification received');
    
    let notificationData = {
        title: 'Inventarsystem',
        body: 'Neue Benachrichtigung',
        icon: '/static/img/logo-192x192.png',
        badge: '/static/img/badge-72x72.png',
        tag: 'inventarsystem-notification',
        requireInteraction: false,
    };

    // Parse the push event data if available
    if (event.data) {
        try {
            const data = event.data.json();
            notificationData = {
                title: data.title || notificationData.title,
                body: data.message || data.body || notificationData.body,
                icon: data.icon || notificationData.icon,
                badge: data.badge || notificationData.badge,
                tag: data.tag || notificationData.tag,
                requireInteraction: data.requireInteraction || false,
                data: {
                    url: data.url || '/',
                    reference: data.reference || null,
                    type: data.type || 'info',
                },
            };
            console.log('[Service Worker] Push data parsed:', notificationData);
        } catch (err) {
            console.error('[Service Worker] Failed to parse push data:', err);
            notificationData.body = event.data.text();
        }
    }

    event.waitUntil(
        self.registration.showNotification(notificationData.title, {
            body: notificationData.body,
            icon: notificationData.icon,
            badge: notificationData.badge,
            tag: notificationData.tag,
            requireInteraction: notificationData.requireInteraction,
            data: notificationData.data,
            actions: [
                {
                    action: 'open',
                    title: 'Öffnen',
                    icon: '/static/img/open-icon.png'
                },
                {
                    action: 'close',
                    title: 'Schließen',
                    icon: '/static/img/close-icon.png'
                }
            ],
        })
    );
});

// Notification click event - handle user clicks on notifications
self.addEventListener('notificationclick', (event) => {
    console.log('[Service Worker] Notification clicked:', event.action);
    event.notification.close();

    const urlToOpen = event.notification.data.url || '/';

    event.waitUntil(
        clients.matchAll({
            type: 'window',
            includeUncontrolled: true
        }).then((windowClients) => {
            // Check if the app is already open
            for (let i = 0; i < windowClients.length; i++) {
                const client = windowClients[i];
                if (client.url === urlToOpen && 'focus' in client) {
                    return client.focus();
                }
            }
            // If not open, open a new window
            if (clients.openWindow) {
                return clients.openWindow(urlToOpen);
            }
        })
    );
});

// Notification close event - track when users dismiss notifications
self.addEventListener('notificationclose', (event) => {
    console.log('[Service Worker] Notification closed');
    // Could send analytics here
});

// Background fetch event (optional, for large data syncs)
self.addEventListener('sync', (event) => {
    console.log('[Service Worker] Background sync triggered:', event.tag);
    if (event.tag === 'sync-notifications') {
        event.waitUntil(
            fetch('/api/notifications/sync').then((response) => {
                console.log('[Service Worker] Notifications synced');
            })
        );
    }
});

// Fetch event - serve cached content when offline
self.addEventListener('fetch', (event) => {
    // Skip non-GET requests
    if (event.request.method !== 'GET') {
        return;
    }

    // Skip API calls - always use network
    if (event.request.url.includes('/api/')) {
        return;
    }

    event.respondWith(
        caches.match(event.request).then((response) => {
            if (response) {
                return response;
            }
            return fetch(event.request).then((response) => {
                // Cache successful responses
                if (response && response.status === 200) {
                    const responseToCache = response.clone();
                    caches.open(CACHE_NAME).then((cache) => {
                        cache.put(event.request, responseToCache);
                    });
                }
                return response;
            }).catch(() => {
                // Return offline page
                return caches.match('/offline.html');
            });
        })
    );
});
