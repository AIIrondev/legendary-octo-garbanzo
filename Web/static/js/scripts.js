/**
 * Copyright 2025-2026 AIIrondev
 *
 * Licensed under the Inventarsystem EULA (Endbenutzer-Lizenzvertrag).
 * See Legal/LICENSE for the full license text.
 * Unauthorized commercial use, SaaS hosting, or removal of branding is prohibited.
 * For commercial licensing inquiries: https://github.com/AIIrondev
 */
chatBox = document.getElementById('chatBox');

function fetchMessages() {
    fetch('/messages')
        .then(response => response.json())
        .then(data => {
            chatBox.innerHTML = '';
            data.messages.forEach(msg => {
                const messageElement = document.createElement('div');
                messageElement.textContent = msg;
                chatBox.appendChild(messageElement);
            });
        });
}

setInterval(fetchMessages, 1000);