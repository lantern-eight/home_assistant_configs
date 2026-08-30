// Deployed to www/card_order.js and loaded by configuration.yaml's
// `frontend: extra_module_url:`.
// Bump the `?v=` on the configuration.yaml entry after any edit.
//
// HA's `type: sections` view renders conditional cards in YAML order,
// ignoring priority. card_mod can't reach the grid-item wrapper (it's
// above the card in the section's shadow DOM). This module bridges the
// gap: it reads a priority-sorted list from a sensor attribute and
// applies CSS `order` to the grid items so cards visually sort by
// priority without changing the YAML.
//
// The sensor attribute (card_order) is the source of truth — all
// priority logic lives in Jinja, this module just maps IDs to DOM
// elements and sets their CSS order.

const SENSOR_ID = 'sensor.dashboard_conditional_visible';
const HOME_PATH = '/general-home/home';

// Section index within the view — the conditional cards live in
// section 3 (0=bg overlay, 1=title/chips, 2=weather, 3=conditionals).
const SECTION_INDEX = 3;

// DOM child order of cards in the section. Must match dashboard.yaml's
// physical card order so index-to-ID mapping is correct.
const CARD_IDS = [
  'house_armed',
  'uv_index',
  'vacuums_heading',
  'vacuum_<entity_34>',
  'vacuum_<entity_35>',
  'soil_moisture'
];

let cachedCards = null;
let lastOrderKey = null;

// HA nests the grid items several shadow roots deep with no stable
// CSS selector path across versions, so we walk recursively.
function queryShadow(root, selector, depth) {
  if (depth <= 0) return [];
  const results = [...(root.querySelectorAll(selector) || [])];
  for (const element of root.querySelectorAll('*')) {
    if (element.shadowRoot) {
      results.push(...queryShadow(element.shadowRoot, selector, depth - 1));
    }
  }
  return results;
}

// Cached because the DOM structure doesn't change until navigation —
// re-walking shadow roots on every state change would be wasteful.
function findCards() {
  if (cachedCards) return cachedCards;

  const home_assistant = document.querySelector('home-assistant');
  if (!home_assistant || !home_assistant.shadowRoot) return null;

  const sections = queryShadow(home_assistant.shadowRoot, 'hui-grid-section', 10);
  if (sections.length <= SECTION_INDEX) return null;

  const section = sections[SECTION_INDEX];
  const sortable = section.shadowRoot
    && section.shadowRoot.querySelector('ha-sortable');
  const container = sortable && sortable.querySelector('.container');
  if (!container) return null;

  const divCards = container.querySelectorAll(':scope > div.card');
  if (divCards.length !== CARD_IDS.length) return null;

  cachedCards = {};
  CARD_IDS.forEach(function (id, index) {
    cachedCards[id] = divCards[index];
  });
  return cachedCards;
}

function applyOrder(hass) {
  if (location.pathname.indexOf(HOME_PATH) !== 0) return;

  const sensor = hass.states[SENSOR_ID];
  const order = sensor && sensor.attributes && sensor.attributes.card_order;
  if (!order || !Array.isArray(order)) return;

  // Skip DOM writes when nothing changed — the sensor fires on every
  // state_changed for this entity, but priorities only shift on actual
  // transitions.
  const key = order.join(',');
  if (key === lastOrderKey) return;

  const cards = findCards();
  if (!cards) return;

  lastOrderKey = key;
  order.forEach(function (id, index) {
    if (cards[id]) {
      cards[id].style.order = String(index);
    }
  });
}

function clearCache() {
  cachedCards = null;
  lastOrderKey = null;
}

(function init() {
  let retries = 0;

  // hass and its WebSocket connection load asynchronously after the
  // frontend shell renders, so we poll until they're available.
  function tryInit() {
    const home_assistant = document.querySelector('home-assistant');
    if (!home_assistant || !home_assistant.hass || !home_assistant.hass.connection) {
      if (retries++ < 30) setTimeout(tryInit, 250);
      return;
    }

    applyOrder(home_assistant.hass);

    home_assistant.hass.connection.subscribeEvents(function () {
      const home_assistant = document.querySelector('home-assistant');
      if (home_assistant && home_assistant.hass) applyOrder(home_assistant.hass);
    }, 'state_changed');

    // Navigation swaps the entire view subtree, so cached DOM refs
    // become stale. The delay gives the new view time to render.
    window.addEventListener('location-changed', function () {
      clearCache();
      setTimeout(function () {
        const home_assistant = document.querySelector('home-assistant');
        if (home_assistant && home_assistant.hass) applyOrder(home_assistant.hass);
      }, 500);
    });

    window.addEventListener('popstate', function () {
      clearCache();
      setTimeout(function () {
        const home_assistant = document.querySelector('home-assistant');
        if (home_assistant && home_assistant.hass) applyOrder(home_assistant.hass);
      }, 500);
    });
  }

  tryInit();
})();
