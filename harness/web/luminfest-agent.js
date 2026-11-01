/* luminfest-agent.js — injected by the server into every served simulation.
 *
 * Runs INSIDE the sandboxed iframe (opaque origin: the iframe is served with
 * sandbox="allow-scripts" and deliberately NOT allow-same-origin, so the
 * workbench cannot reach into the sim's DOM and the sim cannot reach into the
 * workbench's storage). This script is the sim's only channel outward: it
 * observes hover/click and forwards selection payloads to the workbench parent
 * via postMessage. It sends nothing else and reads nothing sensitive — the
 * payload is plain geometry and text of what the learner pointed at.
 *
 * Message types (sim -> workbench):
 *   {type:'luminfest:ready'}                        the bridge is up
 *   {type:'luminfest:hover',  rect:{x,y,w,h}}       cursor moved over an element
 *   {type:'luminfest:select', selection:{...}}      learner clicked an element
 * Selection payload: {kind:'line'|'graph'|'asset'|'element',
 *                     selector, text, rect:{x,y,w,h}}  (see README).
 */
(function () {
  'use strict';

  var pendingHover = null;
  var hoverScheduled = false;

  function send(message) {
    try { window.parent.postMessage(message, '*'); } catch (e) { /* parent gone */ }
  }

  function idSelector(el) {
    if (el.id && /^[A-Za-z][\w-]*$/.test(el.id)) return '#' + el.id;
    return '';
  }

  function pathSelector(el) {
    var doc = el.ownerDocument;
    var parts = [];
    var node = el;
    for (var depth = 0; node && node !== doc.body && depth < 6; depth += 1) {
      var tag = node.tagName ? node.tagName.toLowerCase() : '*';
      var parent = node.parentElement;
      var index = 1;
      if (parent) {
        var same = Array.prototype.filter.call(parent.children, function (c) {
          return c.tagName === node.tagName;
        });
        if (same.length > 1) index = same.indexOf(node) + 1;
      }
      parts.unshift(index > 1 ? tag + ':nth-of-type(' + index + ')' : tag);
      node = parent;
    }
    return 'body ' + parts.join(' > ');
  }

  function classify(el) {
    var series = el.closest ? el.closest('[data-series]') : null;
    if (series) {
      return { kind: 'graph', root: series,
               selector: '[data-series="' + series.getAttribute('data-series') + '"]' };
    }
    var tag = el.tagName ? el.tagName.toLowerCase() : '';
    if (tag === 'img' || tag === 'image') {
      return { kind: 'asset', root: el, selector: idSelector(el) || pathSelector(el) };
    }
    if (tag === 'line' || tag === 'path' || tag === 'polyline') {
      return { kind: 'line', root: el, selector: idSelector(el) || pathSelector(el) };
    }
    return { kind: 'element', root: el, selector: idSelector(el) || pathSelector(el) };
  }

  function selectionFor(classified) {
    var root = classified.root;
    var rect = root.getBoundingClientRect();
    var label = classified.kind === 'graph'
      ? root.getAttribute('data-series')
      : (root.textContent || root.getAttribute('aria-label') || '').trim().slice(0, 120);
    return {
      kind: classified.kind,
      selector: classified.selector,
      text: label || '',
      rect: { x: Math.round(rect.x), y: Math.round(rect.y),
              w: Math.round(rect.width), h: Math.round(rect.height) },
    };
  }

  document.addEventListener('mousemove', function (event) {
    pendingHover = event.target;
    if (hoverScheduled) return;
    hoverScheduled = true;
    requestAnimationFrame(function () {
      hoverScheduled = false;
      if (!pendingHover) return;
      var classified = classify(pendingHover);
      var rect = classified.root.getBoundingClientRect();
      send({ type: 'luminfest:hover', selector: classified.selector,
             rect: { x: Math.round(rect.x), y: Math.round(rect.y),
                     w: Math.round(rect.width), h: Math.round(rect.height) } });
    });
  }, true);

  document.addEventListener('click', function (event) {
    // Links keep their default behaviour; everything else is a selection.
    if (event.target.closest && event.target.closest('a[href]')) return;
    event.preventDefault();
    var selection = selectionFor(classify(event.target));
    send({ type: 'luminfest:select', selection: selection });
  }, true);

  send({ type: 'luminfest:ready' });
})();
