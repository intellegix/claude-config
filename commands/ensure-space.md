# /ensure-space — Add Current Perplexity Thread to Project Space

Ensure the current Perplexity thread is filed into a Space named after the active project. Creates the Space if it doesn't exist.

**Prerequisites**: Perplexity Max subscription. Browser-bridge MCP server running with Chrome extension connected. Active tab must be on a Perplexity thread page.

## Input

`$ARGUMENTS` = Optional space name override. If empty, derives from current working directory.

## Workflow

### Step 1: Determine Space Name

- If `$ARGUMENTS` is provided and non-empty, use it as the space name
- Otherwise, derive from the current working directory: use `path.basename(process.cwd())` (e.g., "Intellegix Chrome Ext")

### Step 2: Add to Space

- Call `browser_add_to_space` with:
  - `spaceName`: the determined space name
  - `createIfMissing: true`

### Step 3: Report Result

Based on the response:

- **`action: 'added'`** → Report: "Thread added to Space: {spaceName}"
- **`action: 'created'`** → Report: "Created new Space '{spaceName}' and added thread"
- **`action: 'no_match'` with `createIfMissing` failure** → Show available spaces, ask user to pick one or confirm creation
- **Error (`MENU_NOT_FOUND`, `ADD_TO_SPACE_NOT_FOUND`, `MODAL_NOT_FOUND`)** → Report the error and suggest the user check they're on a Perplexity thread page

## Error Handling

- If no browser tab is active or not on Perplexity, report clearly
- Do NOT call `browser_close_session` — this command operates on an existing tab, not a full session
