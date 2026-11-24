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
# Pixels of the report table hidden by its container. Measured on the table itself:
# Salesforce parks a 500px Chatter panel off-screen, which never fits and must not count.
REPORT_OVERFLOW_JS = _DEEP_QUERY_JS + """
const tables = deepQuery(document, 'table');
if (!tables.length) return 0;
const table = tables.reduce((a, b) => (b.scrollWidth > a.scrollWidth ? b : a));
for (let n = table.parentNode; n; n = n.parentNode || n.host) {
  if (n.nodeType === 1 && n.clientWidth && n.clientWidth < table.scrollWidth) return table.scrollWidth - n.clientWidth;
}
return Math.max(0, table.getBoundingClientRect().right - window.innerWidth);
"""
# Named column headers of the report table: how many exist and how many sit fully on screen.
REPORT_COLUMNS_JS = _DEEP_QUERY_JS + """
const tables = deepQuery(document, 'table');
if (!tables.length) return {total: 0, visible: 0};
const table = tables.reduce((a, b) => (b.scrollWidth > a.scrollWidth ? b : a));
const heads = [...table.querySelectorAll('thead th, tr:first-child th')].filter(h => (h.innerText || '').trim());
let clip = window.innerWidth;
for (let n = table.parentNode; n; n = n.parentNode || n.host) {
  if (n.nodeType === 1 && n.clientWidth) { clip = Math.min(clip, n.getBoundingClientRect().left + n.clientWidth); }
}
return {total: heads.length, visible: heads.filter(h => h.getBoundingClientRect().right <= clip + 1).length};
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
