// Deployed to www/popup_history_fix.js and loaded by configuration.yaml's
// `frontend: extra_module_url:`.
//
// HA serves /local/ with `Cache-Control: public, max-age=2678400` — 31 days — and
// extra_module_url names this file with no version string, so a browser that has
// loaded the page once, keeps running its cached copy for a month, and never
// revalidates.
//
// In /local/popup_history_fix.js, bump the `?v=` on the entry in configuration.yaml
// for any change. This query string makes a browser re-fetch.
//
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
    // Test every property this function goes on to dereference, `states` and
    // `user` are populated independently. There is a window where `hass` exists
    // with `states` still null.
    if (!ha || !ha.hass || !ha.hass.states || !ha.hass.user) {
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
