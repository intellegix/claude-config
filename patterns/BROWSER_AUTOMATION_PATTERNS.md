# Browser Automation Patterns

## Chrome Extension Architecture

### Manifest V3 Pattern
```json
{
    "manifest_version": 3,
    "name": "Claude Browser Automation",
    "version": "1.0.0",
    "permissions": [
        "activeTab",
        "storage",
        "webNavigation",
        "nativeMessaging"
    ],
    "host_permissions": [
        "*://*/*"
    ],
    "background": {
        "service_worker": "background.js",
        "type": "module"
    },
    "content_scripts": [
        {
            "matches": ["*://*/*"],
            "js": ["content.js"],
            "run_at": "document_end"
        }
    ]
}
```

### Service Worker Pattern (background.js)
```javascript
class BackgroundService {
    constructor() {
        this.websocketUrl = 'ws://localhost:8080';
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
        this.reconnectDelay = 1000;
        this.ws = null;
    }

    async initialize() {
        await this.connectWebSocket();
        this.setupMessageHandlers();
        this.setupTabEventHandlers();
    }

    async connectWebSocket() {
        try {
            this.ws = new WebSocket(this.websocketUrl);

            this.ws.onopen = () => {
                console.log('WebSocket connected');
                this.reconnectAttempts = 0;
            };

            this.ws.onmessage = async (event) => {
                await this.handleMessage(JSON.parse(event.data));
            };

            this.ws.onclose = () => {
                console.log('WebSocket disconnected');
                this.scheduleReconnect();
            };

            this.ws.onerror = (error) => {
                console.error('WebSocket error:', error);
            };

        } catch (error) {
            console.error('WebSocket connection failed:', error);
            this.scheduleReconnect();
        }
    }

    scheduleReconnect() {
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
            this.reconnectAttempts++;
            setTimeout(() => {
                this.connectWebSocket();
            }, this.reconnectDelay * this.reconnectAttempts);
        }
    }

    async handleMessage(message) {
        try {
            const { id, method, params } = message;
            let result;

            switch (method) {
                case 'click':
                    result = await this.executeClick(params);
                    break;
                case 'type':
                    result = await this.executeType(params);
                    break;
                case 'navigate':
                    result = await this.executeNavigate(params);
                    break;
                case 'screenshot':
                    result = await this.executeScreenshot(params);
                    break;
                case 'getPageText':
                    result = await this.getPageText(params);
                    break;
                default:
                    throw new Error(`Unknown method: ${method}`);
            }

            this.sendResponse(id, result);

        } catch (error) {
            this.sendError(id, error.message);
        }
    }

    async executeClick(params) {
        const { tabId, selector } = params;

        const result = await chrome.tabs.sendMessage(tabId, {
            action: 'click',
            selector
        });

        return { success: result.success, element: result.element };
    }

    async executeType(params) {
        const { tabId, selector, text } = params;

        const result = await chrome.tabs.sendMessage(tabId, {
            action: 'type',
            selector,
            text
        });

        return { success: result.success, text };
    }

    async executeNavigate(params) {
        const { tabId, url } = params;

        await chrome.tabs.update(tabId, { url });

        // Wait for navigation to complete
        return new Promise((resolve) => {
            const listener = (tabIdUpdated, changeInfo) => {
                if (tabIdUpdated === tabId && changeInfo.status === 'complete') {
                    chrome.tabs.onUpdated.removeListener(listener);
                    resolve({ success: true, url });
                }
            };
            chrome.tabs.onUpdated.addListener(listener);
        });
    }

    async executeScreenshot(params) {
        const { tabId } = params;

        const dataUrl = await chrome.tabs.captureVisibleTab();
        return { success: true, screenshot: dataUrl };
    }

    async getPageText(params) {
        const { tabId } = params;

        const result = await chrome.tabs.sendMessage(tabId, {
            action: 'getPageText'
        });

        return { success: true, text: result.text };
    }

    sendResponse(id, result) {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify({ id, result }));
        }
    }

    sendError(id, errorMessage) {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify({
                id,
                error: {
                    code: -1,
                    message: errorMessage
                }
            }));
        }
    }

    setupTabEventHandlers() {
        chrome.tabs.onCreated.addListener((tab) => {
            this.notifyTabEvent('created', tab);
        });

        chrome.tabs.onRemoved.addListener((tabId, removeInfo) => {
            this.notifyTabEvent('removed', { tabId, removeInfo });
        });

        chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
            if (changeInfo.status === 'complete') {
                this.notifyTabEvent('updated', { tabId, changeInfo, tab });
            }
        });
    }

    notifyTabEvent(eventType, data) {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify({
                method: 'tabEvent',
                params: { eventType, data }
            }));
        }
    }
}

// Initialize service
const backgroundService = new BackgroundService();
backgroundService.initialize();
```

### Content Script Pattern
```javascript
class ContentScriptHandler {
    constructor() {
        this.setupMessageHandler();
    }

    setupMessageHandler() {
        chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
            this.handleMessage(message)
                .then(sendResponse)
                .catch(error => {
                    sendResponse({ success: false, error: error.message });
                });
            return true; // Keep message channel open for async response
        });
    }

    async handleMessage(message) {
        const { action } = message;

        switch (action) {
            case 'click':
                return await this.handleClick(message);
            case 'type':
                return await this.handleType(message);
            case 'getPageText':
                return await this.handleGetPageText(message);
            case 'waitForElement':
                return await this.handleWaitForElement(message);
            default:
                throw new Error(`Unknown action: ${action}`);
        }
    }

    async handleClick(message) {
        const { selector } = message;
        const element = await this.findElement(selector);

        if (!element) {
            throw new Error(`Element not found: ${selector}`);
        }

        // Scroll element into view
        element.scrollIntoView({ behavior: 'smooth', block: 'center' });

        // Wait for potential animations
        await this.sleep(100);

        // Click the element
        element.click();

        return {
            success: true,
            element: {
                tagName: element.tagName,
                className: element.className,
                textContent: element.textContent?.substring(0, 100)
            }
        };
    }

    async handleType(message) {
        const { selector, text } = message;
        const element = await this.findElement(selector);

        if (!element) {
            throw new Error(`Element not found: ${selector}`);
        }

        if (!['INPUT', 'TEXTAREA'].includes(element.tagName)) {
            throw new Error(`Element is not typeable: ${element.tagName}`);
        }

        // Focus the element
        element.focus();

        // Clear existing content
        element.select();

        // Type text with realistic timing
        await this.typeText(element, text);

        // Trigger change event
        element.dispatchEvent(new Event('input', { bubbles: true }));
        element.dispatchEvent(new Event('change', { bubbles: true }));

        return { success: true, text };
    }

    async handleGetPageText(message) {
        // Remove script and style elements
        const clonedDoc = document.cloneNode(true);
        const scripts = clonedDoc.querySelectorAll('script, style, noscript');
        scripts.forEach(el => el.remove());

        const text = clonedDoc.body?.textContent || clonedDoc.textContent || '';

        return {
            success: true,
            text: text.replace(/\s+/g, ' ').trim().substring(0, 50000) // Limit size
        };
    }

    async handleWaitForElement(message) {
        const { selector, timeout = 5000 } = message;

        const element = await this.waitForElement(selector, timeout);

        return {
            success: true,
            found: !!element,
            element: element ? {
                tagName: element.tagName,
                className: element.className
            } : null
        };
    }

    async findElement(selector, timeout = 1000) {
        return new Promise((resolve) => {
            const element = document.querySelector(selector);
            if (element) {
                resolve(element);
                return;
            }

            // Wait for dynamic content
            const observer = new MutationObserver(() => {
                const element = document.querySelector(selector);
                if (element) {
                    observer.disconnect();
                    resolve(element);
                }
            });

            observer.observe(document.body, {
                childList: true,
                subtree: true
            });

            setTimeout(() => {
                observer.disconnect();
                resolve(null);
            }, timeout);
        });
    }

    async waitForElement(selector, timeout) {
        return new Promise((resolve, reject) => {
            const element = document.querySelector(selector);
            if (element) {
                resolve(element);
                return;
            }

            const observer = new MutationObserver(() => {
                const element = document.querySelector(selector);
                if (element) {
                    observer.disconnect();
                    resolve(element);
                }
            });

            observer.observe(document.body, {
                childList: true,
                subtree: true
            });

            setTimeout(() => {
                observer.disconnect();
                reject(new Error(`Element not found within ${timeout}ms: ${selector}`));
            }, timeout);
        });
    }

    async typeText(element, text) {
        for (const char of text) {
            element.value += char;

            // Trigger input event for each character
            element.dispatchEvent(new InputEvent('input', {
                bubbles: true,
                inputType: 'insertText',
                data: char
            }));

            // Random delay between 50-150ms per character
            await this.sleep(50 + Math.random() * 100);
        }
    }

    sleep(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }
}

// Initialize content script
new ContentScriptHandler();
```

## Browser Action Patterns

### Safe Element Interaction
```javascript
class SafeElementActions {
    static async safeClick(selector, options = {}) {
        const {
            timeout = 5000,
            retries = 3,
            waitForStable = true
        } = options;

        for (let attempt = 1; attempt <= retries; attempt++) {
            try {
                const element = await this.waitForElement(selector, timeout);

                if (!element) {
                    throw new Error(`Element not found: ${selector}`);
                }

                // Check if element is clickable
                if (!this.isClickable(element)) {
                    throw new Error(`Element is not clickable: ${selector}`);
                }

                // Wait for element to be stable (not moving)
                if (waitForStable) {
                    await this.waitForElementStable(element);
                }

                // Scroll into view if needed
                if (!this.isInViewport(element)) {
                    element.scrollIntoView({
                        behavior: 'smooth',
                        block: 'center'
                    });
                    await this.sleep(500);
                }

                // Perform click
                element.click();

                return { success: true, attempt };

            } catch (error) {
                if (attempt === retries) {
                    throw error;
                }
                await this.sleep(1000 * attempt);
            }
        }
    }

    static isClickable(element) {
        const style = window.getComputedStyle(element);

        return (
            style.display !== 'none' &&
            style.visibility !== 'hidden' &&
            style.pointerEvents !== 'none' &&
            element.offsetParent !== null
        );
    }

    static isInViewport(element) {
        const rect = element.getBoundingClientRect();

        return (
            rect.top >= 0 &&
            rect.left >= 0 &&
            rect.bottom <= window.innerHeight &&
            rect.right <= window.innerWidth
        );
    }

    static async waitForElementStable(element, duration = 100) {
        let lastRect = element.getBoundingClientRect();

        return new Promise((resolve) => {
            setTimeout(() => {
                const currentRect = element.getBoundingClientRect();

                if (
                    Math.abs(lastRect.top - currentRect.top) < 1 &&
                    Math.abs(lastRect.left - currentRect.left) < 1
                ) {
                    resolve(true);
                } else {
                    // Element is still moving, wait more
                    this.waitForElementStable(element, duration).then(resolve);
                }
            }, duration);
        });
    }
}
```

### Form Handling Patterns
```javascript
class FormHandler {
    static async fillForm(formSelector, data) {
        const form = document.querySelector(formSelector);
        if (!form) {
            throw new Error(`Form not found: ${formSelector}`);
        }

        const results = [];

        for (const [fieldName, value] of Object.entries(data)) {
            try {
                const result = await this.fillField(form, fieldName, value);
                results.push(result);
            } catch (error) {
                results.push({
                    field: fieldName,
                    success: false,
                    error: error.message
                });
            }
        }

        return results;
    }

    static async fillField(form, fieldName, value) {
        // Try multiple selector strategies
        const selectors = [
            `[name="${fieldName}"]`,
            `#${fieldName}`,
            `[id*="${fieldName}"]`,
            `[placeholder*="${fieldName}"]`,
            `label[for*="${fieldName}"] + input, label[for*="${fieldName}"] + textarea, label[for*="${fieldName}"] + select`
        ];

        let element = null;
        for (const selector of selectors) {
            element = form.querySelector(selector);
            if (element) break;
        }

        if (!element) {
            throw new Error(`Field not found: ${fieldName}`);
        }

        return await this.setElementValue(element, value);
    }

    static async setElementValue(element, value) {
        const tagName = element.tagName.toLowerCase();
        const type = element.type?.toLowerCase();

        switch (tagName) {
            case 'input':
                switch (type) {
                    case 'checkbox':
                    case 'radio':
                        element.checked = Boolean(value);
                        break;
                    case 'file':
                        throw new Error('File inputs not supported');
                    default:
                        await this.typeIntoInput(element, value);
                }
                break;

            case 'select':
                await this.selectOption(element, value);
                break;

            case 'textarea':
                await this.typeIntoInput(element, value);
                break;

            default:
                throw new Error(`Unsupported element type: ${tagName}`);
        }

        // Trigger events
        element.dispatchEvent(new Event('input', { bubbles: true }));
        element.dispatchEvent(new Event('change', { bubbles: true }));

        return {
            field: element.name || element.id,
            success: true,
            value
        };
    }

    static async typeIntoInput(element, text) {
        // Clear existing value
        element.focus();
        element.select();
        document.execCommand('delete');

        // Type new value character by character
        for (const char of String(text)) {
            element.value += char;

            element.dispatchEvent(new InputEvent('input', {
                bubbles: true,
                inputType: 'insertText',
                data: char
            }));

            // Small delay for realism
            await new Promise(resolve => setTimeout(resolve, 10 + Math.random() * 20));
        }
    }

    static async selectOption(selectElement, value) {
        // Try to find option by value first
        let option = selectElement.querySelector(`option[value="${value}"]`);

        // If not found, try by text content
        if (!option) {
            const options = Array.from(selectElement.querySelectorAll('option'));
            option = options.find(opt =>
                opt.textContent.trim().toLowerCase() === String(value).toLowerCase()
            );
        }

        if (!option) {
            throw new Error(`Option not found: ${value}`);
        }

        selectElement.value = option.value;
        option.selected = true;
    }
}
```

## Error Recovery Patterns

### Automatic Retry Strategy
```javascript
class RetryStrategy {
    static async withRetry(operation, options = {}) {
        const {
            maxAttempts = 3,
            baseDelay = 1000,
            backoffFactor = 2,
            onRetry = null
        } = options;

        let lastError;

        for (let attempt = 1; attempt <= maxAttempts; attempt++) {
            try {
                return await operation();
            } catch (error) {
                lastError = error;

                if (attempt === maxAttempts) {
                    break;
                }

                const delay = baseDelay * Math.pow(backoffFactor, attempt - 1);

                if (onRetry) {
                    onRetry(error, attempt, delay);
                }

                await this.sleep(delay);
            }
        }

        throw lastError;
    }

    static sleep(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }

    static async withTimeout(operation, timeoutMs) {
        return Promise.race([
            operation(),
            new Promise((_, reject) =>
                setTimeout(() => reject(new Error(`Operation timed out after ${timeoutMs}ms`)), timeoutMs)
            )
        ]);
    }
}

// Usage
const result = await RetryStrategy.withRetry(
    () => SafeElementActions.safeClick('#submit-button'),
    {
        maxAttempts: 3,
        baseDelay: 1000,
        onRetry: (error, attempt, delay) => {
            console.log(`Attempt ${attempt} failed: ${error.message}. Retrying in ${delay}ms...`);
        }
    }
);
```

## Performance Monitoring

### Action Timing and Metrics
```javascript
class PerformanceMonitor {
    static async measureAction(actionName, operation) {
        const startTime = performance.now();
        let success = false;
        let error = null;

        try {
            const result = await operation();
            success = true;
            return result;
        } catch (e) {
            error = e;
            throw e;
        } finally {
            const endTime = performance.now();
            const duration = endTime - startTime;

            this.recordMetric({
                action: actionName,
                duration,
                success,
                error: error?.message,
                timestamp: Date.now()
            });
        }
    }

    static recordMetric(metric) {
        // Send to analytics or logging service
        console.log('Performance metric:', metric);

        // Store locally for debugging
        const metrics = JSON.parse(localStorage.getItem('automation_metrics') || '[]');
        metrics.push(metric);

        // Keep only last 100 metrics
        if (metrics.length > 100) {
            metrics.shift();
        }

        localStorage.setItem('automation_metrics', JSON.stringify(metrics));
    }

    static getMetrics() {
        return JSON.parse(localStorage.getItem('automation_metrics') || '[]');
    }

    static getAverageActionTime(actionName) {
        const metrics = this.getMetrics()
            .filter(m => m.action === actionName && m.success);

        if (metrics.length === 0) return null;

        const totalTime = metrics.reduce((sum, m) => sum + m.duration, 0);
        return totalTime / metrics.length;
    }
}
```

## Testing Patterns

### Browser Automation Tests
```javascript
class BrowserAutomationTest {
    constructor() {
        this.testResults = [];
    }

    async runTestSuite() {
        const tests = [
            this.testBasicNavigation,
            this.testElementInteraction,
            this.testFormFilling,
            this.testErrorHandling
        ];

        for (const test of tests) {
            await this.runTest(test.name, test.bind(this));
        }

        return this.testResults;
    }

    async runTest(testName, testFunction) {
        try {
            console.log(`Running test: ${testName}`);
            await testFunction();
            this.testResults.push({ test: testName, status: 'PASS' });
        } catch (error) {
            console.error(`Test failed: ${testName}`, error);
            this.testResults.push({
                test: testName,
                status: 'FAIL',
                error: error.message
            });
        }
    }

    async testBasicNavigation() {
        // Test navigation
        await chrome.tabs.update({ url: 'https://example.com' });

        // Wait for page load
        await this.waitForPageLoad();

        // Verify page loaded correctly
        const title = await this.getPageTitle();
        if (!title.includes('Example')) {
            throw new Error('Page did not load correctly');
        }
    }

    async testElementInteraction() {
        // Test clicking elements
        await SafeElementActions.safeClick('a[href="/about"]');
        await this.waitForPageLoad();

        // Verify navigation worked
        const url = await this.getCurrentUrl();
        if (!url.includes('/about')) {
            throw new Error('Navigation did not work');
        }
    }

    async testFormFilling() {
        // Navigate to form page
        await chrome.tabs.update({ url: 'https://example.com/contact' });
        await this.waitForPageLoad();

        // Fill form
        const formData = {
            name: 'Test User',
            email: 'test@example.com',
            message: 'This is a test message'
        };

        await FormHandler.fillForm('#contact-form', formData);

        // Verify form was filled
        const nameValue = await this.getInputValue('[name="name"]');
        if (nameValue !== 'Test User') {
            throw new Error('Form filling did not work');
        }
    }

    async testErrorHandling() {
        // Test clicking non-existent element
        try {
            await SafeElementActions.safeClick('#non-existent-element');
            throw new Error('Should have thrown an error');
        } catch (error) {
            if (!error.message.includes('Element not found')) {
                throw new Error('Wrong error type thrown');
            }
        }
    }

    async waitForPageLoad() {
        return new Promise((resolve) => {
            chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
                const checkLoad = () => {
                    chrome.tabs.get(tabs[0].id, (tab) => {
                        if (tab.status === 'complete') {
                            resolve();
                        } else {
                            setTimeout(checkLoad, 100);
                        }
                    });
                };
                checkLoad();
            });
        });
    }
}
```

## Usage Guidelines

1. **Always handle asynchronous operations** with proper await/Promise patterns
2. **Implement robust error handling** with retries and fallbacks
3. **Wait for elements to be stable** before interaction
4. **Use realistic timing** for typing and interactions
5. **Monitor performance** and track action success rates
6. **Test thoroughly** across different websites and scenarios
7. **Handle dynamic content** with proper observers and timeouts
8. **Implement proper cleanup** for event listeners and observers