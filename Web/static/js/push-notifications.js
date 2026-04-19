/**
 * Push Notification Management
 * Handles subscription, unsubscription, and UI updates for web push notifications
 */

class PushNotificationManager {
    constructor() {
        this.serviceWorkerRegistration = null;
        this.vapidKey = null;
        this.isSupported = this.checkSupport();
    }

    /**
     * Check if push notifications are supported
     */
    checkSupport() {
        return (
            'serviceWorker' in navigator &&
            'PushManager' in window &&
            'Notification' in window
        );
    }

    /**
     * Initialize push notification system
     * Must be called after page load
     */
    async init() {
        if (!this.isSupported) {
            console.log('Push notifications not supported in this browser');
            return false;
        }

        try {
            // Get service worker registration
            const registrations = await navigator.serviceWorker.getRegistrations();
            this.serviceWorkerRegistration = registrations.find(
                reg => reg.scope === window.location.origin + '/'
            );

            if (!this.serviceWorkerRegistration) {
                console.warn('Service Worker not found, retrying...');
                // Try registering if not already done
                try {
                    this.serviceWorkerRegistration = await navigator.serviceWorker.register('/static/service-worker.js');
                } catch (err) {
                    console.error('Failed to register Service Worker:', err);
                    return false;
                }
            }

            // Fetch VAPID public key from server
            const keyResponse = await fetch('/api/push/vapid-key');
            if (keyResponse.ok) {
                const keyData = await keyResponse.json();
                this.vapidKey = keyData.vapid_key;
            } else {
                console.warn('Failed to fetch VAPID key');
                return false;
            }

            return true;
        } catch (error) {
            console.error('Failed to initialize push notifications:', error);
            return false;
        }
    }

    /**
     * Request notification permission from user
     */
    async requestPermission() {
        if (!this.isSupported) {
            console.warn('Push notifications not supported');
            return false;
        }

        if (Notification.permission === 'granted') {
            console.log('Push notifications already permitted');
            return true;
        }

        if (Notification.permission === 'denied') {
            console.warn('Push notifications have been denied by user');
            return false;
        }

        try {
            const permission = await Notification.requestPermission();
            return permission === 'granted';
        } catch (error) {
            console.error('Error requesting notification permission:', error);
            return false;
        }
    }

    /**
     * Subscribe to push notifications
     */
    async subscribe() {
        if (!this.isSupported) {
            console.error('Push notifications not supported');
            return false;
        }

        if (!this.serviceWorkerRegistration) {
            console.error('Service Worker not initialized');
            return false;
        }

        if (!this.vapidKey) {
            console.error('VAPID key not available');
            return false;
        }

        try {
            // Check if already subscribed
            const existingSubscription = await this.serviceWorkerRegistration.pushManager.getSubscription();
            if (existingSubscription) {
                console.log('Already subscribed to push notifications');
                return await this.saveSubscriptionToServer(existingSubscription);
            }

            // Request permission if needed
            const hasPermission = await this.requestPermission();
            if (!hasPermission) {
                console.warn('User denied notification permission');
                return false;
            }

            // Subscribe to push service
            const subscription = await this.serviceWorkerRegistration.pushManager.subscribe({
                userVisibleOnly: true,
                applicationServerKey: this.urlBase64ToUint8Array(this.vapidKey)
            });

            // Save subscription to server
            return await this.saveSubscriptionToServer(subscription);
        } catch (error) {
            console.error('Failed to subscribe to push notifications:', error);
            return false;
        }
    }

    /**
     * Unsubscribe from push notifications
     */
    async unsubscribe() {
        if (!this.serviceWorkerRegistration) {
            console.error('Service Worker not initialized');
            return false;
        }

        try {
            const subscription = await this.serviceWorkerRegistration.pushManager.getSubscription();
            if (!subscription) {
                console.warn('No active push subscription');
                return false;
            }

            // Remove subscription on server
            const success = await this.removeSubscriptionFromServer(subscription);

            // Unsubscribe from push service
            if (success) {
                await subscription.unsubscribe();
                return true;
            }

            return false;
        } catch (error) {
            console.error('Failed to unsubscribe from push notifications:', error);
            return false;
        }
    }

    /**
     * Check if user is subscribed to push notifications
     */
    async isSubscribed() {
        if (!this.serviceWorkerRegistration) {
            return false;
        }

        try {
            const subscription = await this.serviceWorkerRegistration.pushManager.getSubscription();
            return subscription !== null;
        } catch (error) {
            console.error('Failed to check subscription status:', error);
            return false;
        }
    }

    /**
     * Save subscription to server
     */
    async saveSubscriptionToServer(subscription) {
        try {
            const response = await fetch('/api/push/subscribe', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    subscription: subscription.toJSON()
                })
            });

            if (response.ok) {
                const data = await response.json();
                console.log('Subscription saved to server:', data.message);
                return true;
            } else {
                const error = await response.json();
                console.error('Failed to save subscription:', error.error);
                return false;
            }
        } catch (error) {
            console.error('Error communicating with server:', error);
            return false;
        }
    }

    /**
     * Remove subscription from server
     */
    async removeSubscriptionFromServer(subscription) {
        try {
            const response = await fetch('/api/push/unsubscribe', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    endpoint: subscription.endpoint
                })
            });

            if (response.ok) {
                console.log('Subscription removed from server');
                return true;
            } else {
                const error = await response.json();
                console.error('Failed to remove subscription:', error.error);
                return false;
            }
        } catch (error) {
            console.error('Error communicating with server:', error);
            return false;
        }
    }

    /**
     * Get all subscriptions for current user
     */
    async getSubscriptions() {
        try {
            const response = await fetch('/api/push/subscriptions');
            if (response.ok) {
                const data = await response.json();
                return data.subscriptions || [];
            }
            return [];
        } catch (error) {
            console.error('Error fetching subscriptions:', error);
            return [];
        }
    }

    /**
     * Send test notification (admin only)
     */
    async sendTestNotification(targetUser = null) {
        try {
            const response = await fetch('/api/push/test', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    target_user: targetUser
                })
            });

            if (response.ok) {
                const data = await response.json();
                console.log('Test notification sent:', data.message);
                return true;
            } else {
                const error = await response.json();
                console.error('Failed to send test notification:', error.error);
                return false;
            }
        } catch (error) {
            console.error('Error sending test notification:', error);
            return false;
        }
    }

    /**
     * Convert VAPID key from base64 string to Uint8Array
     * Required for subscribing to push service
     */
    urlBase64ToUint8Array(base64String) {
        const padding = '='.repeat((4 - base64String.length % 4) % 4);
        const base64 = (base64String + padding)
            .replace(/\-/g, '+')
            .replace(/_/g, '/');

        const rawData = window.atob(base64);
        const outputArray = new Uint8Array(rawData.length);

        for (let i = 0; i < rawData.length; ++i) {
            outputArray[i] = rawData.charCodeAt(i);
        }

        return outputArray;
    }
}

// Create global instance
const pushNotificationManager = new PushNotificationManager();

/**
 * Show notification subscription UI (typically in settings)
 */
function showPushNotificationSettings() {
    const container = document.getElementById('push-notification-settings');
    if (!container) return;

    if (!pushNotificationManager.isSupported) {
        container.innerHTML = '<p class="text-muted">Push-Benachrichtigungen werden in diesem Browser nicht unterstützt.</p>';
        return;
    }

    const html = `
        <div class="push-notification-settings">
            <h5>Push-Benachrichtigungen</h5>
            <p>Erhalten Sie Benachrichtigungen für wichtige Ereignisse direkt auf Ihrem Gerät.</p>
            
            <div id="push-status" style="margin: 15px 0;"></div>
            
            <button id="toggle-push-btn" class="btn btn-primary" style="margin-bottom: 10px;">
                Benachrichtigungen aktivieren
            </button>
            
            <div id="subscriptions-list" style="margin-top: 15px;"></div>
        </div>
    `;

    container.innerHTML = html;

    // Set up button handler
    const toggleBtn = document.getElementById('toggle-push-btn');
    pushNotificationManager.init().then(() => {
        updatePushStatus();
    });

    toggleBtn.addEventListener('click', togglePushNotifications);
}

/**
 * Update push notification status display
 */
async function updatePushStatus() {
    const statusDiv = document.getElementById('push-status');
    const toggleBtn = document.getElementById('toggle-push-btn');

    if (!statusDiv || !toggleBtn) return;

    const isSubscribed = await pushNotificationManager.isSubscribed();
    const permission = Notification.permission;

    let statusHtml = '<div class="alert alert-info">';

    if (isSubscribed) {
        statusHtml += '<strong>✓ Aktiv:</strong> Sie erhalten Push-Benachrichtigungen.';
        toggleBtn.textContent = 'Benachrichtigungen deaktivieren';
        toggleBtn.classList.remove('btn-primary');
        toggleBtn.classList.add('btn-danger');
    } else if (permission === 'denied') {
        statusHtml += '<strong>✗ Blockiert:</strong> Benachrichtigungen wurden abgelehnt. Bitte überprüfen Sie Ihre Browser-Einstellungen.';
        toggleBtn.disabled = true;
        toggleBtn.textContent = 'Benachrichtigungen deaktiviert';
    } else {
        statusHtml += '<strong>○ Inaktiv:</strong> Sie erhalten derzeit keine Push-Benachrichtigungen.';
        toggleBtn.textContent = 'Benachrichtigungen aktivieren';
        toggleBtn.classList.add('btn-primary');
        toggleBtn.classList.remove('btn-danger');
    }

    statusHtml += '</div>';
    statusDiv.innerHTML = statusHtml;

    // Show subscriptions list
    const subscriptionsList = document.getElementById('subscriptions-list');
    if (subscriptionsList && isSubscribed) {
        const subs = await pushNotificationManager.getSubscriptions();
        if (subs.length > 0) {
            let subsHtml = '<h6>Aktive Abos:</h6><ul class="list-group">';
            subs.forEach(sub => {
                const endpoint = new URL(sub.endpoint);
                subsHtml += `<li class="list-group-item"><small>${endpoint.hostname}</small><br><small class="text-muted">${sub.created_at}</small></li>`;
            });
            subsHtml += '</ul>';
            subscriptionsList.innerHTML = subsHtml;
        }
    }
}

/**
 * Toggle push notifications on/off
 */
async function togglePushNotifications() {
    const isSubscribed = await pushNotificationManager.isSubscribed();

    if (isSubscribed) {
        // Unsubscribe
        const success = await pushNotificationManager.unsubscribe();
        if (success) {
            showAlert('Benachrichtigungen deaktiviert', 'success');
        } else {
            showAlert('Fehler beim Deaktivieren der Benachrichtigungen', 'danger');
        }
    } else {
        // Subscribe
        const success = await pushNotificationManager.subscribe();
        if (success) {
            showAlert('Benachrichtigungen aktiviert!', 'success');
        } else {
            showAlert('Fehler beim Aktivieren der Benachrichtigungen', 'danger');
        }
    }

    // Update status display
    updatePushStatus();
}

/**
 * Show an alert message
 */
function showAlert(message, type = 'info') {
    // Try to show toast or alert
    const alertDiv = document.createElement('div');
    alertDiv.className = `alert alert-${type} alert-dismissible fade show`;
    alertDiv.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;

    // Find a good place to show the alert
    const container = document.querySelector('.container-fluid') || document.body;
    const firstElement = container.firstChild;

    if (firstElement) {
        container.insertBefore(alertDiv, firstElement);
    } else {
        container.appendChild(alertDiv);
    }

    // Auto-dismiss after 5 seconds
    setTimeout(() => {
        alertDiv.remove();
    }, 5000);
}

// Auto-initialize on page load
document.addEventListener('DOMContentLoaded', async () => {
    await pushNotificationManager.init();
});
