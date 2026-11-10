/* Development-only smoke harness. Not shipped in Resources/Visuals. */
(async () => {
  const cases = [
    {
      type: 'mafs',
      spec: {
        viewport: { x: [-5, 5], y: [-2, 8] },
        curves: [{ expr: 'x^2' }],
        points: [{ x: 1, y: 1, label: 'P' }],
      },
    },
    {
      type: 'plotly',
      spec: { traces: [{ type: 'scatter', x: [1, 2, 3, 4], y: [1, 4, 9, 16], mode: 'lines+markers' }] },
    },
    {
      type: 'jsxgraph',
      spec: { viewport: { boundingbox: [-5, 5, 5, -5] }, functions: [{ expr: 'sin(x)' }] },
    },
    {
      type: 'mathbox',
      spec: { range: [[-3, 3], [-3, 3], [-3, 3]], surfaces: [{ expr: 'sin(x)*cos(y)', grid: 16 }] },
    },
    {
      type: 'molecule',
      spec: {
        format: 'pdb',
        data: 'ATOM      1  C   MOL A   1       0.000   0.000   0.000  1.00  0.00           C\n'
            + 'ATOM      2  O   MOL A   1       1.200   0.000   0.000  1.00  0.00           O\n',
        style: 'stick',
      },
    },
    { type: 'desmos', spec: { expressions: [{ latex: 'x^2' }] } },
    {
      type: 'tikz',
      spec: { source: '\\begin{tikzpicture}\\draw (0,0) circle (1in);\\end{tikzpicture}' },
    },
    // The tex case must do more than return ok: KaTeX can report success while drawing
    // nothing if its stylesheet or fonts are missing. `expect` is checked by the runner.
    {
      type: 'tex',
      spec: { latex: 'x = \\frac{-b \\pm \\sqrt{b^2 - 4ac}}{2a}', display: true },
    },
  ];
  const results = [];
  for (const c of cases) {
    try {
      const r = await window.LuminestVisuals.renderFromNative({
        type: c.type,
        spec: c.spec,
        config: { tikzAssets: true, desmosApiKey: '' },
        requestId: c.type,
      });
      results.push({ type: c.type, ok: !!r.ok, code: r.code || '', detail: (r.detail || '').slice(0, 180) });
      // A renderer can return ok and still draw nothing. For tex the failure mode is a
      // stylesheet that never loaded: KaTeX emits its MathML+HTML either way, but only
      // katex.min.css gives the root element its KaTeX_Main font and its width. Record
      // what the DOM actually contains so the runner can assert it.
      if (c.type === 'tex' && r.ok) {
        const el = document.querySelector('#stage .katex');
        results[results.length - 1].dom = {
          katex: !!el,
          fontFamily: el ? getComputedStyle(el).fontFamily : '',
          width: el ? Math.round(el.getBoundingClientRect().width) : 0,
          fonts: document.fonts ? document.fonts.size : 0,
        };
      }
    } catch (e) {
      results.push({ type: c.type, ok: false, code: 'THREW', detail: String(e && e.message || e).slice(0, 180) });
    }
  }
  document.title = 'SELFTEST_DONE';
  document.body.setAttribute('data-results', JSON.stringify(results));
  const pre = document.createElement('pre');
  pre.id = 'selftest-results';
  pre.textContent = 'SELFTEST_JSON:' + JSON.stringify(results);
  document.body.appendChild(pre);
})();
