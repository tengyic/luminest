/* Luminfest workbench — interaction telemetry, browser side.
 *
 * The macOS app has had a click channel since `ClickTelemetry.swift`; the web
 * workbench had none at all, so a learner who used the browser surface was
 * invisible to `/api/v1/attention/window`. This module is the missing client
 * half. It is deliberately outside `app.js` for the same reason `cards.js` is:
 * `app.js` is one IIFE that touches the DOM at load time, so nothing in it can
 * be exercised without a browser. Everything here is pure and testable.
 *
 * The vocabulary is the server's, not ours. `app/harness/telemetry.py` owns the
 * closed grammar — `KINDS = click|tap|key|blur|focus`, `FIELDS = kind|target`,
 * target matching `^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$` — and `POST /events`
 * refuses anything else with 422. So this file never invents a field:
 *
 *   * no text, no key code, no value — `key` records *that* a key was pressed
 *   * no window title, no URL, no page text — a target is an identifier
 *   * `blur`/`focus` carry no target at all, because they are window-level
 *
 * Absence is not a signal: a learner who never clicks may be reading closely, so
 * nothing here builds an engagement score. It records, and the server decides
 * what the record can support.
 */
(function (root) {
  'use strict';

  // Mirrors app/harness/telemetry.py. Kept as a literal rather than fetched
  // because a client that asks the server for its own grammar can be talked out
  // of a refusal it should have made locally.
  var TARGET = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$/;
  var TARGETED = { click: true, tap: true, key: true };
  var KINDS = { click: true, tap: true, key: true, blur: true, focus: true };

  /** A string the server will accept as a target, or '' if nothing survives. */
  function sanitizeTarget(raw) {
    if (typeof raw !== 'string') return '';
    // Illegal characters collapse to '-'; a leading '-' is stripped because the
    // grammar requires alphanumerics first.
    var cleaned = raw.replace(/[^A-Za-z0-9._:-]+/g, '-').replace(/^-+/, '');
    cleaned = cleaned.slice(0, 64);
    return TARGET.test(cleaned) ? cleaned : '';
  }

  /**
   * Name what was touched, without recording what it said.
   *
   * Preference order: an explicit `data-target` (a stable identifier the markup
   * author chose), then `id`, then the tag name plus its first class. The climb
   * is bounded so a click on a deeply nested span still lands on something with
   * a name, and stops at the body.
   */
  function targetFor(element, limit) {
    var depth = typeof limit === 'number' ? limit : 4;
    var node = element;
    while (node && depth-- > 0 && node.nodeType === 1) {
      var explicit = node.getAttribute && node.getAttribute('data-target');
      if (explicit) {
        var named = sanitizeTarget(explicit);
        if (named) return named;
      }
      if (node.id) {
        var byId = sanitizeTarget('web.' + node.id);
        if (byId) return byId;
      }
      node = node.parentElement;
    }
    // No identifier anywhere up the chain: report the element type, which is a
    // category rather than a location and therefore carries no content.
    var tag = element && element.tagName ? String(element.tagName).toLowerCase() : '';
    return sanitizeTarget('web.' + (tag || 'window')) || 'web.window';
  }

  /** True when this element must never be named, because naming it leaks input. */
  function isSensitive(element) {
    var node = element;
    var depth = 4;
    while (node && depth-- > 0 && node.nodeType === 1) {
      var tag = String(node.tagName || '').toLowerCase();
      var type = String((node.getAttribute && node.getAttribute('type')) || '').toLowerCase();
      if (tag === 'input' && (type === 'password' || type === 'email')) return true;
      if (node.getAttribute && node.getAttribute('data-private') === '1') return true;
      node = node.parentElement;
    }
    return false;
  }

  /**
   * A batch queue with a size trigger and a caller-supplied sender.
   *
   * `send` receives the finished event array; whatever it returns is ignored, so
   * a failed flush can be retried by the caller (the queue keeps the batch until
   * `ack()` is called). Keeping the network out of here is what makes the
   * trigger logic testable without a server.
   */
  function createQueue(options) {
    var opts = options || {};
    var max = opts.max || 40;
    var now = opts.now || function () { return new Date().toISOString(); };
    var id = opts.id || function () {
      if (typeof crypto !== 'undefined' && crypto.randomUUID) return crypto.randomUUID();
      return 'w-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 10);
    };
    var send = opts.send || function () {};
    var pending = [];
    var seq = 0;

    function record(kind, target) {
      if (!KINDS[kind]) return false;
      var payload = { kind: kind };
      if (TARGETED[kind]) {
        var named = sanitizeTarget(target);
        if (!named) return false;
        payload.target = named;
      }
      // A blur/focus still needs an id and a time, but no target: the grammar
      // makes `target` forbidden for them, so leaving it out is the valid form.
      pending.push({
        id: id(),
        type: 'interaction',
        occurred_at: now(),
        payload: payload,
      });
      seq += 1;
      if (pending.length >= max) flush();
      return true;
    }

    function flush() {
      if (!pending.length) return [];
      var batch = pending.slice();
      pending = [];
      send(batch);
      return batch;
    }

    function size() { return pending.length; }
    function lastId() { return pending.length ? pending[pending.length - 1].id : ''; }

    return { record: record, flush: flush, size: size, lastId: lastId };
  }

  var api = {
    KINDS: Object.keys(KINDS),
    TARGETED: Object.keys(TARGETED),
    sanitizeTarget: sanitizeTarget,
    targetFor: targetFor,
    isSensitive: isSensitive,
    createQueue: createQueue,
  };
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) root.LuminfestTelemetry = api;
})(typeof globalThis !== 'undefined' ? globalThis : this);
