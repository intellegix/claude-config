# MCP (Model Context Protocol) Patterns

## Core MCP Architecture

### WebSocket Communication Pattern
```typescript
interface MCPMessage {
    id: string;
    method: string;
    params?: Record<string, unknown>;
    result?: unknown;
    error?: MCPError;
}

interface MCPError {
    code: number;
    message: string;
    data?: unknown;
}

// WebSocket bridge pattern
class WebSocketBridge {
    private ws: WebSocket | null = null;
    private messageQueue: MCPMessage[] = [];

    async connect(): Promise<Result<void>> {
        try {
            this.ws = new WebSocket('ws://localhost:8080');
            return Result.ok(undefined);
        } catch (error) {
            return Result.error(`Connection failed: ${error.message}`);
        }
    }

    async sendMessage(message: MCPMessage): Promise<Result<MCPMessage>> {
        if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
            return Result.error('WebSocket not connected');
        }

        return new Promise((resolve) => {
            const timeout = setTimeout(() => {
                resolve(Result.error('Request timeout'));
            }, 5000);

            const handler = (event: MessageEvent) => {
                const response = JSON.parse(event.data);
                if (response.id === message.id) {
                    clearTimeout(timeout);
                    this.ws!.removeEventListener('message', handler);
                    resolve(Result.ok(response));
                }
            };

            this.ws!.addEventListener('message', handler);
            this.ws!.send(JSON.stringify(message));
        });
    }
}
```

### Context Management Pattern
```javascript
class ContextManager {
    constructor() {
        this.db = new Database(':memory:');
        this.sessions = new Map();
        this.cleanupInterval = setInterval(() => this.cleanup(), 300000); // 5 min
    }

    async createSession(): Promise<Result<string>> {
        try {
            const sessionId = crypto.randomUUID();
            const stmt = this.db.prepare(`
                INSERT INTO sessions (id, created_at, last_accessed)
                VALUES (?, ?, ?)
            `);

            stmt.run(sessionId, Date.now(), Date.now());

            this.sessions.set(sessionId, {
                tabs: new Map(),
                context: {},
                lastAccessed: Date.now()
            });

            return Result.ok(sessionId);
        } catch (error) {
            return Result.error(`Session creation failed: ${error.message}`);
        }
    }

    async cleanup() {
        const cutoff = Date.now() - 3600000; // 1 hour

        for (const [sessionId, session] of this.sessions) {
            if (session.lastAccessed < cutoff) {
                try {
                    // Close database connections
                    this.db.prepare('DELETE FROM sessions WHERE id = ?').run(sessionId);
                    this.sessions.delete(sessionId);
                } catch (error) {
                    console.error(`Cleanup failed for session ${sessionId}:`, error);
                }
            }
        }
    }

    destroy() {
        if (this.cleanupInterval) {
            clearInterval(this.cleanupInterval);
        }

        try {
            this.db.close();
        } catch (error) {
            console.error('Database close error:', error);
        }
    }
}
```

## Result Pattern for MCP Operations

```typescript
class Result<T> {
    constructor(
        private _isSuccess: boolean,
        private _value?: T,
        private _error?: string
    ) {}

    static ok<T>(value: T): Result<T> {
        return new Result<T>(true, value);
    }

    static error<T>(error: string): Result<T> {
        return new Result<T>(false, undefined, error);
    }

    get isSuccess(): boolean {
        return this._isSuccess;
    }

    get isError(): boolean {
        return !this._isSuccess;
    }

    get value(): T {
        if (!this._isSuccess) {
            throw new Error('Cannot access value of failed Result');
        }
        return this._value!;
    }

    get error(): string {
        if (this._isSuccess) {
            throw new Error('Cannot access error of successful Result');
        }
        return this._error!;
    }

    map<U>(fn: (value: T) => U): Result<U> {
        if (this.isError) {
            return Result.error<U>(this.error);
        }
        return Result.ok(fn(this.value));
    }

    flatMap<U>(fn: (value: T) => Result<U>): Result<U> {
        if (this.isError) {
            return Result.error<U>(this.error);
        }
        return fn(this.value);
    }
}

// Usage in MCP operations
async function executeBrowserAction(action: BrowserAction): Promise<Result<ActionResult>> {
    return await contextManager.getSession(action.sessionId)
        .flatMap(session => validateAction(action))
        .flatMap(validAction => sendToExtension(validAction))
        .flatMap(response => parseActionResult(response));
}
```

## Database Connection Patterns

### SQLite with Proper Cleanup
```javascript
class DatabaseManager {
    constructor(path = ':memory:') {
        this.db = null;
        this.path = path;
        this.isConnected = false;
    }

    connect() {
        if (this.isConnected) return;

        try {
            this.db = new Database(this.path);
            this.isConnected = true;

            // Enable WAL mode for better concurrency
            this.db.exec('PRAGMA journal_mode = WAL');
            this.db.exec('PRAGMA synchronous = NORMAL');
            this.db.exec('PRAGMA cache_size = 1000');

            this.initTables();
        } catch (error) {
            throw new Error(`Database connection failed: ${error.message}`);
        }
    }

    initTables() {
        const schema = `
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                created_at INTEGER NOT NULL,
                last_accessed INTEGER NOT NULL,
                context TEXT
            );

            CREATE TABLE IF NOT EXISTS actions (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                action_type TEXT NOT NULL,
                params TEXT NOT NULL,
                result TEXT,
                timestamp INTEGER NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions (id)
            );

            CREATE INDEX IF NOT EXISTS idx_sessions_last_accessed
            ON sessions (last_accessed);
        `;

        this.db.exec(schema);
    }

    close() {
        if (this.db && this.isConnected) {
            try {
                this.db.close();
                this.isConnected = false;
                this.db = null;
            } catch (error) {
                console.error('Database close error:', error);
            }
        }
    }

    prepare(sql) {
        if (!this.isConnected) {
            throw new Error('Database not connected');
        }
        return this.db.prepare(sql);
    }
}
```

## Error Handling Patterns

### Comprehensive Error Types
```typescript
enum MCPErrorCode {
    CONNECTION_FAILED = 1001,
    SESSION_NOT_FOUND = 1002,
    INVALID_ACTION = 1003,
    EXTENSION_ERROR = 1004,
    TIMEOUT = 1005,
    DATABASE_ERROR = 1006,
    VALIDATION_ERROR = 1007
}

class MCPError extends Error {
    constructor(
        public code: MCPErrorCode,
        message: string,
        public context?: Record<string, unknown>
    ) {
        super(message);
        this.name = 'MCPError';
    }

    static connectionFailed(details: string): MCPError {
        return new MCPError(
            MCPErrorCode.CONNECTION_FAILED,
            `Connection failed: ${details}`
        );
    }

    static sessionNotFound(sessionId: string): MCPError {
        return new MCPError(
            MCPErrorCode.SESSION_NOT_FOUND,
            `Session not found: ${sessionId}`,
            { sessionId }
        );
    }

    static timeout(operation: string): MCPError {
        return new MCPError(
            MCPErrorCode.TIMEOUT,
            `Operation timed out: ${operation}`,
            { operation, timeout: 5000 }
        );
    }
}

// Error handling wrapper
function withErrorHandling<T>(
    operation: () => Promise<T>,
    context: string
): Promise<Result<T>> {
    return operation()
        .then(result => Result.ok(result))
        .catch(error => {
            console.error(`${context} failed:`, error);

            if (error instanceof MCPError) {
                return Result.error(error.message);
            }

            return Result.error(`${context}: ${error.message}`);
        });
}
```

## Testing Patterns

### MCP Server Testing
```javascript
class MCPTestSuite {
    constructor() {
        this.testDb = new Database(':memory:');
        this.mockExtension = new MockExtension();
    }

    async setUp() {
        this.server = new MCPServer({
            database: this.testDb,
            extension: this.mockExtension
        });
        await this.server.start();
    }

    async tearDown() {
        await this.server.stop();
        this.testDb.close();
    }

    async testSessionCreation() {
        const result = await this.server.createSession();
        assert(result.isSuccess);
        assert(typeof result.value === 'string');

        // Verify session exists in database
        const session = this.testDb
            .prepare('SELECT * FROM sessions WHERE id = ?')
            .get(result.value);
        assert(session !== undefined);
    }

    async testActionExecution() {
        const sessionResult = await this.server.createSession();
        assert(sessionResult.isSuccess);

        const action = {
            sessionId: sessionResult.value,
            type: 'click',
            selector: '#test-button'
        };

        const result = await this.server.executeAction(action);
        assert(result.isSuccess);
        assert(this.mockExtension.lastAction.selector === '#test-button');
    }
}
```

## Performance Patterns

### Connection Pooling
```javascript
class ConnectionPool {
    constructor(maxConnections = 10) {
        this.pool = [];
        this.activeConnections = new Set();
        this.maxConnections = maxConnections;
        this.waitingQueue = [];
    }

    async getConnection(): Promise<WebSocket> {
        if (this.pool.length > 0) {
            const connection = this.pool.pop();
            this.activeConnections.add(connection);
            return connection;
        }

        if (this.activeConnections.size < this.maxConnections) {
            const connection = await this.createConnection();
            this.activeConnections.add(connection);
            return connection;
        }

        // Wait for connection to become available
        return new Promise((resolve) => {
            this.waitingQueue.push(resolve);
        });
    }

    releaseConnection(connection: WebSocket) {
        this.activeConnections.delete(connection);

        if (this.waitingQueue.length > 0) {
            const waiting = this.waitingQueue.shift();
            this.activeConnections.add(connection);
            waiting(connection);
        } else {
            this.pool.push(connection);
        }
    }

    async createConnection(): Promise<WebSocket> {
        return new Promise((resolve, reject) => {
            const ws = new WebSocket('ws://localhost:8080');
            ws.onopen = () => resolve(ws);
            ws.onerror = reject;
        });
    }
}
```

## Security Patterns

### Input Validation
```typescript
import { z } from 'zod';

const SessionActionSchema = z.object({
    sessionId: z.string().uuid(),
    type: z.enum(['click', 'type', 'navigate', 'screenshot']),
    selector: z.string().optional(),
    text: z.string().optional(),
    url: z.string().url().optional()
});

type SessionAction = z.infer<typeof SessionActionSchema>;

function validateAction(input: unknown): Result<SessionAction> {
    try {
        const action = SessionActionSchema.parse(input);
        return Result.ok(action);
    } catch (error) {
        return Result.error(`Validation failed: ${error.message}`);
    }
}

// XSS Prevention
function sanitizeSelector(selector: string): string {
    // Only allow safe CSS selectors
    const safePattern = /^[a-zA-Z0-9\-_#.\[\]="':() ]+$/;
    if (!safePattern.test(selector)) {
        throw new Error('Invalid selector characters');
    }
    return selector;
}
```

## Deployment Patterns

### Environment Configuration
```javascript
// .env.example
/*
MCP_SERVER_PORT=8080
DATABASE_URL=postgresql://localhost:5432/mcp_browser
LOG_LEVEL=info
EXTENSION_TIMEOUT=5000
CLEANUP_INTERVAL=300000
MAX_SESSIONS=100
*/

class Config {
    static load() {
        require('dotenv').config();

        return {
            port: parseInt(process.env.MCP_SERVER_PORT || '8080'),
            databaseUrl: process.env.DATABASE_URL || ':memory:',
            logLevel: process.env.LOG_LEVEL || 'info',
            extensionTimeout: parseInt(process.env.EXTENSION_TIMEOUT || '5000'),
            cleanupInterval: parseInt(process.env.CLEANUP_INTERVAL || '300000'),
            maxSessions: parseInt(process.env.MAX_SESSIONS || '100')
        };
    }
}
```

## Usage Guidelines

1. **Always use Result pattern** for operations that can fail
2. **Implement proper cleanup** for database connections and sessions
3. **Validate all inputs** using Zod schemas
4. **Use connection pooling** for production deployments
5. **Log errors comprehensively** but never log sensitive data
6. **Test both success and failure paths** in unit tests
7. **Handle timeouts gracefully** with configurable values
8. **Implement proper session management** with automatic cleanup