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

// Collapse the notification tray on every page load so it never persists
// in the expanded state across refreshes. Retries until hass is ready
// (it loads asynchronously after the frontend bootstraps).
(function () {
  let retries = 0;
  function collapseNotificationTray() {
    const ha = document.querySelector("home-assistant");
    if (!ha || !ha.hass) {
      if (retries++ < 20) setTimeout(collapseNotificationTray, 250);
      return;
    }
    const state = ha.hass.states["input_boolean.notification_expanded"];
    if (state && state.state === "on") {
      ha.hass.callService("input_boolean", "turn_off", {
        entity_id: "input_boolean.notification_expanded",
      });
    }
  }
  collapseNotificationTray();
})();
