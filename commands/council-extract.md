# /council-extract — Extract Model Council Response to Markdown

Extract a completed Perplexity Model Council response from the current browser tab, converting it to structured markdown with model attribution, and save to disk.

## Input

`$ARGUMENTS` = Optional output filename or tabId. Defaults to timestamped name. If a number, treated as tabId.

## Prerequisites

- Browser-bridge MCP server running with Chrome extension connected
- A completed Model Council response visible in an active Perplexity tab
- Read `~/.claude/perplexity-selectors.json` for CSS selectors

## Workflow

### Step 1: Identify the target tab

- `browser_get_tabs` to find tabs with `perplexity.ai` URLs
- If `$ARGUMENTS` is a number, use that as the specific tabId
- Otherwise use the most recently active Perplexity tab in the current session group
- If no Perplexity tab found, error: "No Perplexity tab found. Navigate to a council response first."
- Store the target `tabId` for all subsequent tool calls

### Step 2: DOM Recon (adaptive selector discovery)

Run `browser_evaluate` on the target tab with this script to discover the actual DOM structure:

```javascript
(() => {
  const results = {
    proseBlocks: document.querySelectorAll('.prose').length,
    proseFallback: document.querySelectorAll("[class*='prose']").length,
    modelNames: [],
    modelRows: [],
    completedIndicators: 0,
    thinkingSteps: 0,
    hasCloseButton: false,
    hasThreeDotMenu: false,
    pageUrl: location.href,
    pageTitle: document.title,
    queryText: ''
  };

  // Find model name elements — look for short text matching known model patterns
  const MODEL_PATTERNS = [/Claude/i, /GPT/i, /Gemini/i, /Llama/i, /Grok/i, /Mistral/i, /Sonar/i, /DeepSeek/i];
  document.querySelectorAll('div, span').forEach(el => {
    const text = el.textContent?.trim();
    if (text && text.length < 40 && MODEL_PATTERNS.some(p => p.test(text))) {
      // Check this isn't a huge container — should be a leaf-ish element
      if (el.children.length <= 3 && !results.modelNames.includes(text)) {
        results.modelNames.push(text);
      }
    }
  });

  // Try configured selectors
  const selectors = {
    councilModelRow: "[class*='interactable'][class*='appearance-none']",
    councilModelRowFallback: "[class*='gap-x-xs'][class*='items-center']",
    councilModelName: "div[class*='font-sans'][class*='text-xs'][class*='font-medium']",
    councilCompletedIndicator: "[class*='Completed'], svg[class*='check']",
    councilThinkingSteps: "[class*='steps']",
    councilPanelClose: "button[aria-label='Close']",
    councilThreeDotMenu: "button[aria-label='More'], [class*='overflow']"
  };

  results.modelRows = document.querySelectorAll(selectors.councilModelRow).length ||
    document.querySelectorAll(selectors.councilModelRowFallback).length;
  results.completedIndicators = document.querySelectorAll(selectors.councilCompletedIndicator).length;
  results.thinkingSteps = document.querySelectorAll(selectors.councilThinkingSteps).length;
  results.hasCloseButton = !!document.querySelector(selectors.councilPanelClose);
  results.hasThreeDotMenu = !!document.querySelector(selectors.councilThreeDotMenu);

  // Try to extract query text from the page
  const askInput = document.querySelector('#ask-input');
  if (askInput) results.queryText = askInput.textContent?.trim() || '';
  // Also try the first user message block
  if (!results.queryText) {
    const userMsg = document.querySelector('[class*="query"], [class*="question"]');
    if (userMsg) results.queryText = userMsg.textContent?.trim().slice(0, 200) || '';
  }

  return results;
})()
```

Log which selectors matched — this validates the config and adapts on the fly. If `proseBlocks === 0`, warn: "No .prose blocks found — page may not have a council response loaded."

### Step 3: Two-Phase Streaming Wait (with timing)

Record the start timestamp using `browser_evaluate`: `Date.now()` → store as `startTime`.

**Phase A** — Wait for model panels to show "Completed":

Run `browser_evaluate` on the target tab with a polling script:

```javascript
(() => {
  const indicators = document.querySelectorAll("[class*='Completed'], svg[class*='check'], [class*='complete']");
  const modelCount = document.querySelectorAll("[class*='interactable'][class*='appearance-none']").length ||
    document.querySelectorAll("[class*='gap-x-xs'][class*='items-center']").length || 3;
  return { completed: indicators.length, expected: modelCount, ready: indicators.length >= modelCount };
})()
```

If `ready === false`, wait 3 seconds and re-run the check. Repeat up to 40 times (120s total). If still not ready after timeout, proceed anyway — extract whatever is available and note the warning.

After Phase A completes, record `modelsCompleteTime = Date.now()` via `browser_evaluate`. Log: "Models completed in {modelsCompleteTime - startTime}ms".

**Phase B** — Wait for synthesis to stabilize:

Use `browser_wait_for_stable` on the target tab:
- `selector`: `.prose:first-of-type` (or the `councilSynthesis` selector from config)
- `stableMs`: 10000
- `timeout`: 120000
- `pollInterval`: 2000

After Phase B completes, record `synthesisStableTime = Date.now()` via `browser_evaluate`. Log: "Synthesis stabilized in {synthesisStableTime - startTime}ms total ({synthesisStableTime - modelsCompleteTime}ms after models)".

Store all three timestamps (`startTime`, `modelsCompleteTime`, `synthesisStableTime`) for inclusion in the output YAML frontmatter.

If both phases pass, proceed. If timeout on either phase, log a warning and continue extraction with whatever content is available.

### Step 4: Extract Synthesis

Run `browser_evaluate` on the target tab with the HTML-to-Markdown converter IIFE:

```javascript
(() => {
  function htmlToMd(node) {
    if (!node) return '';
    if (node.nodeType === 3) return node.textContent || '';
    if (node.nodeType !== 1) return '';

    const tag = node.tagName?.toLowerCase();
    const children = () => Array.from(node.childNodes).map(htmlToMd).join('');

    switch (tag) {
      case 'h1': return '\n# ' + children().trim() + '\n\n';
      case 'h2': return '\n## ' + children().trim() + '\n\n';
      case 'h3': return '\n### ' + children().trim() + '\n\n';
      case 'h4': return '\n#### ' + children().trim() + '\n\n';
      case 'h5': return '\n##### ' + children().trim() + '\n\n';
      case 'h6': return '\n###### ' + children().trim() + '\n\n';
      case 'p': return children().trim() + '\n\n';
      case 'br': return '\n';
      case 'hr': return '\n---\n\n';
      case 'strong': case 'b': return '**' + children().trim() + '**';
      case 'em': case 'i': return '*' + children().trim() + '*';
      case 'code': {
        if (node.parentElement?.tagName?.toLowerCase() === 'pre') return children();
        return '`' + children().trim() + '`';
      }
      case 'pre': {
        const codeEl = node.querySelector('code');
        const langClass = codeEl?.className?.match(/language-(\w+)/);
        const lang = langClass ? langClass[1] : '';
        const code = codeEl ? codeEl.textContent : node.textContent;
        return '\n```' + lang + '\n' + code + '\n```\n\n';
      }
      case 'a': {
        const href = node.getAttribute('href');
        const text = children().trim();
        return href ? '[' + text + '](' + href + ')' : text;
      }
      case 'blockquote': {
        const lines = children().trim().split('\n');
        return '\n' + lines.map(l => '> ' + l).join('\n') + '\n\n';
      }
      case 'ul': {
        return '\n' + Array.from(node.children).map(li => {
          if (li.tagName?.toLowerCase() === 'li') return '- ' + htmlToMd(li).trim();
          return htmlToMd(li);
        }).join('\n') + '\n\n';
      }
      case 'ol': {
        return '\n' + Array.from(node.children).map((li, i) => {
          if (li.tagName?.toLowerCase() === 'li') return (i + 1) + '. ' + htmlToMd(li).trim();
          return htmlToMd(li);
        }).join('\n') + '\n\n';
      }
      case 'li': return children();
      case 'table': {
        const rows = Array.from(node.querySelectorAll('tr'));
        if (!rows.length) return children();
        const result = [];
        rows.forEach((row, ri) => {
          const cells = Array.from(row.querySelectorAll('th, td')).map(c => htmlToMd(c).trim());
          result.push('| ' + cells.join(' | ') + ' |');
          if (ri === 0) result.push('| ' + cells.map(() => '---').join(' | ') + ' |');
        });
        return '\n' + result.join('\n') + '\n\n';
      }
      case 'details': {
        node.open = true; // expand it
        const summary = node.querySelector('summary');
        const summaryText = summary ? htmlToMd(summary).trim() : 'Details';
        const body = Array.from(node.childNodes)
          .filter(n => n !== summary)
          .map(htmlToMd).join('');
        return '\n<details>\n<summary>' + summaryText + '</summary>\n\n' + body.trim() + '\n</details>\n\n';
      }
      case 'summary': return children();
      case 'img': {
        const alt = node.getAttribute('alt') || '';
        const src = node.getAttribute('src') || '';
        return '![' + alt + '](' + src + ')';
      }
      case 'sup': return '<sup>' + children() + '</sup>';
      case 'sub': return '<sub>' + children() + '</sub>';
      case 'del': case 's': return '~~' + children().trim() + '~~';
      case 'div': case 'section': case 'article': case 'main': case 'span':
        return children();
      default: return children();
    }
  }

  // Find synthesis block — first .prose in the response area
  const proseBlocks = document.querySelectorAll('.prose');
  const synthesis = proseBlocks.length > 0 ? proseBlocks[0] : null;

  if (!synthesis) {
    // Try fallback
    const fallback = document.querySelector("[class*='prose']:first-of-type");
    if (fallback) {
      return {
        synthesis: htmlToMd(fallback),
        rawLength: fallback.textContent?.length || 0,
        metadata: { url: location.href, title: document.title, timestamp: new Date().toISOString() }
      };
    }
    return { synthesis: '', rawLength: 0, error: 'No .prose blocks found' };
  }

  return {
    synthesis: htmlToMd(synthesis),
    rawLength: synthesis.textContent?.length || 0,
    metadata: {
      url: location.href,
      title: document.title,
      modelCount: proseBlocks.length,
      timestamp: new Date().toISOString()
    }
  };
})()
```

Store the returned `synthesis` markdown and `metadata`.

### Step 5: Extract Individual Model Responses

Based on the model names discovered in Step 2, extract each model's individual response.

For each model discovered:

**5a.** Run `browser_evaluate` to find and click the model's panel row:

```javascript
(() => {
  const MODEL_PATTERNS = [/Claude/i, /GPT/i, /Gemini/i, /Llama/i, /Grok/i, /Mistral/i, /Sonar/i, /DeepSeek/i];
  const rows = document.querySelectorAll("[class*='interactable'][class*='appearance-none']");
  if (!rows.length) {
    // Try fallback selector
    const fallbackRows = document.querySelectorAll("[class*='gap-x-xs'][class*='items-center']");
    // Find the one matching model name index N
  }
  // Click the Nth model row (pass modelIndex as parameter)
  const row = rows[MODEL_INDEX];
  if (row) { row.click(); return { clicked: true }; }
  return { clicked: false, error: 'Model row not found at index ' + MODEL_INDEX };
})()
```

Replace `MODEL_INDEX` with the actual index (0, 1, 2) for each model.

**5b.** Wait 1.5 seconds for the side panel to render.

**5c.** Run `browser_evaluate` with the same `htmlToMd` converter to extract the model's full response from the side panel:

```javascript
(() => {
  // The htmlToMd function (same as Step 4 — inline it again or reference)
  function htmlToMd(node) { /* ... same converter ... */ }

  // The side panel typically shows as the last/second .prose block
  const proseBlocks = document.querySelectorAll('.prose');
  // The panel content is usually the last .prose or a .prose inside a drawer/panel
  const panelProse = proseBlocks.length > 1 ? proseBlocks[proseBlocks.length - 1] : null;

  if (!panelProse) return { content: '', error: 'No panel prose found' };

  const md = htmlToMd(panelProse);
  return {
    content: md.length > 100000 ? md.slice(0, 100000) + '\n\n[Truncated - ' + md.length + ' chars total]' : md,
    rawLength: panelProse.textContent?.length || 0
  };
})()
```

**5d.** Run `browser_evaluate` to close the side panel:

```javascript
(() => {
  const closeBtn = document.querySelector("button[aria-label='Close']");
  if (closeBtn) { closeBtn.click(); return { closed: true }; }
  // Try pressing Escape as fallback
  document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
  return { closed: false, fallback: 'escape' };
})()
```

**5e.** Wait 0.5 seconds before next model.

**5f.** Store `{ name: modelNames[i], content: extractedMarkdown }`.

If panel click/extraction fails for any model, log a warning and continue with the others. The synthesis already contains all models' perspectives.

### Step 6: Native Export (primary) or Fallback

**Primary method**: Call `browser_export_council_md` to trigger Perplexity's native "Export as Markdown" download.

If `exported: true`:
- Use Bash to find the most recently downloaded `.md` file in `~/Downloads/`:
  ```bash
  ls -t ~/Downloads/*.md 2>/dev/null | head -1
  ```
- Read the downloaded file and use its content as the authoritative extraction
- Note `extraction_method: "native_export"` in metadata

If native export fails (returns `success: false` or `MENU_NOT_FOUND` / `EXPORT_NOT_FOUND`):
- Fall back to the `browser_evaluate` IIFE extraction from Steps 4-5
- If Steps 4-5 also produced < 500 chars, extract raw `.textContent` from all `.prose` blocks:

```javascript
(() => {
  return Array.from(document.querySelectorAll('.prose'))
    .map((el, i) => '## Section ' + (i + 1) + '\n\n' + el.textContent)
    .join('\n\n---\n\n');
})()
```

Note `extraction_method: "evaluate"` or `extraction_method: "textContent_fallback"` in metadata accordingly.

### Step 7: Assemble Markdown Document

Build the output `.md` file with this structure:

```markdown
---
schema: council_md_v1
date: {ISO timestamp from metadata}
url: {page URL from metadata}
models: [{comma-separated model names from Step 2/5}]
extraction_method: {evaluate|native_export|textContent_fallback}
timing:
  models_complete_ms: {modelsCompleteTime - startTime, or null if not measured}
  synthesis_stable_ms: {synthesisStableTime - modelsCompleteTime, or null}
  total_ms: {synthesisStableTime - startTime, or null}
---

# Model Council Response

## Query
{extracted query text from Step 2 recon, or from page title}

---

## Synthesis
{converted markdown from Step 4}

---

## Model 1: {name}
{converted markdown from Step 5}

---

## Model 2: {name}
{converted markdown from Step 5}

---

## Model 3: {name}
{converted markdown from Step 5}
```

If individual model extraction failed for some models, include only those that succeeded. If no individual models were extracted, just include the Synthesis section.

### Step 8: Save to Disk

- Directory: `~/.claude/council-logs/`
- Create directory if it doesn't exist (use Bash `mkdir -p`)
- Filename format: `{YYYY-MM-DD_HHmm}-council-extract-{sanitized-query-slug}.md`
  - Sanitize query: take first 40 chars, replace spaces with `-`, remove non-alphanumeric except hyphens, lowercase
  - If no query text available, use `unknown-query`
  - If `$ARGUMENTS` provided a non-numeric string, use that as the filename stem instead
- Write the assembled markdown using the Write tool

### Step 9: Return Summary (NOT full content)

**CRITICAL**: Do NOT return the full markdown document to the Claude Code conversation context. This prevents 10-20K token cost explosion on every subsequent message.

Return ONLY:
- File path where the full `.md` was saved
- 200-word summary of key findings from the synthesis
- Model names discovered and which were successfully extracted
- Extraction method used (`evaluate`, `native_export`, or `textContent_fallback`)
- Any warnings (incomplete models, selector mismatches, timeouts)
- Character count of the full document

Format:

```
### Council Extraction Complete

**Saved to**: `~/.claude/council-logs/{filename}.md`
**Size**: {N} characters ({M} words approx)
**Models**: {model1}, {model2}, {model3}
**Extraction**: {method} ({X}/{Y} models individually extracted)

**Key Findings Summary** (from synthesis):
{200-word summary of the council's synthesis section}

**Timing**: Models completed in {N}s, synthesis stable in {M}s, total {T}s
**Warnings**: {any issues encountered, or "None"}
```

## Error Handling

- **No Perplexity tab found**: Error immediately — "No Perplexity tab found. Navigate to a council response first."
- **No .prose blocks found**: Take a screenshot for debugging, report what the page shows
- **Selector not found**: Try fallback selectors from config, then screenshot, then report
- **Model panel won't open**: Skip that model, log warning, continue with others
- **Native export also fails**: Extract raw `.textContent` from all `.prose` blocks as last resort
- **Clipboard read denied**: Fall back to `.textContent` extraction
- **Always report** what was extracted vs what was expected
- **No browser_close_session** — this command extracts from an existing tab, doesn't manage tab lifecycle. The calling command (`/export-to-council` or `/council-refine`) handles cleanup.

## Notes

- The `htmlToMd` converter IIFE must be inlined in each `browser_evaluate` call since it runs in a fresh page context each time (no persistent state between evaluations)
- CDP `Runtime.evaluate` has no character limit — unlike `browser_extract_data` which caps at 5000 chars
- The `maxMessageSize` on the WebSocket is 50MB, so even massive responses won't be truncated in transit
- Model panel extraction is best-effort — the synthesis already contains all models' perspectives
- This command is designed to be called by other commands (`/export-to-council`, `/council-refine`) or standalone
