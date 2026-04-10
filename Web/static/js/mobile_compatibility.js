/**
 * Copyright 2025-2026 AIIrondev
 *
 * Licensed under the Inventarsystem EULA (Endbenutzer-Lizenzvertrag).
 * See Legal/LICENSE for the full license text.
 * Unauthorized commercial use, SaaS hosting, or removal of branding is prohibited.
 * For commercial licensing inquiries: https://github.com/AIIrondev
 */

// Detect mobile devices including tablets
function isMobileDevice() {
    return /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);
}

// Specifically detect iOS devices
function isIOSDevice() {
    return /iPad|iPhone|iPod/.test(navigator.userAgent) && !window.MSStream;
}

// Mobile-compatible file tracker to replace DataTransfer API
class MobileCompatFileTracker {
    constructor() {
        this.files = [];
        this.removedIndices = new Set();
    }

    // Add files from a FileList
    addFiles(fileList) {
        // Convert FileList to Array for easier handling
        Array.from(fileList).forEach(file => {
            this.files.push(file);
        });
    }

    // Remove a file by index
    removeFile(index) {
        if (index >= 0 && index < this.files.length) {
            this.removedIndices.add(index);
        }
    }

    // Get all non-removed files
    getFiles() {
        return this.files.filter((_, index) => !this.removedIndices.has(index));
    }

    // Convert to FormData for upload
    appendToFormData(formData, fieldName) {
        this.getFiles().forEach(file => {
            formData.append(fieldName, file);
        });
    }

    // Clear all files
    clear() {
        this.files = [];
        this.removedIndices.clear();
    }
}

// Mobile optimized image preview generator
class ImagePreviewGenerator {
    constructor(options = {}) {
        this.maxWidth = options.maxWidth || 800;
        this.maxHeight = options.maxHeight || 600;
        this.quality = options.quality || 0.8;
        this.maxPreviewsOnMobile = options.maxPreviewsOnMobile || 3;
    }

    // Create optimized image preview element
    createPreview(file, index) {
        return new Promise((resolve, reject) => {
            if (!file) {
                reject(new Error('No file provided'));
                return;
            }

            const isVideo = file.type.startsWith('video/');
            
            if (isVideo) {
                this._createVideoPreview(file, index).then(resolve).catch(reject);
            } else if (file.type.startsWith('image/')) {
                this._createImagePreview(file, index).then(resolve).catch(reject);
            } else {
                reject(new Error('Unsupported file type'));
            }
        });
    }

    // Create image preview with optimization for mobile
    _createImagePreview(file, index) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            
            reader.onload = (e) => {
                // For mobile, we'll compress the image before creating the preview
                if (isMobileDevice()) {
                    this._compressImage(e.target.result)
                        .then(compressedDataUrl => {
                            const previewElement = this._createPreviewElement(compressedDataUrl, file.name, index, false);
                            resolve(previewElement);
                        })
                        .catch(err => {
                            // Fallback to original if compression fails
                            console.warn('Image compression failed, using original:', err);
                            const previewElement = this._createPreviewElement(e.target.result, file.name, index, false);
                            resolve(previewElement);
                        });
                } else {
                    // For desktop, use the original image
                    const previewElement = this._createPreviewElement(e.target.result, file.name, index, false);
                    resolve(previewElement);
                }
            };
            
            reader.onerror = () => reject(new Error('Failed to read file'));
            reader.readAsDataURL(file);
        });
    }

    // Create video preview with thumbnail generation
    _createVideoPreview(file, index) {
        return new Promise((resolve, reject) => {
            const videoUrl = URL.createObjectURL(file);
            const video = document.createElement('video');
            
            video.src = videoUrl;
            video.onloadedmetadata = () => {
                // Create preview element
                const previewElement = this._createPreviewElement(videoUrl, file.name, index, true);
                resolve(previewElement);
                
                // Revoke object URL after a delay to ensure it's loaded
                setTimeout(() => {
                    URL.revokeObjectURL(videoUrl);
                }, 3000);
            };
            
            video.onerror = () => {
                URL.revokeObjectURL(videoUrl);
                reject(new Error('Failed to load video'));
            };
            
            // Set a timeout in case the video never loads
            setTimeout(() => {
                if (!video.videoWidth) {
                    URL.revokeObjectURL(videoUrl);
                    reject(new Error('Video load timeout'));
                }
            }, 5000);
        });
    }

    // Create HTML element for preview
    _createPreviewElement(src, fileName, index, isVideo) {
        const previewDiv = document.createElement('div');
        previewDiv.className = 'image-preview-item';
        
        if (isVideo) {
            const video = document.createElement('video');
            video.src = src;
            video.controls = true;
            video.preload = 'metadata';
            video.style.maxWidth = '150px';
            video.style.maxHeight = '150px';
            video.style.objectFit = 'cover';
            previewDiv.appendChild(video);
        } else {
            const img = document.createElement('img');
            img.src = src;
            img.alt = fileName;
            img.style.maxWidth = '150px';
            img.style.maxHeight = '150px';
            img.style.objectFit = 'cover';
            previewDiv.appendChild(img);
        }
        
        const controlsDiv = document.createElement('div');
        controlsDiv.className = 'image-controls';
        
        const removeButton = document.createElement('button');
        removeButton.type = 'button';
        removeButton.textContent = 'Entfernen';
        removeButton.style.background = '#dc3545';
        removeButton.style.color = 'white';
        removeButton.style.border = 'none';
        removeButton.style.padding = '5px 10px';
        removeButton.style.borderRadius = '3px';
        removeButton.style.cursor = 'pointer';
        removeButton.style.marginLeft = '10px';
        removeButton.dataset.index = index;
        removeButton.addEventListener('click', function() {
            const indexToRemove = parseInt(this.dataset.index, 10);
            // We'll define removeImagePreview elsewhere
            if (typeof window.removeImagePreview === 'function') {
                window.removeImagePreview(indexToRemove);
            }
        });
        
        controlsDiv.appendChild(removeButton);
        previewDiv.appendChild(controlsDiv);
        
        return previewDiv;
    }

    // Compress image for mobile devices
    _compressImage(dataUrl) {
        return new Promise((resolve, reject) => {
            const img = new Image();
            img.onload = () => {
                const canvas = document.createElement('canvas');
                let width = img.width;
                let height = img.height;
                
                // Scale down if needed
                if (width > this.maxWidth || height > this.maxHeight) {
                    const ratio = Math.min(this.maxWidth / width, this.maxHeight / height);
                    width *= ratio;
                    height *= ratio;
                }
                
                canvas.width = width;
                canvas.height = height;
                const ctx = canvas.getContext('2d');
                ctx.drawImage(img, 0, 0, width, height);
                
                // Get compressed data URL
                const compressedDataUrl = canvas.toDataURL('image/jpeg', this.quality);
                
                // Clean up
                canvas.width = 0;
                canvas.height = 0;
                
                resolve(compressedDataUrl);
            };
            
            img.onerror = () => reject(new Error('Failed to load image for compression'));
            img.src = dataUrl;
        });
    }
}

// Mobile-optimized debounce function for event handlers
function debounce(func, wait = 300) {
    let timeout;
    return function(...args) {
        clearTimeout(timeout);
        timeout = setTimeout(() => func.apply(this, args), wait);
    };
}

// Mobile-safe promise-based setTimeout
function delay(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

// Log mobile-specific issues to console or server
function logMobileIssue(action, error) {
    if (isMobileDevice()) {
        const diagnosticInfo = {
            action: action,
            error: error.message,
            browser: navigator.userAgent,
            timestamp: new Date().toISOString(),
            memoryInfo: performance?.memory ? {
                jsHeapSizeLimit: performance.memory.jsHeapSizeLimit,
                totalJSHeapSize: performance.memory.totalJSHeapSize,
                usedJSHeapSize: performance.memory.usedJSHeapSize
            } : 'Not available'
        };
        
        console.error('Mobile Issue:', diagnosticInfo);
        
        // Optionally send to server
        fetch('/log_mobile_issue', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(diagnosticInfo)
        }).catch(() => {
            // Silently fail if logging fails
        });
    }
}
