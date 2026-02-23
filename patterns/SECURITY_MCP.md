# MCP Browser Automation Security Checklist

## WebSocket Security

### TLS Encryption
```javascript
// Production WebSocket configuration
class SecureWebSocket {
    constructor() {
        this.wsUrl = process.env.NODE_ENV === 'production'
            ? 'wss://localhost:8443'
            : 'ws://localhost:8080';

        this.tlsOptions = {
            key: fs.readFileSync('server-key.pem'),
            cert: fs.readFileSync('server-cert.pem'),
            ca: fs.readFileSync('ca-cert.pem'), // Optional CA chain
            requestCert: true,
            rejectUnauthorized: true
        };
    }

    createSecureServer() {
        const httpsServer = https.createServer(this.tlsOptions);
        const wss = new WebSocket.Server({
            server: httpsServer,
            verifyClient: this.verifyClient.bind(this)
        });

        return { httpsServer, wss };
    }

    verifyClient(info) {
        // Verify origin
        const allowedOrigins = process.env.ALLOWED_ORIGINS?.split(',') || ['chrome-extension://'];
        const origin = info.origin;

        if (!allowedOrigins.some(allowed => origin.startsWith(allowed))) {
            console.warn(`Rejected connection from unauthorized origin: ${origin}`);
            return false;
        }

        // Additional security checks
        return this.validateClientCertificate(info.req.socket);
    }

    validateClientCertificate(socket) {
        if (!socket.authorized) {
            console.warn('Client certificate validation failed');
            return false;
        }

        const cert = socket.getPeerCertificate();
        if (!cert || !cert.subject) {
            console.warn('No valid client certificate provided');
            return false;
        }

        return true;
    }
}
```

### Message Authentication
```javascript
const crypto = require('crypto');

class MessageAuthenticator {
    constructor(secretKey) {
        this.secretKey = secretKey;
        this.algorithm = 'aes-256-gcm';
    }

    encryptMessage(message) {
        const iv = crypto.randomBytes(16);
        const cipher = crypto.createCipher(this.algorithm, this.secretKey);
        cipher.setAAD(Buffer.from('mcp-browser-automation'));

        let encrypted = cipher.update(JSON.stringify(message), 'utf8', 'hex');
        encrypted += cipher.final('hex');

        const authTag = cipher.getAuthTag();

        return {
            data: encrypted,
            iv: iv.toString('hex'),
            authTag: authTag.toString('hex')
        };
    }

    decryptMessage(encryptedData) {
        const { data, iv, authTag } = encryptedData;

        const decipher = crypto.createDecipher(this.algorithm, this.secretKey);
        decipher.setAAD(Buffer.from('mcp-browser-automation'));
        decipher.setAuthTag(Buffer.from(authTag, 'hex'));

        let decrypted = decipher.update(data, 'hex', 'utf8');
        decrypted += decipher.final('utf8');

        return JSON.parse(decrypted);
    }

    generateHMAC(message) {
        return crypto
            .createHmac('sha256', this.secretKey)
            .update(JSON.stringify(message))
            .digest('hex');
    }

    verifyHMAC(message, signature) {
        const expectedSignature = this.generateHMAC(message);
        return crypto.timingSafeEqual(
            Buffer.from(signature, 'hex'),
            Buffer.from(expectedSignature, 'hex')
        );
    }
}
```

## Input Validation & Sanitization

### Comprehensive Input Validation
```typescript
import { z } from 'zod';

// URL validation with whitelist
const SafeURLSchema = z.string().url().refine((url) => {
    const parsed = new URL(url);
    const allowedProtocols = ['http:', 'https:'];
    const blockedDomains = ['localhost', '127.0.0.1', '0.0.0.0'];

    if (!allowedProtocols.includes(parsed.protocol)) {
        throw new Error('Invalid protocol');
    }

    if (blockedDomains.includes(parsed.hostname)) {
        throw new Error('Blocked domain');
    }

    return true;
});

// CSS selector sanitization
const SafeSelectorSchema = z.string().refine((selector) => {
    // Only allow safe CSS selector characters
    const safePattern = /^[a-zA-Z0-9\-_#.\[\]="':() >+~*]+$/;
    if (!safePattern.test(selector)) {
        throw new Error('Invalid selector characters');
    }

    // Block dangerous selectors
    const dangerousPatterns = [
        /javascript:/i,
        /data:/i,
        /vbscript:/i,
        /on\w+=/i
    ];

    for (const pattern of dangerousPatterns) {
        if (pattern.test(selector)) {
            throw new Error('Dangerous selector pattern detected');
        }
    }

    return true;
});

// Complete action validation schema
const ActionSchema = z.object({
    sessionId: z.string().uuid(),
    type: z.enum(['click', 'type', 'navigate', 'screenshot', 'scroll']),
    selector: SafeSelectorSchema.optional(),
    text: z.string().max(10000).optional(), // Limit text length
    url: SafeURLSchema.optional(),
    tabId: z.number().int().positive().optional()
}).refine((data) => {
    // Cross-field validation
    if (data.type === 'click' && !data.selector) {
        throw new Error('Selector required for click action');
    }
    if (data.type === 'type' && (!data.selector || !data.text)) {
        throw new Error('Selector and text required for type action');
    }
    if (data.type === 'navigate' && !data.url) {
        throw new Error('URL required for navigate action');
    }
    return true;
});

function validateAndSanitizeAction(input: unknown): Result<ValidAction> {
    try {
        const action = ActionSchema.parse(input);
        return Result.ok(action);
    } catch (error) {
        console.warn('Action validation failed:', error.message, { input });
        return Result.error(`Validation failed: ${error.message}`);
    }
}
```

### XSS Prevention
```javascript
class XSSPrevention {
    static sanitizeText(text) {
        if (typeof text !== 'string') {
            return '';
        }

        // HTML entity encoding
        return text
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#x27;')
            .replace(/\//g, '&#x2F;');
    }

    static validateSelector(selector) {
        // Remove any potential script injection
        const cleaned = selector
            .replace(/javascript:/gi, '')
            .replace(/data:/gi, '')
            .replace(/vbscript:/gi, '')
            .replace(/on\w+\s*=/gi, '');

        // Ensure it's a valid CSS selector
        try {
            document.createElement('div').querySelector(cleaned);
            return cleaned;
        } catch (error) {
            throw new Error('Invalid CSS selector');
        }
    }

    static sanitizeURL(url) {
        try {
            const parsed = new URL(url);

            // Only allow safe protocols
            if (!['http:', 'https:'].includes(parsed.protocol)) {
                throw new Error('Invalid protocol');
            }

            return parsed.toString();
        } catch (error) {
            throw new Error('Invalid URL');
        }
    }
}
```

## Authentication & Authorization

### Session-Based Authentication
```javascript
class SessionManager {
    constructor() {
        this.sessions = new Map();
        this.sessionTimeout = 30 * 60 * 1000; // 30 minutes
        this.cleanupInterval = setInterval(() => this.cleanup(), 60000); // 1 minute
    }

    async createSession(clientId, permissions = []) {
        const sessionId = crypto.randomUUID();
        const expiresAt = Date.now() + this.sessionTimeout;

        const session = {
            id: sessionId,
            clientId,
            permissions: new Set(permissions),
            createdAt: Date.now(),
            expiresAt,
            lastAccessed: Date.now()
        };

        this.sessions.set(sessionId, session);

        // Store in database for persistence
        await this.persistSession(session);

        return sessionId;
    }

    async validateSession(sessionId) {
        const session = this.sessions.get(sessionId);

        if (!session) {
            return Result.error('Session not found');
        }

        if (Date.now() > session.expiresAt) {
            this.sessions.delete(sessionId);
            return Result.error('Session expired');
        }

        // Update last accessed time
        session.lastAccessed = Date.now();
        session.expiresAt = Date.now() + this.sessionTimeout;

        return Result.ok(session);
    }

    async revokeSession(sessionId) {
        this.sessions.delete(sessionId);
        await this.removeSessionFromDatabase(sessionId);
    }

    hasPermission(session, requiredPermission) {
        return session.permissions.has(requiredPermission) ||
               session.permissions.has('admin');
    }

    cleanup() {
        const now = Date.now();
        for (const [sessionId, session] of this.sessions) {
            if (now > session.expiresAt) {
                this.sessions.delete(sessionId);
            }
        }
    }
}

// Permission-based action authorization
class ActionAuthorizer {
    static async authorize(session, action) {
        const requiredPermissions = {
            'navigate': 'navigation',
            'click': 'interaction',
            'type': 'interaction',
            'screenshot': 'capture',
            'scroll': 'interaction'
        };

        const required = requiredPermissions[action.type];
        if (!required) {
            return Result.error(`Unknown action type: ${action.type}`);
        }

        if (!session.permissions.has(required)) {
            return Result.error(`Insufficient permissions for ${action.type}`);
        }

        // Additional checks for sensitive actions
        if (action.type === 'navigate') {
            return this.authorizeNavigation(session, action.url);
        }

        return Result.ok(true);
    }

    static authorizeNavigation(session, url) {
        try {
            const parsed = new URL(url);

            // Check domain whitelist
            const allowedDomains = session.permissions.has('unrestricted')
                ? null
                : ['example.com', 'test.com'];

            if (allowedDomains && !allowedDomains.includes(parsed.hostname)) {
                return Result.error(`Domain not allowed: ${parsed.hostname}`);
            }

            return Result.ok(true);
        } catch (error) {
            return Result.error('Invalid URL for navigation');
        }
    }
}
```

## Audit Logging

### Comprehensive Audit Trail
```javascript
class AuditLogger {
    constructor() {
        this.logFile = path.join(__dirname, 'logs', 'audit.log');
        this.ensureLogDirectory();
    }

    ensureLogDirectory() {
        const logDir = path.dirname(this.logFile);
        if (!fs.existsSync(logDir)) {
            fs.mkdirSync(logDir, { recursive: true });
        }
    }

    async logAction(session, action, result) {
        const logEntry = {
            timestamp: new Date().toISOString(),
            sessionId: session.id,
            clientId: session.clientId,
            action: {
                type: action.type,
                selector: action.selector,
                url: action.url,
                // Never log sensitive data like passwords
                hasText: !!action.text,
                textLength: action.text?.length || 0
            },
            result: {
                success: result.isSuccess,
                error: result.isError ? result.error : undefined,
                duration: result.duration
            },
            sourceIP: session.sourceIP,
            userAgent: session.userAgent
        };

        await this.writeLogEntry(logEntry);
    }

    async logSecurityEvent(eventType, details) {
        const logEntry = {
            timestamp: new Date().toISOString(),
            type: 'SECURITY_EVENT',
            eventType,
            details: {
                ...details,
                // Sanitize sensitive information
                sessionId: details.sessionId ? this.hashSensitiveData(details.sessionId) : undefined,
                sourceIP: details.sourceIP || 'unknown'
            }
        };

        await this.writeLogEntry(logEntry);

        // Send security alerts for critical events
        if (['AUTHENTICATION_FAILURE', 'UNAUTHORIZED_ACCESS', 'XSS_ATTEMPT'].includes(eventType)) {
            await this.sendSecurityAlert(logEntry);
        }
    }

    async writeLogEntry(entry) {
        const logLine = JSON.stringify(entry) + '\n';

        try {
            await fs.promises.appendFile(this.logFile, logLine, 'utf8');
        } catch (error) {
            console.error('Failed to write audit log:', error);
            // Could implement fallback logging here (e.g., database)
        }
    }

    hashSensitiveData(data) {
        return crypto
            .createHash('sha256')
            .update(data)
            .digest('hex')
            .substring(0, 8); // First 8 characters for identification
    }

    async sendSecurityAlert(logEntry) {
        // Implementation depends on your alerting system
        // Could be email, Slack, PagerDuty, etc.
        console.error('SECURITY ALERT:', logEntry);
    }

    async queryLogs(filters = {}) {
        // Read and parse log file for security analysis
        const logs = [];
        const fileContent = await fs.promises.readFile(this.logFile, 'utf8');
        const lines = fileContent.trim().split('\n');

        for (const line of lines) {
            try {
                const entry = JSON.parse(line);

                // Apply filters
                if (filters.sessionId && entry.sessionId !== filters.sessionId) continue;
                if (filters.eventType && entry.eventType !== filters.eventType) continue;
                if (filters.startTime && entry.timestamp < filters.startTime) continue;
                if (filters.endTime && entry.timestamp > filters.endTime) continue;

                logs.push(entry);
            } catch (error) {
                console.warn('Failed to parse log line:', line);
            }
        }

        return logs;
    }
}
```

## Rate Limiting & DoS Prevention

### Rate Limiting Implementation
```javascript
class RateLimiter {
    constructor() {
        this.requests = new Map(); // clientId -> request data
        this.cleanupInterval = setInterval(() => this.cleanup(), 60000);
    }

    async checkRateLimit(clientId, action) {
        const now = Date.now();
        const windowSize = 60 * 1000; // 1 minute
        const limits = {
            'click': 100,
            'type': 50,
            'navigate': 20,
            'screenshot': 10
        };

        const maxRequests = limits[action] || 10;

        if (!this.requests.has(clientId)) {
            this.requests.set(clientId, []);
        }

        const clientRequests = this.requests.get(clientId);

        // Remove old requests outside the window
        const recentRequests = clientRequests.filter(
            timestamp => now - timestamp < windowSize
        );

        if (recentRequests.length >= maxRequests) {
            await this.logRateLimitViolation(clientId, action, recentRequests.length);
            return Result.error(`Rate limit exceeded for ${action}: ${recentRequests.length}/${maxRequests} per minute`);
        }

        recentRequests.push(now);
        this.requests.set(clientId, recentRequests);

        return Result.ok(true);
    }

    async logRateLimitViolation(clientId, action, requestCount) {
        console.warn(`Rate limit violation: ${clientId} attempted ${requestCount} ${action} requests`);

        // Could implement progressive penalties here
        // e.g., temporary bans for repeated violations
    }

    cleanup() {
        const now = Date.now();
        const windowSize = 60 * 1000;

        for (const [clientId, requests] of this.requests) {
            const recentRequests = requests.filter(
                timestamp => now - timestamp < windowSize
            );

            if (recentRequests.length === 0) {
                this.requests.delete(clientId);
            } else {
                this.requests.set(clientId, recentRequests);
            }
        }
    }
}
```

## Data Protection

### Sensitive Data Handling
```javascript
class DataProtection {
    static classifyData(data) {
        const sensitivePatterns = [
            /\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b/, // Credit card
            /\b\d{3}-\d{2}-\d{4}\b/, // SSN
            /\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b/, // Email
            /\b(?:\d{3}-|\d{3}\s)?\d{3}-\d{4}\b/, // Phone
            /password|pwd|pass/i // Password fields
        ];

        for (const pattern of sensitivePatterns) {
            if (pattern.test(data)) {
                return 'SENSITIVE';
            }
        }

        return 'SAFE';
    }

    static sanitizeForLogging(data) {
        if (this.classifyData(data) === 'SENSITIVE') {
            return '[REDACTED]';
        }

        // Still limit length for logging
        return data.length > 100 ? data.substring(0, 100) + '...' : data;
    }

    static encryptSensitiveData(data, key) {
        const cipher = crypto.createCipher('aes-256-gcm', key);
        let encrypted = cipher.update(data, 'utf8', 'hex');
        encrypted += cipher.final('hex');

        return {
            data: encrypted,
            authTag: cipher.getAuthTag().toString('hex')
        };
    }
}
```

## Security Monitoring

### Real-time Threat Detection
```javascript
class ThreatDetector {
    constructor() {
        this.suspiciousPatterns = [
            /javascript:/i,
            /<script/i,
            /eval\(/i,
            /document\.cookie/i,
            /window\.location/i
        ];

        this.anomalyThresholds = {
            requestsPerMinute: 200,
            failureRate: 0.5,
            uniqueSelectorsPerSession: 1000
        };

        this.sessionMetrics = new Map();
    }

    async analyzeAction(session, action) {
        const threats = [];

        // Check for XSS attempts
        if (this.detectXSSAttempt(action)) {
            threats.push('XSS_ATTEMPT');
        }

        // Check for suspicious selectors
        if (action.selector && this.detectSuspiciousSelector(action.selector)) {
            threats.push('SUSPICIOUS_SELECTOR');
        }

        // Check for automation detection evasion
        if (this.detectEvasionAttempt(action)) {
            threats.push('EVASION_ATTEMPT');
        }

        // Update session metrics
        this.updateSessionMetrics(session.id, action);

        // Check for anomalous behavior
        const anomalies = this.detectAnomalies(session.id);
        threats.push(...anomalies);

        if (threats.length > 0) {
            await this.handleThreats(session, action, threats);
        }

        return threats;
    }

    detectXSSAttempt(action) {
        const textToCheck = [action.selector, action.text, action.url].filter(Boolean);

        return textToCheck.some(text =>
            this.suspiciousPatterns.some(pattern => pattern.test(text))
        );
    }

    detectSuspiciousSelector(selector) {
        // Check for selectors that might be targeting security-sensitive elements
        const dangerousPatterns = [
            /\[type=["']?password["']?\]/i,
            /input\[name\*=["']?password/i,
            /\[autocomplete=["']?current-password/i
        ];

        return dangerousPatterns.some(pattern => pattern.test(selector));
    }

    detectEvasionAttempt(action) {
        // Detect attempts to evade bot detection
        if (action.type === 'type' && action.text) {
            // Extremely fast typing might indicate automation
            if (action.duration && action.duration < action.text.length * 10) {
                return true;
            }
        }

        return false;
    }

    updateSessionMetrics(sessionId, action) {
        if (!this.sessionMetrics.has(sessionId)) {
            this.sessionMetrics.set(sessionId, {
                actions: [],
                uniqueSelectors: new Set(),
                startTime: Date.now()
            });
        }

        const metrics = this.sessionMetrics.get(sessionId);
        metrics.actions.push({
            type: action.type,
            timestamp: Date.now()
        });

        if (action.selector) {
            metrics.uniqueSelectors.add(action.selector);
        }
    }

    detectAnomalies(sessionId) {
        const metrics = this.sessionMetrics.get(sessionId);
        if (!metrics) return [];

        const anomalies = [];
        const now = Date.now();
        const sessionDuration = now - metrics.startTime;

        // High request rate
        const recentActions = metrics.actions.filter(
            a => now - a.timestamp < 60000
        );

        if (recentActions.length > this.anomalyThresholds.requestsPerMinute) {
            anomalies.push('HIGH_REQUEST_RATE');
        }

        // Too many unique selectors (possible scraping)
        if (metrics.uniqueSelectors.size > this.anomalyThresholds.uniqueSelectorsPerSession) {
            anomalies.push('EXCESSIVE_SELECTORS');
        }

        return anomalies;
    }

    async handleThreats(session, action, threats) {
        const severity = this.calculateThreatSeverity(threats);

        // Log security event
        await auditLogger.logSecurityEvent('THREAT_DETECTED', {
            sessionId: session.id,
            threats,
            severity,
            action: {
                type: action.type,
                hasSelector: !!action.selector,
                hasText: !!action.text
            }
        });

        // Take action based on severity
        if (severity >= 8) {
            await this.terminateSession(session.id);
        } else if (severity >= 5) {
            await this.flagSession(session.id);
        }
    }

    calculateThreatSeverity(threats) {
        const severityMap = {
            'XSS_ATTEMPT': 9,
            'SUSPICIOUS_SELECTOR': 6,
            'EVASION_ATTEMPT': 4,
            'HIGH_REQUEST_RATE': 5,
            'EXCESSIVE_SELECTORS': 7
        };

        return Math.max(...threats.map(threat => severityMap[threat] || 1));
    }
}
```

## Security Checklist

### Pre-Production Security Review

- [ ] **WebSocket Security**
  - [ ] TLS encryption enabled in production
  - [ ] Client certificate validation implemented
  - [ ] Origin validation for WebSocket connections
  - [ ] Message authentication and integrity checks

- [ ] **Input Validation**
  - [ ] All inputs validated using Zod schemas
  - [ ] CSS selectors sanitized against XSS
  - [ ] URLs validated against safe protocols and domains
  - [ ] Text inputs length-limited and sanitized

- [ ] **Authentication & Authorization**
  - [ ] Session-based authentication implemented
  - [ ] Permission-based action authorization
  - [ ] Session timeouts and automatic cleanup
  - [ ] Proper session revocation on logout

- [ ] **Audit Logging**
  - [ ] All actions logged with timestamp and user context
  - [ ] Security events logged and monitored
  - [ ] Sensitive data properly redacted in logs
  - [ ] Log integrity protection implemented

- [ ] **Rate Limiting**
  - [ ] Per-client rate limiting implemented
  - [ ] Action-specific rate limits configured
  - [ ] Progressive penalties for violations
  - [ ] DoS protection mechanisms in place

- [ ] **Data Protection**
  - [ ] Sensitive data classification implemented
  - [ ] Encryption for data at rest and in transit
  - [ ] Secure key management practices
  - [ ] Data retention policies enforced

- [ ] **Monitoring & Detection**
  - [ ] Real-time threat detection implemented
  - [ ] Anomaly detection for suspicious behavior
  - [ ] Security alerts configured
  - [ ] Incident response procedures documented

- [ ] **Infrastructure Security**
  - [ ] Server hardening completed
  - [ ] Network security controls in place
  - [ ] Regular security updates applied
  - [ ] Backup and recovery procedures tested