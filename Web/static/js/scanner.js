/**
 * Hybrid Barcode Scanner
 * Supports: Real-time camera scanning (ZXing.js), image upload fallback (server-side pyzbar),
 *           and USB/keyboard scanner emulation.
 */

class HybridScanner {
  constructor(options = {}) {
    this.options = {
      videoId: options.videoId || 'scanner-video',
      canvasId: options.canvasId || 'scanner-canvas',
      formats: options.formats || ['QR_CODE', 'CODE_128', 'EAN_13', 'ISBN', 'CODE_39', 'UPC_A'],
      fps: options.fps || 10,
      onSuccess: options.onSuccess || (() => {}),
      onError: options.onError || (() => {}),
      facingMode: options.facingMode || 'environment', // 'environment' for rear, 'user' for front
    };

    this.state = {
      isRunning: false,
      stream: null,
      reader: null,
      canvas: null,
      videoElement: null,
      zxingReady: false,
      lastScanTime: 0,
      scanDebounceMs: 300, // Prevent rapid duplicate scans
    };

    this.keyboardInputBuffer = '';
    this.keyboardInputTimeout = null;
  }

  /**
   * Initialize ZXing library from CDN
   */
  async initZXing() {
    if (this.state.zxingReady) {
      return true;
    }

    return new Promise((resolve) => {
      // Load ZXing library from CDN
      if (typeof ZXing !== 'undefined') {
        this.state.zxingReady = true;
        resolve(true);
        return;
      }

      const script = document.createElement('script');
      script.src = 'https://unpkg.com/@zxing/library@latest/umd/index.min.js';
      script.onload = () => {
        this.state.zxingReady = typeof ZXing !== 'undefined';
        resolve(this.state.zxingReady);
      };
      script.onerror = () => {
        console.error('Failed to load ZXing library');
        resolve(false);
      };
      document.head.appendChild(script);
    });
  }

  /**
   * Start real-time barcode scanning via camera
   */
  async start() {
    if (this.state.isRunning) {
      return;
    }

    try {
      // Ensure ZXing is loaded
      const zxingReady = await this.initZXing();
      if (!zxingReady) {
        this.options.onError('ZXing library failed to load. Please use image upload fallback.');
        return;
      }

      // Get DOM elements
      this.state.videoElement = document.getElementById(this.options.videoId);
      this.state.canvas = document.getElementById(this.options.canvasId);

      if (!this.state.videoElement || !this.state.canvas) {
        this.options.onError('Scanner video or canvas element not found.');
        return;
      }

      // Request camera access
      const stream = await navigator.mediaDevices.getUserMedia({
        video: {
          facingMode: this.options.facingMode,
          width: { ideal: 1280 },
          height: { ideal: 720 },
        },
        audio: false,
      });

      this.state.stream = stream;
      this.state.videoElement.srcObject = stream;
      
      // Make video element visible (ensure it's not hidden by display: none)
      this.state.videoElement.style.display = 'block';

      // Initialize ZXing reader
      const hints = new Map();
      hints.set(ZXing.DecodeHintType.POSSIBLE_FORMATS, this.options.formats);
      hints.set(ZXing.DecodeHintType.TRY_HARDER, true);
      this.state.reader = new ZXing.BrowserMultiFormatReader(hints);

      this.state.isRunning = true;

      // Start scanning loop
      this.scanLoop();

      // Setup keyboard input fallback for USB scanners
      this.setupKeyboardInput();
    } catch (err) {
      this.options.onError(`Camera error: ${err.message || err}`);
    }
  }

  /**
   * Stop barcode scanning
   */
  stop() {
    if (!this.state.isRunning) {
      return;
    }

    this.state.isRunning = false;

    if (this.state.stream) {
      this.state.stream.getTracks().forEach((track) => track.stop());
      this.state.stream = null;
    }

    if (this.state.videoElement) {
      this.state.videoElement.srcObject = null;
      this.state.videoElement.style.display = 'none';
    }

    this.removeKeyboardInput();
  }

  /**
   * Main scanning loop for real-time frame processing
   */
  scanLoop() {
    if (!this.state.isRunning) {
      return;
    }

    const canvas = this.state.canvas;
    const video = this.state.videoElement;

    if (video.readyState === video.HAVE_ENOUGH_DATA) {
      canvas.width = video.videoWidth;
      canvas.height = video.videoHeight;
      const context = canvas.getContext('2d');

      if (context) {
        context.drawImage(video, 0, 0);

        try {
          const imageData = context.getImageData(0, 0, canvas.width, canvas.height);
          const luminanceSource = new ZXing.HTMLCanvasElementLuminanceSource(canvas);
          const binaryBitmap = new ZXing.BinaryBitmap(new ZXing.HybridBinarizer(luminanceSource));

          try {
            const result = this.state.reader.decodeFromBitmap(binaryBitmap);
            this.handleScanResult(result.text);
          } catch (e) {
            // No barcode found in frame; continue scanning
          }
        } catch (err) {
          // Silently ignore canvas errors
        }
      }
    }

    // Throttle scan loop
    setTimeout(() => this.scanLoop(), 1000 / this.options.fps);
  }

  /**
   * Handle successful barcode scan with debouncing
   */
  handleScanResult(scannedText) {
    const now = Date.now();
    if (now - this.state.lastScanTime < this.state.scanDebounceMs) {
      return; // Ignore rapid duplicates
    }

    this.state.lastScanTime = now;
    this.options.onSuccess(scannedText.trim());
  }

  /**
   * Setup keyboard input listener for USB scanner emulation
   * Most USB scanners emulate keyboard input (barcode followed by Enter)
   */
  setupKeyboardInput() {
    this.keyboardListener = (event) => {
      // Allow only alphanumeric, dash, colon (common in barcodes)
      if (/^[a-zA-Z0-9:_\-]$/.test(event.key)) {
        event.preventDefault();
        this.keyboardInputBuffer += event.key;

        // Reset timeout for multi-part barcodes
        if (this.keyboardInputTimeout) {
          clearTimeout(this.keyboardInputTimeout);
        }
      } else if (event.key === 'Enter') {
        event.preventDefault();
        if (this.keyboardInputBuffer.length > 0) {
          this.handleScanResult(this.keyboardInputBuffer);
          this.keyboardInputBuffer = '';
        }
      } else if (event.key === 'Escape') {
        this.keyboardInputBuffer = '';
        this.stop();
      }

      // Auto-trigger if buffer looks complete (common barcode lengths)
      if ([8, 12, 13, 17].includes(this.keyboardInputBuffer.length)) {
        this.keyboardInputTimeout = setTimeout(() => {
          if (this.keyboardInputBuffer.length > 0) {
            this.handleScanResult(this.keyboardInputBuffer);
            this.keyboardInputBuffer = '';
          }
        }, 200);
      }
    };

    document.addEventListener('keydown', this.keyboardListener);
  }

  /**
   * Remove keyboard input listener
   */
  removeKeyboardInput() {
    if (this.keyboardListener) {
      document.removeEventListener('keydown', this.keyboardListener);
      this.keyboardListener = null;
    }
    this.keyboardInputBuffer = '';
  }

  /**
   * Upload image for server-side decoding (fallback)
   * Requires /api/scan_upload endpoint
   */
  static async uploadImageForDecoding(file, onSuccess, onError) {
    try {
      const formData = new FormData();
      formData.append('image', file);

      const response = await fetch('/api/scan_upload', {
        method: 'POST',
        body: formData,
      });

      const data = await response.json();

      if (data.ok && data.barcodes && data.barcodes.length > 0) {
        // Return first detected barcode (highest confidence)
        onSuccess(data.barcodes[0].value);
      } else {
        onError(data.message || 'No barcode detected in image.');
      }
    } catch (err) {
      onError(`Upload error: ${err.message}`);
    }
  }

  /**
   * Toggle camera (front/rear on mobile)
   */
  toggleCamera() {
    if (this.options.facingMode === 'environment') {
      this.options.facingMode = 'user';
    } else {
      this.options.facingMode = 'environment';
    }

    // Restart scanning with new camera
    this.stop();
    this.start();
  }
}

// Export for use in templates
if (typeof window !== 'undefined') {
  window.HybridScanner = HybridScanner;
}
