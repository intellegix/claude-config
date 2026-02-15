# /cache-perplexity-session — Cache Perplexity Login for Council Commands

Capture Perplexity session state (cookies, localStorage, model preferences) from an already-authenticated browser session. Cached data is used by `/council-refine` and `/export-to-council` to skip fragile UI model-selector clicks.

**Prerequisites**: User must be logged into Perplexity in Chrome. Browser-bridge MCP server running with Chrome extension connected.

## Input

`$ARGUMENTS` = Ignored (no arguments needed).

## Workflow

### Step 1: Navigate to Perplexity
- `browser_navigate` to `https://www.perplexity.ai/`
- Wait 3 seconds for full page load (auth state must be hydrated)

### Step 2: Verify logged in
- Take a screenshot to confirm the user is logged in
- Look for indicators: user avatar, "New Thread" button, absence of "Sign in" button
- If NOT logged in, abort with message: "Please log into Perplexity in Chrome first, then re-run this command"

### Step 3: Read session cookies
- Use `browser_evaluate` to read cookies:
  ```javascript
  document.cookie
  ```
- Store the result as `cookies` string

### Step 4: Read localStorage preferences
- Use `browser_evaluate` to read relevant localStorage keys:
  ```javascript
  JSON.stringify(Object.fromEntries(
    Object.keys(localStorage)
      .filter(k => k.includes('session') || k.includes('model') || k.includes('user') || k.includes('auth') || k.includes('token') || k.includes('pplx') || k.includes('preference'))
      .map(k => [k, localStorage.getItem(k)])
  ))
  ```
- Parse the JSON result as `localStorageData`

### Step 5: Detect current model and council state
- **IMPORTANT**: Council is NOT in the model selector dropdown. It's a separate "Model council" button/chip in the input toolbar area.
- Use `browser_evaluate` to check for the council button:
  ```javascript
  (function() {
    const btn = [...document.querySelectorAll('button')].find(b => b.textContent.trim() === 'Model council');
    const modelBtn = document.querySelector('button[aria-label="Choose a model"]');
    const threeModels = document.querySelector('button[aria-label="3 models"]');
    return {
      councilButton: btn ? { found: true, classes: btn.className, active: btn.className.includes('bg-subtle') } : { found: false },
      modelSelector: modelBtn?.textContent?.trim() || 'not found',
      threeModelsDropdown: threeModels ? true : false
    };
  })()
  ```
- If council button found → `currentModel = "council"`
- If council button NOT found → `currentModel = modelSelector text`

### Step 6: Activate Council mode (if not already active)
- If council button was found but not active:
  ```javascript
  (function() { const btn = [...document.querySelectorAll('button')].find(b => b.textContent.trim() === 'Model council'); if (btn) { btn.click(); return { clicked: true }; } return { clicked: false }; })()
  ```
  - Wait 1s, take screenshot to verify
- If council button is already active: proceed (already in council mode)
- If council button NOT found: set `modelPreference = currentModel` and warn user that council requires Perplexity Max
- Set `modelPreference = "council"` if council is active, otherwise use detected model name

### Step 7: Read final state
- Re-read cookies and localStorage (model change may have updated them)
- Capture the current URL

### Step 8: Save session cache
- Write to `~/.claude/config/perplexity-session.json`:
  ```json
  {
    "cookies": "<cookie string>",
    "localStorage": { "<key>": "<value>", ... },
    "currentModel": "<detected model name>",
    "modelPreference": "council",
    "baseUrl": "https://www.perplexity.ai/",
    "cachedAt": "<ISO 8601 timestamp>",
    "expiresAt": "<ISO 8601 timestamp +24h>"
  }
  ```
- Use `Write` tool to create the file

### Step 9: Confirm and cleanup
- Report what was cached:
  - Number of cookies captured
  - Number of localStorage keys captured
  - Current model detected
  - Expiry time (24h from now)
- `browser_close_session` to close all session tabs

## Output Format

```
Session cached successfully!
- Cookies: {N} captured
- LocalStorage keys: {N} relevant keys
- Model: {currentModel}
- Expires: {expiresAt}
- Saved to: ~/.claude/config/perplexity-session.json

Council commands will now use this cached session to skip model selection UI.
Re-run /cache-perplexity-session if you get "session expired" warnings.
```

## Error Handling
- **Not logged in**: Abort with login instructions
- **Council not available**: Cache what's available, warn that council mode requires Max subscription
- **Cookie read blocked**: Some cookies are httpOnly and won't appear in `document.cookie` — this is expected. Cache what's readable.
- **Always** call `browser_close_session` on exit
