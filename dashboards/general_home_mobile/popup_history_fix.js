// When navigating away from a bubble-card popup (hash-based), rewrite the
// current history entry to strip the popup hash. Without this, browser/system
// back lands on the hash URL and reopens the popup.
const _pushState = history.pushState.bind(history);

history.pushState = function (state, title, url) {
  if (location.hash) {
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
    if (!ha || !ha.hass || !ha.hass.user) {
      if (retries++ < 20) setTimeout(collapseNotificationTray, 250);
      return;
    }
    const entity = ha.hass.user.name === '<entity_31>'
      ? 'input_boolean.notification_expanded_<entity_31>'
      : 'input_boolean.notification_expanded_<entity_32>';
    const state = ha.hass.states[entity];
    if (state && state.state === "on") {
      ha.hass.callService("input_boolean", "turn_off", {
        entity_id: entity,
      });
    }
  }
  collapseNotificationTray();
})();
