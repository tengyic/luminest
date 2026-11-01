/* Luminfest workbench — pure card helpers.
 *
 * These live outside app.js on purpose: app.js is one IIFE that touches the DOM at
 * load time, so nothing in it can be exercised without a browser. The merge below
 * used to be an inline loop that reassigned the `const` of a `for…of`, which threw
 * `TypeError: Assignment to constant variable` the first time an image card had a
 * cached sha — and took the rest of that result block down with it. It is a pure
 * function now, so it can be exercised from a console or a browser check without a
 * page load.
 *
 * The merge exists because a card names a picture by URL, while the authenticated
 * bytes route needs the cache sha. Media results carry both; the sha is mapped onto
 * the matching card so a downloaded image renders its local copy and an
 * embed-posture one its remote thumbnail. The backend half of that contract — every
 * media row carries `thumb_url` *and* `sha` for the same picture — is pinned by
 * `backend/tests/test_ta_media_feed.py`.
 */
(function (root) {
  'use strict';

  /**
   * @param {Array<object>} cards   teacher-assistant result cards
   * @param {Map<string,string>} shaByUrl  thumb_url -> cache sha
   * @returns {Array<object>} new array; the inputs are never mutated
   */
  function mergeCachedSha(cards, shaByUrl) {
    const merged = [];
    for (const card of cards || []) {
      if (card && card.kind === 'image' && !card.sha && shaByUrl && shaByUrl.has(card.url)) {
        merged.push(Object.assign({}, card, { sha: shaByUrl.get(card.url) }));
      } else {
        merged.push(card);
      }
    }
    return merged;
  }

  /** The same map the merge consumes, built from a result's `media` list. */
  function shaMapFromMedia(media) {
    const map = new Map();
    for (const item of media || []) {
      if (item && item.sha && item.thumb_url) map.set(item.thumb_url, item.sha);
    }
    return map;
  }

  const api = { mergeCachedSha, shaMapFromMedia };
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) root.LuminfestCards = api;
})(typeof globalThis !== 'undefined' ? globalThis : this);
