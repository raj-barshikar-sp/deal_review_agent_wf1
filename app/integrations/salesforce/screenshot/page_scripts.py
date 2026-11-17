"""JavaScript snippets run inside the Lightning report page."""


# Lightning hides the report in shadow DOM and sometimes an iframe.
_DEEP_QUERY_JS = """
function deepQuery(root, selector, out) {
  out = out || [];
  for (const n of root.querySelectorAll(selector)) out.push(n);
  for (const el of root.querySelectorAll('*')) {
    if (el.shadowRoot) deepQuery(el.shadowRoot, selector, out);
  }
  return out;
}
"""
_TOTAL_RECORDS_TILE_JS = (
    "const tile = deepQuery(document, '*').find(e => e.children.length === 0 "
    "&& (e.textContent || '').trim() === 'Total Records');"
)
REPORT_READY_JS = _DEEP_QUERY_JS + _TOTAL_RECORDS_TILE_JS + "return !!tile;"
REPORT_TOTAL_JS = _DEEP_QUERY_JS + _TOTAL_RECORDS_TILE_JS + r"""
if (!tile || !tile.parentElement) return null;
const m = tile.parentElement.innerText.match(/Total Records\s*([\d,]+)/);
return m ? parseInt(m[1].replace(/,/g, ''), 10) : null;
"""
REPORT_BOTTOM_JS = _DEEP_QUERY_JS + """
const tables = deepQuery(document, 'table');
if (!tables.length) return null;
return Math.ceil(Math.max(...tables.map(t => t.getBoundingClientRect().bottom)) + window.scrollY);
"""
DISMISS_POPUPS_JS = _DEEP_QUERY_JS + """
for (const b of deepQuery(document, 'button', [])) {
  const label = ((b.getAttribute('title') || '') + ' ' + (b.getAttribute('aria-label') || '') + ' ' + b.innerText).toLowerCase();
  let inPrompt = false;
  for (let n = b; n; n = n.parentNode || n.host) {
    if (n.nodeType === 1 && n.matches && n.matches('.forceInAppGuidance, .prompt, .docked-composer, section[role=dialog]')) inPrompt = true;
  }
  if (inPrompt && /close|dismiss|minimize/.test(label)) b.click();
}
"""
