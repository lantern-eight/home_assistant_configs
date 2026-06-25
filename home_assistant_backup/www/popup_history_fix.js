// When navigating away from a bubble-card popup (hash-based), rewrite the
// current history entry to strip the popup hash. Without this, browser/system
// back lands on the hash URL and reopens the popup.
const POPUP_HASHES = new Set(["#more", "#rooms"]);
const _pushState = history.pushState.bind(history);

history.pushState = function (state, title, url) {
  if (POPUP_HASHES.has(location.hash)) {
    history.replaceState(null, "", location.pathname);
  }
  return _pushState(state, title, url);
};
