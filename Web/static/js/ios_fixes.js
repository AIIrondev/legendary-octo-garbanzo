/**
 * Copyright 2025-2026 AIIrondev
 *
 * Licensed under the Inventarsystem EULA (Endbenutzer-Lizenzvertrag).
 * See Legal/LICENSE for the full license text.
 * Unauthorized commercial use, SaaS hosting, or removal of branding is prohibited.
 * For commercial licensing inquiries: https://github.com/AIIrondev
 */

// Initialize when document is loaded
document.addEventListener('DOMContentLoaded', function() {
    if (isIOSDevice()) {
        console.log('iOS device detected, applying iOS-specific enhancements');
        applyIOSFixes();
    }
});

// Apply all iOS-specific fixes
function applyIOSFixes() {
    // Fix file input issues
    fixIOSFileInputs();
    
    // Fix form submission
    fixIOSFormSubmission();
    
    // Fix image handling
    fixIOSImageHandling();
    
    // Fix duplication
    fixIOSDuplication();
    
    // Apply CSS fixes
    applyIOSCSSFixes();
}

// Fix iOS file input issues
function fixIOSFileInputs() {
    // Find all file inputs
    const fileInputs = document.querySelectorAll('input[type="file"]');
    
    fileInputs.forEach(input => {
        // Create a touch-friendly wrapper
        const wrapper = document.createElement('div');
        wrapper.className = 'ios-file-input-wrapper';
        wrapper.style.position = 'relative';
        
        // Style the original input to be more touch-friendly
        input.style.padding = '20px 0';
        
        // Wrap the input
        if (input.parentNode) {
            input.parentNode.insertBefore(wrapper, input);
            wrapper.appendChild(input);
            
            // Add a visible button for better touch target
            const fakeButton = document.createElement('div');
            fakeButton.className = 'ios-file-button';
            fakeButton.textContent = 'Wählen Sie Bilder/Videos aus';
            fakeButton.style.display = 'inline-block';
            fakeButton.style.padding = '10px 15px';
            fakeButton.style.backgroundColor = '#4CAF50';
            fakeButton.style.color = 'white';
            fakeButton.style.borderRadius = '4px';
            fakeButton.style.textAlign = 'center';
            fakeButton.style.margin = '10px 0';
            fakeButton.style.fontWeight = 'bold';
            wrapper.appendChild(fakeButton);
            
            // Make sure the real input covers the fake button
            input.style.position = 'absolute';
            input.style.top = '0';
            input.style.left = '0';
            input.style.width = '100%';
            input.style.height = '100%';
            input.style.opacity = '0';
            input.style.zIndex = '10';
        }
        
        // Add custom event handling
        input.addEventListener('change', function() {
            // Update visual feedback
            const fileCount = this.files ? this.files.length : 0;
            let fileText = fakeButton.textContent;
            
            if (fileCount > 0) {
                fileText = `${fileCount} Datei${fileCount !== 1 ? 'en' : ''} ausgewählt`;
                fakeButton.style.backgroundColor = '#2E7D32';
            } else {
                fileText = 'Wählen Sie Bilder/Videos aus';
                fakeButton.style.backgroundColor = '#4CAF50';
            }
            
            fakeButton.textContent = fileText;
        });
    });
}

// Fix iOS form submission issues
function fixIOSFormSubmission() {
    // Find upload forms
    const uploadForms = document.querySelectorAll('form[action*="upload_item"]');
    
    uploadForms.forEach(form => {
        // Add an iOS submission handler
        form.addEventListener('submit', function(e) {
            // Only intercept on iOS
            if (!isIOSDevice()) return;
            
            e.preventDefault();
            
            // Show that we're processing
            const loadingMessage = document.createElement('div');
            loadingMessage.className = 'ios-loading-message';
            loadingMessage.textContent = 'Wird verarbeitet...';
            loadingMessage.style.padding = '10px';
            loadingMessage.style.backgroundColor = '#f0f0f0';
            loadingMessage.style.borderRadius = '5px';
            loadingMessage.style.margin = '10px 0';
            loadingMessage.style.textAlign = 'center';
            form.appendChild(loadingMessage);
            
            // Disable the submit button
            const submitButton = form.querySelector('button[type="submit"]');
            if (submitButton) {
                submitButton.disabled = true;
            }
            
            // Use timeout to allow UI to update before heavy processing
            setTimeout(() => {
                // Gather form data with special handling for iOS
                const formData = new FormData(form);
                
                // Add iOS flag
                formData.append('is_ios', 'true');
                
                // Submit with fetch API which works better on iOS
                fetch(form.action, {
                    method: 'POST',
                    body: formData,
                    credentials: 'same-origin'
                })
                .then(response => response.json())
                .then(data => {
                    // Remove loading message
                    if (loadingMessage.parentNode) {
                        loadingMessage.parentNode.removeChild(loadingMessage);
                    }
                    
                    // Re-enable submit button
                    if (submitButton) {
                        submitButton.disabled = false;
                    }
                    
                    if (data.success) {
                        // Show success and redirect
                        alert(data.message || 'Element erfolgreich hinzugefügt');
                        
                        // Redirect to the appropriate page
                        if (data.itemId) {
                            window.location.href = `/home_admin?highlight_item=${data.itemId}`;
                        } else {
                            window.location.href = '/home_admin';
                        }
                    } else {
                        // Show error
                        alert(data.message || 'Ein Fehler ist aufgetreten');
                    }
                })
                .catch(error => {
                    console.error('iOS form submission error:', error);
                    
                    // Remove loading message
                    if (loadingMessage.parentNode) {
                        loadingMessage.parentNode.removeChild(loadingMessage);
                    }
                    
                    // Re-enable submit button
                    if (submitButton) {
                        submitButton.disabled = false;
                    }
                    
                    // Show error
                    alert('Ein Netzwerkfehler ist aufgetreten. Bitte versuchen Sie es erneut.');
                });
            }, 100);
        });
    });
}

// Fix iOS image handling issues
function fixIOSImageHandling() {
    // Reduce image preview quality on iOS
    if (typeof ImagePreviewGenerator !== 'undefined') {
        // Override the compression quality for iOS
        const originalCompressImage = ImagePreviewGenerator.prototype._compressImage;
        
        if (originalCompressImage) {
            ImagePreviewGenerator.prototype._compressImage = function(dataUrl) {
                // Lower quality for iOS
                this.quality = 0.5;
                this.maxWidth = 600;
                this.maxHeight = 600;
                
                return originalCompressImage.call(this, dataUrl);
            };
        }
    }
    
    // Fix image preview display
    document.querySelectorAll('.image-preview-container').forEach(container => {
        // Add iOS-specific styling
        container.style.webkitOverflowScrolling = 'touch';
        container.style.maxHeight = '150px';
        container.style.overflow = 'auto';
    });
}

// Fix iOS duplication issues
function fixIOSDuplication() {
    // Override duplicateItem function
    if (typeof duplicateItem !== 'undefined') {
        const originalDuplicateItem = duplicateItem;
        
        duplicateItem = function(itemId) {
            // Use localStorage on iOS instead of sessionStorage
            const useFunction = originalDuplicateItem;
            
            useFunction(itemId);
            
            // Additional iOS-specific handling
            const checkForSessionData = setInterval(() => {
                const sessionData = sessionStorage.getItem('duplicateItemData');
                if (sessionData) {
                    // Copy from sessionStorage to localStorage
                    try {
                        localStorage.setItem('duplicateItemData', sessionData);
                        localStorage.setItem('duplicateItemTimestamp', Date.now().toString());
                        console.log('Copied duplicate data to localStorage for iOS reliability');
                    } catch (e) {
                        console.warn('Failed to copy to localStorage:', e);
                    }
                    
                    clearInterval(checkForSessionData);
                }
            }, 100);
            
            // Clear interval after 3 seconds regardless
            setTimeout(() => clearInterval(checkForSessionData), 3000);
        };
    }
    
    // Fix prefill function
    if (typeof prefillFormWithDuplicateData !== 'undefined') {
        const originalPrefill = prefillFormWithDuplicateData;
        
        prefillFormWithDuplicateData = function() {
            // Try to get data from localStorage first
            let data = null;
            try {
                const localData = localStorage.getItem('duplicateItemData');
                if (localData) {
                    data = JSON.parse(localData);
                    localStorage.removeItem('duplicateItemData');
                    localStorage.removeItem('duplicateItemTimestamp');
                    console.log('Using duplicate data from localStorage');
                }
            } catch (e) {
                console.warn('Error accessing localStorage:', e);
            }
            
            // If we got data from localStorage, manually populate the form
            if (data) {
                console.log('Manually populating form with iOS optimization');
                
                // Basic fields
                document.getElementById('name').value = data.name || '';
                document.getElementById('beschreibung').value = data.description || '';
                
                // Handle filters with a delay
                setTimeout(() => {
                    // Filter 1
                    if (data.filter1 && Array.isArray(data.filter1)) {
                        data.filter1.forEach((val, idx) => {
                            const field = document.getElementById(`filter1-${idx+1}`);
                            if (field && val) field.value = val;
                        });
                    }
                    
                    // Filter 2
                    if (data.filter2 && Array.isArray(data.filter2)) {
                        data.filter2.forEach((val, idx) => {
                            const field = document.getElementById(`filter2-${idx+1}`);
                            if (field && val) field.value = val;
                        });
                    }
                    
                    // Filter 3
                    if (data.filter3 && Array.isArray(data.filter3)) {
                        data.filter3.forEach((val, idx) => {
                            const field = document.getElementById(`filter3-${idx+1}`);
                            if (field && val) field.value = val;
                        });
                    }
                }, 300);
                
                // Location
                setTimeout(() => {
                    const location = document.getElementById('ort');
                    if (location && data.location) location.value = data.location;
                }, 400);
                
                // Year and cost
                const year = document.getElementById('anschaffungsjahr');
                if (year && data.year) year.value = data.year;
                
                const cost = document.getElementById('anschaffungskosten');
                if (cost && data.cost) cost.value = data.cost;
                
                // Handle images - limited for iOS
                const form = document.querySelector('form');
                if (form && data.images && Array.isArray(data.images)) {
                    // Add hidden field to indicate duplication
                    const isDuplicatingField = document.createElement('input');
                    isDuplicatingField.type = 'hidden';
                    isDuplicatingField.name = 'is_duplicating';
                    isDuplicatingField.value = 'true';
                    form.appendChild(isDuplicatingField);
                    
                    // Only use first 3 images on iOS for performance
                    const limitedImages = data.images.slice(0, 3);
                    
                    limitedImages.forEach(imageName => {
                        const imageField = document.createElement('input');
                        imageField.type = 'hidden';
                        imageField.name = 'duplicate_images';
                        imageField.value = imageName;
                        form.appendChild(imageField);
                    });
                    
                    // Add a message about limited images
                    if (data.images.length > 3) {
                        const messageDiv = document.createElement('div');
                        messageDiv.style.margin = '10px 0';
                        messageDiv.style.padding = '10px';
                        messageDiv.style.backgroundColor = '#fff3cd';
                        messageDiv.style.borderRadius = '5px';
                        messageDiv.style.color = '#856404';
                        messageDiv.textContent = `Aus Leistungsgründen werden nur ${limitedImages.length} von ${data.images.length} Bildern verwendet`;
                        
                        const fileInput = document.getElementById('images');
                        if (fileInput && fileInput.parentNode) {
                            fileInput.parentNode.appendChild(messageDiv);
                        } else {
                            form.appendChild(messageDiv);
                        }
                    }
                }
            } else {
                // Use original function as fallback
                originalPrefill();
            }
        };
    }
}

// Apply iOS-specific CSS fixes
function applyIOSCSSFixes() {
    // Create a style element
    const style = document.createElement('style');
    style.textContent = `
        /* Improve touch targets for iOS */
        button, select, input[type="submit"], .ausleihen, .edit-button, 
        .delete-button, .duplicate-button, .details-button {
            min-height: 44px !important;
            padding: 10px 15px !important;
        }
        
        /* Improve scrolling on iOS */
        .items-container, .filter-options, .modal-content {
            -webkit-overflow-scrolling: touch !important;
        }
        
        /* Prevent zoom on inputs */
        input, select, textarea {
            font-size: 16px !important;
        }
        
        /* Fix iOS image display */
        .item-image {
            -webkit-transform: translateZ(0);
        }
        
        /* Improve form fields on iOS */
        .form-group {
            margin-bottom: 15px !important;
        }
    `;
    
    document.head.appendChild(style);
}
