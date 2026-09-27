/* Presents /api/current. Averages, counts, ranks and colours are all calculated by the API. */
'use strict';

const REFRESH_MS = 60000;
const SOURCE = 'municipalities';
const POINTS = 'unmapped-places';
// OpenFreeMap provides context; municipality rendering falls back to a local background if either
// its style or tiles are unavailable.
function localStyle(background) {
  return { version: 8, sources: {}, layers: [{ id: 'background', type: 'background', paint: { 'background-color': background } }] };
}
const MAP_THEMES = {
  light: { basemap: 'https://tiles.openfreemap.org/styles/positron', fallback: localStyle('#f2f4f5'), empty: '#e2e7ea', edge: '#ffffff', emptyEdge: '#9aa7b0', focus: '#16212b' },
  dark: { basemap: 'https://tiles.openfreemap.org/styles/dark', fallback: localStyle('#161f26'), empty: '#3b4a55', edge: '#0f171d', emptyEdge: '#51626f', focus: '#ffffff' },
};
// Plain-language names for the quartile colours the API assigns, lowest to highest.
const BANDS = [
  { color: '#367c59', label: 'lowest 25%' },
  { color: '#8fab63', label: '25–50%' },
  { color: '#d7a83e', label: '50–75%' },
  { color: '#b9553f', label: 'highest 25%' },
];
const POLLUTANTS = {
  pm25: { formula: 'PM<sub>2.5</sub>', text: 'PM2.5', name: 'Fine particles' },
  pm10: { formula: 'PM<sub>10</sub>', text: 'PM10', name: 'Inhalable particles' },
  no2: { formula: 'NO<sub>2</sub>', text: 'NO₂', name: 'Nitrogen dioxide' },
  o3: { formula: 'O<sub>3</sub>', text: 'O₃', name: 'Ozone' },
  so2: { formula: 'SO<sub>2</sub>', text: 'SO₂', name: 'Sulphur dioxide' },
  co: { formula: 'CO', text: 'CO', name: 'Carbon monoxide' },
};
const POLLUTANT_ORDER = Object.keys(POLLUTANTS);
const ICON_BACK = '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M10 3 5 8l5 5"/></svg>';

const state = {
  data: { cities: [], freshness: {} },
  cityIndex: new Map(),
  geometry: null,
  features: new Map(),
  bounds: null,
  pollutant: null,
  view: 'map',
  selected: null,
  hovered: null,
  map: null,
  mapReady: null,
  mapBuilt: false,
  popup: null,
  callout: null,
  home: null,
  theme: 'light',
  searchIndex: null,
  searchMatches: [],
  searchActive: -1,
};

const byId = (id) => document.getElementById(id);
const escapeHtml = (value) => String(value ?? '').replace(/[&<>'"]/g, (character) => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;',
})[character]);
const normalise = (text) => String(text).normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
const countFormat = new Intl.NumberFormat('en-GB');
const plural = (count, word) => `${countFormat.format(count)} ${word}${count === 1 ? '' : 's'}`;
const motionAllowed = () => !window.matchMedia('(prefers-reduced-motion: reduce)').matches;
const isStacked = () => window.matchMedia('(max-width: 900px)').matches;

function formatValue(value) {
  const digits = Math.abs(value) >= 10 ? 1 : 2;
  return new Intl.NumberFormat('en-GB', { minimumFractionDigits: digits, maximumFractionDigits: digits }).format(value);
}

function formatTime(value) {
  if (!value) return '—';
  return new Intl.DateTimeFormat('en-GB', { hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Brussels' }).format(new Date(value));
}

function formatDayTime(value) {
  if (!value) return '—';
  return new Intl.DateTimeFormat('en-GB', {
    day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Brussels',
  }).format(new Date(value));
}

async function loadJson(path) {
  const response = await fetch(path, { cache: 'no-store' });
  if (!response.ok) throw new Error(`${path} returned ${response.status}`);
  return response.json();
}

/* API data access */

const cityKey = (city) => city.nis_code || `source:${city.name}`;
const cities = () => state.data.cities || [];
const cityByKey = (key) => state.cityIndex.get(key) || null;
const valueOf = (city, series = state.pollutant) => city?.values?.[series] ?? null;
const whoValueOf = (city, series = state.pollutant) => city?.who_values?.[series] ?? null;
const windowHours = () => state.data.window?.duration_hours ?? 3;
const windowPhrase = () => `the last ${windowHours()} hours`;

function indexCities() {
  state.cityIndex = new Map(cities().map((city) => [cityKey(city), city]));
  state.searchIndex = null;
}

function seriesSample(series) {
  for (const city of cities()) {
    const value = valueOf(city, series) || whoValueOf(city, series);
    if (value) return value;
  }
  return null;
}

// One tab per air pollutant found in either the current or WHO-period results.
// Weather readings (temperature, humidity) and odd units reported by a few stations get no tab.
function seriesList() {
  const keys = new Set(cities().flatMap((city) => [
    ...Object.keys(city.values || {}), ...Object.keys(city.who_values || {}),
  ]));
  const preference = (key) => [seriesSample(key).unit === 'µg/m³' ? 1 : 0, rankedCities(key).length];
  const chosen = new Map();
  keys.forEach((key) => {
    const parameter = seriesSample(key)?.parameter;
    if (!POLLUTANTS[parameter]) return;
    const current = chosen.get(parameter);
    const [unitScore, places] = preference(key);
    const [currentUnitScore, currentPlaces] = current ? preference(current) : [-1, -1];
    if (unitScore > currentUnitScore || (unitScore === currentUnitScore && places > currentPlaces)) {
      chosen.set(parameter, key);
    }
  });
  return POLLUTANT_ORDER.filter((parameter) => chosen.has(parameter)).map((parameter) => chosen.get(parameter));
}

function presentation(series) {
  const parameter = seriesSample(series)?.parameter || String(series).split('_')[0];
  return POLLUTANTS[parameter] || { formula: escapeHtml(parameter.toUpperCase()), text: parameter.toUpperCase(), name: parameter.toUpperCase() };
}

function seriesForParameter(parameter) {
  return seriesList().find((series) => seriesSample(series)?.parameter === parameter) || null;
}

function rankedCities(series = state.pollutant) {
  return cities().filter((city) => valueOf(city, series))
    .sort((a, b) => valueOf(a, series).rank - valueOf(b, series).rank);
}

function bandIndex(value) {
  return BANDS.findIndex((band) => band.color === String(value?.color).toLowerCase());
}

/* Geometry */

// NIS codes of the German-speaking Community. Other Walloon codes start with 25, 5, 6, 8 or 9.
const GERMAN_SPEAKING = new Set(['63001', '63012', '63013', '63023', '63040', '63048', '63061', '63067', '63087']);
const WALLOON_PREFIXES = ['25', '5', '6', '8', '9'];

// The name a municipality uses itself: Liège, not Luik; both names in bilingual Brussels.
// Same rule as local_name in the transformation service.
function municipalityName(feature) {
  const { nis_code: code, name_nl: nl, name_fr: fr, name_de: de } = feature.properties;
  const nis = String(code);
  if (GERMAN_SPEAKING.has(nis)) return de || fr || nl;
  if (nis.startsWith('21')) return [...new Set([fr, nl].filter(Boolean))].join(' / ');
  if (WALLOON_PREFIXES.some((prefix) => nis.startsWith(prefix))) return fr || nl || de;
  return nl || fr || de;
}

function municipalityAliases(feature, name) {
  const { name_nl: nl, name_fr: fr, name_de: de } = feature.properties;
  return [...new Set([nl, fr, de])].filter((alias) => alias && alias !== name);
}

function extendBounds(bounds, coordinates) {
  if (typeof coordinates[0] === 'number') bounds.extend(coordinates);
  else coordinates.forEach((part) => extendBounds(bounds, part));
  return bounds;
}

function indexGeometry() {
  state.geometry.features.forEach((feature) => state.features.set(String(feature.properties.nis_code), feature));
  state.bounds = state.geometry.features.reduce(
    (bounds, feature) => extendBounds(bounds, feature.geometry.coordinates), new maplibregl.LngLatBounds());
}

function displayName(key) {
  const feature = state.features.get(key);
  return cityByKey(key)?.name || (feature ? municipalityName(feature) : String(key).replace(/^source:/, ''));
}

/* Map */

async function loadStyle(theme) {
  const { basemap, fallback } = MAP_THEMES[theme];
  try {
    const response = await fetch(basemap, { signal: AbortSignal.timeout(4000) });
    if (!response.ok) throw new Error(`basemap ${response.status}`);
    return await response.json();
  } catch (error) {
    console.warn('Basemap unavailable, using local background', error);
    return fallback;
  }
}

function initialiseMap() {
  state.mapReady = loadStyle(state.theme)
    .then((style) => createMap(style, MAP_THEMES[state.theme].fallback));
}

function createMap(style, fallback = null) {
  const map = new maplibregl.Map({
    container: 'map',
    style,
    center: [4.67, 50.65],
    zoom: 7,
    minZoom: 6,
    maxZoom: 13,
    dragRotate: false,
    pitchWithRotate: false,
    attributionControl: { compact: true, customAttribution: 'Boundaries © NGI/IGN, CC BY 4.0' },
  });
  state.map = map;
  map.touchZoomRotate.disableRotation();
  map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right');
  return new Promise((resolve) => {
    const timeout = fallback && setTimeout(() => {
      map.remove();
      createMap(fallback).then(resolve);
    }, 5000);
    map.once('load', () => {
      if (timeout) clearTimeout(timeout);
      resolve();
    });
  });
}

// Places OpenAQ reported that could not be matched to an official municipality are shown as dots.
function pointData() {
  return {
    type: 'FeatureCollection',
    features: cities().filter((city) => !city.nis_code && valueOf(city)).map((city) => ({
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [city.longitude, city.latitude] },
      properties: { key: cityKey(city), color: valueOf(city).color, selected: cityKey(city) === state.selected },
    })),
  };
}

// Re-run after every basemap change: switching styles drops custom sources and layers.
function addDataLayers() {
  const map = state.map;
  const colors = MAP_THEMES[state.theme];
  const reported = ['boolean', ['feature-state', 'reported'], false];
  const selected = ['boolean', ['feature-state', 'selected'], false];
  const hovered = ['boolean', ['feature-state', 'hover'], false];
  const firstLabel = map.getStyle().layers.find((layer) => layer.type === 'symbol')?.id;
  map.addSource(SOURCE, { type: 'geojson', data: state.geometry, promoteId: 'nis_code' });
  map.addLayer({ id: 'municipality-fill', type: 'fill', source: SOURCE, paint: {
    'fill-color': ['coalesce', ['feature-state', 'color'], colors.empty],
    'fill-opacity': ['case', reported, 0.78, 0.35],
  } }, firstLabel);
  map.addLayer({ id: 'municipality-line', type: 'line', source: SOURCE, paint: {
    'line-color': ['case', reported, colors.edge, colors.emptyEdge],
    'line-width': ['interpolate', ['linear'], ['zoom'], 6, 0.3, 10, 1.2],
    'line-opacity': ['case', reported, 0.9, 0.6],
  } }, firstLabel);
  map.addLayer({ id: 'municipality-focus', type: 'line', source: SOURCE, paint: {
    'line-color': colors.focus, 'line-width': ['case', selected, 2.6, hovered, 1.5, 0],
  } }, firstLabel);
  map.addSource(POINTS, { type: 'geojson', data: pointData() });
  map.addLayer({ id: 'unmapped-points', type: 'circle', source: POINTS, paint: {
    'circle-color': ['get', 'color'],
    'circle-radius': ['case', ['boolean', ['get', 'selected'], false], 9, 7],
    'circle-stroke-color': ['case', ['boolean', ['get', 'selected'], false], colors.focus, colors.edge],
    'circle-stroke-width': 2,
  } });
}

function setFlag(code, key, value) {
  if (code && state.features.has(code) && state.map?.getSource(SOURCE)) {
    state.map.setFeatureState({ source: SOURCE, id: code }, { [key]: value });
  }
}

function tooltipHtml(key) {
  const value = valueOf(cityByKey(key));
  const reading = value
    ? `<span class="tip-value"><i style="--colour:${escapeHtml(value.color)}"></i>${formatValue(value.average)} ${escapeHtml(value.unit)}</span>
       <span class="tip-meta">${plural(value.measurement_count, 'measurement')}, ${plural(value.station_count, 'station')}</span>`
    : `<span class="tip-meta">No measurements in ${windowPhrase()}</span>`;
  return `<strong>${escapeHtml(displayName(key))}</strong>${reading}`;
}

function paintMap() {
  if (!state.map?.getSource(SOURCE)) return;
  const empty = MAP_THEMES[state.theme].empty;
  state.features.forEach((feature, code) => {
    const value = valueOf(cityByKey(code));
    state.map.setFeatureState({ source: SOURCE, id: code }, {
      color: value?.color || empty, reported: Boolean(value), selected: code === state.selected,
    });
  });
  state.map.getSource(POINTS)?.setData(pointData());
}

function mapPadding(extra = 0) {
  const { clientWidth: width, clientHeight: height } = state.map.getContainer();
  const limit = (value, size) => Math.round(Math.max(0, Math.min(value + extra, size / 4)));
  return { top: limit(24, height), right: limit(56, width), bottom: limit(52, height), left: limit(24, width) };
}

function showBelgium({ animate = false } = {}) {
  state.map.once('moveend', () => {
    state.home = { center: state.map.getCenter(), zoom: state.map.getZoom() };
    byId('resetView').hidden = true;
  });
  state.map.fitBounds(state.bounds, { padding: mapPadding(), duration: animate && motionAllowed() ? 800 : 0 });
}

// Offer the way back only once the map has moved away from the whole-country view.
function updateResetButton() {
  if (!state.home) return;
  const map = state.map;
  const moved = map.project(state.home.center).dist(map.project(map.getCenter())) > 40;
  byId('resetView').hidden = !(moved || Math.abs(map.getZoom() - state.home.zoom) > 0.15);
}

function focusPlace(key) {
  const feature = state.features.get(key);
  const duration = motionAllowed() ? 900 : 0;
  if (feature) {
    state.map.fitBounds(extendBounds(new maplibregl.LngLatBounds(), feature.geometry.coordinates), {
      padding: mapPadding(80), maxZoom: 10.5, duration,
    });
    return;
  }
  const city = cityByKey(key);
  if (city) state.map.flyTo({ center: [city.longitude, city.latitude], zoom: 10, duration });
}

function renderCallout() {
  if (!state.callout) return;
  const key = state.selected || rankedCities()[0]?.nis_code || (rankedCities()[0] && cityKey(rankedCities()[0]));
  const city = cityByKey(key);
  const value = valueOf(city);
  if (!city || !value) {
    state.callout.remove();
    return;
  }
  const element = state.callout.getElement();
  element.dataset.key = key;
  element.setAttribute('aria-label', `${city.name}, ${formatValue(value.average)} ${value.unit}`);
  element.innerHTML = `<span class="callout-card"><strong>${formatValue(value.average)}</strong><span>${escapeHtml(city.name)}</span></span>
    <span class="callout-stem"></span><i style="--colour:${escapeHtml(value.color)}"></i>`;
  state.callout.setLngLat([city.longitude, city.latitude]).addTo(state.map);
}

function bindMapEvents() {
  const map = state.map;
  state.popup = new maplibregl.Popup({ closeButton: false, closeOnClick: false, offset: 14, className: 'map-tip', maxWidth: '260px' });
  const showTip = (key, lngLat) => {
    map.getCanvas().style.cursor = 'pointer';
    state.popup.setLngLat(lngLat).setHTML(tooltipHtml(key)).addTo(map);
  };
  const hideTip = () => {
    map.getCanvas().style.cursor = '';
    state.popup.remove();
  };
  map.on('mousemove', 'municipality-fill', (event) => {
    const code = String(event.features[0].properties.nis_code);
    if (state.hovered !== code) {
      setFlag(state.hovered, 'hover', false);
      state.hovered = code;
      setFlag(code, 'hover', true);
    }
    showTip(code, event.lngLat);
  });
  map.on('mouseleave', 'municipality-fill', () => {
    setFlag(state.hovered, 'hover', false);
    state.hovered = null;
    hideTip();
  });
  map.on('click', 'municipality-fill', (event) => {
    if (map.queryRenderedFeatures(event.point, { layers: ['unmapped-points'] }).length) return;
    selectPlace(String(event.features[0].properties.nis_code), { reveal: true });
  });
  map.on('mousemove', 'unmapped-points', (event) => showTip(event.features[0].properties.key, event.lngLat));
  map.on('mouseleave', 'unmapped-points', hideTip);
  map.on('click', 'unmapped-points', (event) => selectPlace(event.features[0].properties.key, { reveal: true }));

  const callout = document.createElement('button');
  callout.type = 'button';
  callout.className = 'callout';
  callout.addEventListener('click', () => selectPlace(callout.dataset.key, { reveal: true }));
  state.callout = new maplibregl.Marker({ element: callout, anchor: 'bottom', offset: [0, 5] });

  map.on('moveend', updateResetButton);
  byId('resetView').addEventListener('click', () => showBelgium({ animate: true }));
  let resizeTimer;
  window.addEventListener('resize', () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => { if (!state.selected) showBelgium(); }, 150);
  });
}

/* Theme */

function preferredTheme() {
  try {
    const saved = localStorage.getItem('airmax-theme');
    if (saved === 'light' || saved === 'dark') return saved;
  } catch { /* storage blocked: fall back to the system setting */ }
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

function applyTheme(theme) {
  state.theme = theme;
  document.documentElement.dataset.theme = theme;
  const label = theme === 'dark' ? 'Switch to light mode' : 'Switch to night mode';
  const button = byId('themeToggle');
  button.setAttribute('aria-label', label);
  button.title = label;
  button.setAttribute('aria-pressed', String(theme === 'dark'));
}

function toggleTheme() {
  const theme = state.theme === 'dark' ? 'light' : 'dark';
  try { localStorage.setItem('airmax-theme', theme); } catch { /* storage blocked: choice lasts this visit */ }
  applyTheme(theme);
  if (!state.map) return;
  state.map.once('style.load', () => {
    if (!state.mapBuilt) return;
    addDataLayers();
    paintMap();
  });
  loadStyle(theme).then((style) => state.map.setStyle(style, { diff: false }));
}

/* Header, tabs and headline */

function renderStatus() {
  const freshness = state.data.freshness || {};
  const badge = byId('freshnessBadge');
  badge.dataset.status = freshness.status || 'unavailable';
  badge.title = freshness.label || '';
  if (freshness.status === 'current') badge.textContent = `Latest data received ${formatTime(freshness.latest_observation)}`;
  else if (freshness.status === 'stale') badge.textContent = `Stale data, latest received ${formatDayTime(freshness.latest_observation)}`;
  else badge.textContent = `No measurements in ${windowPhrase()}`;
}

function renderTabs() {
  byId('pollutantTabs').innerHTML = seriesList().map((key) => {
    const pollutant = presentation(key);
    const unit = seriesSample(key)?.unit || '';
    return `<button type="button" class="pollutant-tab" data-series="${escapeHtml(key)}" aria-pressed="${key === state.pollutant}"
      title="${escapeHtml(`${pollutant.name} (${unit})`)}">
      <span class="pollutant-formula">${pollutant.formula}</span>
      <span class="pollutant-coverage">${plural(rankedCities(key).length, 'place')}</span>
    </button>`;
  }).join('');
}

// The headline describes the highest reading, so it steps aside while a place is selected.
function renderHeading() {
  const heading = document.querySelector('.map-heading');
  const wasHidden = heading.hidden;
  heading.hidden = Boolean(state.selected);
  if (wasHidden !== heading.hidden) state.map?.resize();
  if (heading.hidden) return;
  if (!seriesList().length) {
    byId('mapTitle').textContent = `No measurements in ${windowPhrase()}`;
    byId('mapSubtitle').textContent = state.data.freshness?.latest_observation
      ? `The latest measurement arrived for ${formatDayTime(state.data.freshness.latest_observation)}. The map fills in as soon as new measurements come in.`
      : 'The map fills in as soon as new measurements come in.';
    return;
  }
  const top = rankedCities()[0];
  const pollutant = presentation(state.pollutant);
  if (!top) {
    byId('mapTitle').textContent = `No current ${pollutant.text} measurements in ${windowPhrase()}`;
    byId('mapSubtitle').textContent = 'WHO-period estimates remain available in place details where earlier measurements exist.';
    return;
  }
  const value = valueOf(top);
  byId('mapTitle').textContent = `${pollutant.text} is highest in ${top.name}: ${formatValue(value.average)} ${value.unit}`;
  byId('mapSubtitle').textContent = `Average of the ${value.measurement_count === 1 ? 'measurement' : `${countFormat.format(value.measurement_count)} measurements`} `
    + `taken in ${top.name} between ${formatTime(value.earliest_observation)} and ${formatTime(value.latest_observation)}.`;
}

/* Ranking */

function renderRanking() {
  const list = byId('ranking');
  list.className = 'ranking';
  if (!state.pollutant) {
    byId('rankingTitle').textContent = 'Highest readings';
    byId('rankingSubtitle').textContent = 'Three-hour averages per place.';
    list.innerHTML = `<li class="panel-empty"><strong>No measurements in ${windowPhrase()}</strong>
      New measurements appear here automatically; the page checks every minute.</li>`;
    byId('scaleNote').hidden = true;
    return;
  }
  const pollutant = presentation(state.pollutant);
  byId('rankingTitle').innerHTML = `Highest <span class="formula">${pollutant.formula}</span> readings`;
  byId('rankingSubtitle').textContent = `Three-hour average in ${seriesSample(state.pollutant)?.unit || ''}. `
    + '"Indicative" means too few stations or measurements for a firm value.';
  const rows = rankedCities();
  if (!rows.length) {
    list.innerHTML = `<li class="panel-empty"><strong>No current measurements in ${windowPhrase()}</strong>
      WHO-period estimates remain visible when you open a place that has earlier measurements.</li>`;
    byId('scaleNote').hidden = true;
    return;
  }
  const values = rows.map((city) => valueOf(city).average);
  // Keep one extreme value from flattening every other bar; its bar is drawn with a break.
  const scaleMax = values.length > 2 && values[0] > values[1] * 2 ? values[1] * 1.15 : Math.max(...values);
  let clipped = false;
  list.innerHTML = rows.map((city) => {
    const key = cityKey(city);
    const value = valueOf(city);
    const isClipped = value.average > scaleMax;
    clipped ||= isClipped;
    const share = scaleMax > 0 ? Math.max(2, Math.min(100, (value.average / scaleMax) * 100)) : 2;
    const flag = value.status === 'available' ? '' : '<span class="rank-flag">Indicative</span>';
    return `<li><button type="button" data-key="${escapeHtml(key)}"${key === state.selected ? ' class="is-selected" aria-current="true"' : ''}>
      <span class="rank-number">${escapeHtml(value.rank)}</span>
      <span class="rank-city">${escapeHtml(city.name)}${flag}</span>
      <span class="rank-value">${formatValue(value.average)}</span>
      <span class="rank-meta">${plural(value.measurement_count, 'measurement')}, ${plural(value.station_count, 'station')}</span>
      <span class="rank-bar${isClipped ? ' is-clipped' : ''}"><i style="--bar:${share.toFixed(1)}%;--colour:${escapeHtml(value.color)}"></i></span>
    </button></li>`;
  }).join('');
  byId('scaleNote').hidden = !clipped;
}

function renderMunicipalities() {
  const list = byId('ranking');
  const places = searchIndex().filter((place) => !place.key.startsWith('source:'));
  byId('rankingTitle').textContent = 'Municipalities';
  byId('rankingSubtitle').textContent = `${countFormat.format(places.length)} Belgian municipalities. Grey means no measurements—not clean air.`;
  list.className = 'municipality-list';
  list.innerHTML = places.map((place) => {
    const city = cityByKey(place.key);
    const available = seriesList().filter((series) => valueOf(city, series) || whoValueOf(city, series));
    return `<li><button type="button" data-key="${escapeHtml(place.key)}">
      <strong>${escapeHtml(place.name)}</strong><small>${available.length ? `${plural(available.length, 'pollutant')} with data` : 'No measurements'}</small>
      <span class="municipality-pollutants">${available.map((series) => {
        const value = valueOf(city, series);
        return `<span><i style="--colour:${escapeHtml(value?.color || MAP_THEMES[state.theme].empty)}"></i>${presentation(series).formula}</span>`;
      }).join('')}</span>
    </button></li>`;
  }).join('');
  byId('scaleNote').hidden = true;
}

/* Place detail */

function whoComparisonHtml(value) {
  const guideline = (state.data.guidelines || []).find((item) => item.pollutant === value.parameter && item.unit === value.unit);
  if (!guideline) return '';
  const comparison = value.who_comparison;
  const hours = guideline.period_hours;
  if (!comparison) {
    return `<section class="who-comparison" aria-label="WHO ${hours}-hour reference">
      <h3>${escapeHtml(presentation(state.pollutant).text)} WHO reference</h3>
      <div class="who-values"><p><span>WHO ${hours}-hour guideline</span><strong>${formatValue(guideline.guideline)} ${escapeHtml(guideline.unit)}</strong></p></div>
      <p class="who-status" data-status="insufficient_coverage">No ${hours}-hour estimate is available for this place yet.</p>
      <p class="who-basis">The reference is always shown; measurements only determine when a comparison becomes available. <a href="${escapeHtml(guideline.source)}" target="_blank" rel="noopener">WHO guideline</a>.</p>
    </section>`;
  }
  const observedHours = comparison.observation_hour_count;
  const heading = escapeHtml(presentation(state.pollutant).text);
  const evidence = `${plural(comparison.measurement_count, 'measurement')} from
    ${plural(comparison.physical_site_count, 'physical site')} at
    ${plural(comparison.observation_count, 'distinct observation time')}`;
  if (comparison.status === 'insufficient_coverage') {
    return `<section class="who-comparison" aria-label="WHO ${hours}-hour comparison">
      <h3>${heading} compared with WHO</h3>
      <div class="who-values"><p><span>Average from the data we have</span><strong>${formatValue(comparison.average)} ${escapeHtml(value.unit)}</strong></p>
        <p><span>WHO ${hours}-hour guideline</span><strong>${formatValue(guideline.guideline)} ${escapeHtml(guideline.unit)}</strong></p></div>
      <p class="who-status" data-status="insufficient_coverage">Not enough data yet</p>
      <p class="who-explanation">We have readings from only ${plural(observedHours, 'hour')}. A fair ${hours}-hour comparison needs readings from at least ${comparison.required_hour_count} different hours.</p>
      <p class="who-basis">So far: ${evidence}, across ${observedHours} of ${hours} hours. <a href="${escapeHtml(comparison.source)}" target="_blank" rel="noopener">About this WHO guideline</a>.</p>
    </section>`;
  }
  const amount = `${formatValue(Math.abs(comparison.difference))} ${escapeHtml(value.unit)}`;
  const position = comparison.difference > 0 ? `${amount} above the WHO guideline`
    : comparison.difference < 0 ? `${amount} below the WHO guideline` : 'Equal to the WHO guideline';
  return `<section class="who-comparison" aria-label="WHO ${hours}-hour comparison">
    <h3>${heading} compared with WHO</h3>
    <div class="who-values"><p><span>${hours}-hour average</span><strong>${formatValue(comparison.average)} ${escapeHtml(value.unit)}</strong></p>
      <p><span>WHO ${hours}-hour guideline</span><strong>${formatValue(guideline.guideline)} ${escapeHtml(guideline.unit)}</strong></p></div>
    <p class="who-status" data-status="${escapeHtml(comparison.status)}">${position}</p>
    <p class="who-explanation">Based on ${evidence}, across ${observedHours} of ${hours} hours.</p>
    <p class="who-basis">Indicative comparison—not a health or legal verdict. <a href="${escapeHtml(comparison.source)}" target="_blank" rel="noopener">About this WHO guideline</a>.</p>
  </section>`;
}

function readingHtml(city, value) {
  const pollutant = presentation(state.pollutant);
  const band = bandIndex(value);
  const comparison = whoValueOf(city)?.comparison || null;
  const indicative = value.status === 'available' ? ''
    : '<p class="detail-note">Indicative: based on too few stations or measurements for a firm value.</p>';
  return `<div class="reading">
      <p class="reading-context">${escapeHtml(pollutant.name)}, average of ${windowPhrase()}</p>
      <p class="reading-value"><strong>${formatValue(value.average)}</strong><span>${escapeHtml(value.unit)}</span></p>
      <p class="reading-basis">Based on ${plural(value.measurement_count, 'measurement')} from ${plural(value.station_count, 'station')}, ${formatTime(value.earliest_observation)}–${formatTime(value.latest_observation)}.</p>
      <div class="band" aria-hidden="true">${BANDS.map((item, index) =>
        `<i style="--colour:${item.color}"${index === band ? ' class="is-active"' : ''}></i>`).join('')}</div>
      <div class="band-labels" aria-hidden="true"><span>Lowest 25%</span><span>Highest 25%</span></div>
      <p class="reading-standing">Rank ${escapeHtml(value.rank)} of ${rankedCities().length} places measuring ${escapeHtml(pollutant.text)}${band >= 0 ? `, in the ${BANDS[band].label} group` : ''}.</p>
      ${indicative}
    </div>
    <dl class="evidence">
      <div><dt>Measurements</dt><dd>${countFormat.format(value.measurement_count)}</dd></div>
      <div><dt>Stations</dt><dd>${countFormat.format(value.station_count)}</dd></div>
      <div><dt>First measurement</dt><dd>${escapeHtml(formatTime(value.earliest_observation))}</dd></div>
      <div><dt>Latest measurement</dt><dd>${escapeHtml(formatTime(value.latest_observation))}</dd></div>
    </dl>${whoComparisonHtml({ ...value, who_comparison: comparison })}`;
}

function otherPollutantsHtml(city) {
  const others = city ? seriesList().filter((series) => series !== state.pollutant && valueOf(city, series)) : [];
  if (!others.length) return '';
  return `<section class="detail-section"><h3>Other pollutants here</h3><ul class="others">${others.map((series) => {
    const value = valueOf(city, series);
    const pollutant = presentation(series);
    return `<li><button type="button" data-series="${escapeHtml(series)}">
      <span class="formula">${pollutant.formula}</span>
      <span class="dot" style="--colour:${escapeHtml(value.color)}"></span>
      <span class="label">${escapeHtml(pollutant.name)}</span>
      <span class="value">${formatValue(value.average)} <small>${escapeHtml(value.unit)}</small></span>
    </button></li>`;
  }).join('')}</ul></section>`;
}

function allPollutantsHtml(city) {
  return `<section class="detail-section"><h3>All pollutants in this municipality</h3>
    <p class="overview-note">Card colours compare the current value with other reporting municipalities. WHO status uses its own averaging period.</p>
    <ul class="pollutant-overview">${POLLUTANT_ORDER.map((parameter) => {
    const series = seriesForParameter(parameter);
    const current = series && valueOf(city, series);
    const who = series && whoValueOf(city, series);
    const comparison = who?.comparison;
    const guideline = (state.data.guidelines || []).find((item) => item.pollutant === parameter);
    const band = bandIndex(current);
    let meaning = guideline ? `WHO ${guideline.period_hours}h: no estimate yet` : 'No WHO comparison';
    let status = 'insufficient_coverage';
    if (comparison?.status === 'above_guideline_value') {
      meaning = `WHO ${guideline.period_hours}h: ${formatValue(Math.abs(comparison.difference))} ${escapeHtml(guideline.unit)} above guideline`;
      status = comparison.status;
    } else if (comparison?.status === 'at_or_below_guideline_value') {
      meaning = `WHO ${guideline.period_hours}h: at or below guideline`;
      status = comparison.status;
    } else if (comparison) {
      meaning = `WHO ${guideline.period_hours}h: not enough data (${comparison.observation_hour_count} of ${comparison.period_hours} hours; ${comparison.required_hour_count} required)`;
    }
    const evidence = current
      ? `${plural(current.measurement_count, 'measurement')} · ${plural(current.station_count, 'station')}`
      : 'No current reading';
    const relative = band >= 0 ? `${BANDS[band].label} among reporting municipalities` : 'No current comparison';
    return `<li style="--colour:${escapeHtml(current?.color || MAP_THEMES[state.theme].empty)}"><button type="button"${series ? ` data-series="${escapeHtml(series)}"` : ' disabled'}${series === state.pollutant ? ' aria-current="true"' : ''}>
      <span class="pollutant-name"><span class="formula">${POLLUTANTS[parameter].formula}</span>${escapeHtml(POLLUTANTS[parameter].name)}</span>
      <span class="pollutant-current">${current ? `${formatValue(current.average)} ${escapeHtml(current.unit)}` : '—'}</span>
      <span class="pollutant-relative"><i></i>${relative}</span>
      <span class="pollutant-evidence">${evidence}</span>
      <span class="pollutant-meaning" data-status="${escapeHtml(status)}">${meaning}</span>
    </button></li>`;
  }).join('')}</ul></section>`;
}

function renderDetail() {
  const key = state.selected;
  const city = cityByKey(key);
  const feature = state.features.get(key);
  const name = displayName(key);
  const value = valueOf(city);
  let identity = '';
  if (feature) {
    const aliases = municipalityAliases(feature, name);
    identity = `${aliases.length ? `Also ${aliases.join(', ')}. ` : ''}NIS code ${key}.`;
  } else if (city && !city.nis_code) {
    identity = "Placed by OpenAQ's city name; its stations could not be matched to an official municipality.";
  }
  const pollutantText = state.pollutant ? presentation(state.pollutant).text : 'any pollutant';
  const sample = state.pollutant && seriesSample(state.pollutant);
  const whoValue = whoValueOf(city);
  const body = value ? readingHtml(city, value)
    : `<p class="detail-empty-note">No station in ${escapeHtml(name)} measured ${escapeHtml(pollutantText)} in ${windowPhrase()}.</p>`
      + (sample ? whoComparisonHtml({
        parameter: sample.parameter, unit: sample.unit, who_comparison: whoValue?.comparison || null,
      }) : '');
  const content = state.view === 'municipalities'
    ? `${allPollutantsHtml(city)}<section class="detail-section"><h3>Selected pollutant detail</h3>${body}</section>`
    : `${body}${otherPollutantsHtml(city)}`;
  byId('cityPanel').innerHTML = `<div class="detail">
    <button type="button" class="detail-back" data-action="back">${ICON_BACK}All places</button>
    <h2>${escapeHtml(name)}</h2>
    ${identity ? `<p class="detail-identity">${escapeHtml(identity)}</p>` : ''}
    ${content}
  </div>`;
}

function renderPanel() {
  const open = Boolean(state.selected);
  byId('rankingView').hidden = open;
  byId('cityPanel').hidden = !open;
  if (open) renderDetail();
  else if (state.view === 'municipalities') renderMunicipalities();
  else renderRanking();
}

/* Search */

function searchIndex() {
  if (!state.searchIndex) {
    const municipalities = [...state.features.values()].map((feature) => {
      const name = municipalityName(feature);
      const aliases = municipalityAliases(feature, name);
      return { key: String(feature.properties.nis_code), name, aliases, haystack: normalise([name, ...aliases].join(' ')) };
    });
    const unmapped = cities().filter((city) => !city.nis_code)
      .map((city) => ({ key: cityKey(city), name: city.name, aliases: ['OpenAQ place name'], haystack: normalise(city.name) }));
    state.searchIndex = [...municipalities, ...unmapped].sort((a, b) => a.name.localeCompare(b.name, 'nl'));
  }
  return state.searchIndex;
}

function closeSearch() {
  const input = byId('placeSearch');
  byId('placeResults').hidden = true;
  input.setAttribute('aria-expanded', 'false');
  input.removeAttribute('aria-activedescendant');
  state.searchMatches = [];
  state.searchActive = -1;
}

function renderSearchResults() {
  const input = byId('placeSearch');
  const results = byId('placeResults');
  const query = normalise(input.value.trim());
  if (!query) {
    closeSearch();
    return;
  }
  if (!state.features.size) {
    results.innerHTML = '<li class="search-empty" role="option" aria-disabled="true">Loading places…</li>';
  } else {
    const startsWith = (item) => item.haystack.split(/[\s'-]+/).some((word) => word.startsWith(query));
    state.searchMatches = searchIndex().filter((item) => item.haystack.includes(query))
      .sort((a, b) => Number(startsWith(b)) - Number(startsWith(a))).slice(0, 8);
    state.searchActive = Math.min(Math.max(state.searchActive, 0), state.searchMatches.length - 1);
    results.innerHTML = state.searchMatches.length ? state.searchMatches.map((item, index) => {
      const city = cityByKey(item.key);
      const value = valueOf(city);
      const available = state.view === 'municipalities' && city
        ? seriesList().filter((series) => valueOf(city, series) || whoValueOf(city, series)).length : 0;
      const reading = available
        ? `<span class="result-value is-empty">${plural(available, 'pollutant')}</span>`
        : value
          ? `<span class="result-value"><i style="--colour:${escapeHtml(value.color)}"></i>${formatValue(value.average)}</span>`
          : '<span class="result-value is-empty">No reading</span>';
      return `<li id="place-${escapeHtml(item.key.replace(/[^a-z0-9]/gi, '-'))}" role="option" data-key="${escapeHtml(item.key)}" aria-selected="${index === state.searchActive}">
        <span class="result-name">${escapeHtml(item.name)}</span>${reading}
        ${item.aliases.length ? `<span class="result-alias">${escapeHtml(item.aliases.join(', '))}</span>` : ''}
      </li>`;
    }).join('') : '<li class="search-empty" role="option" aria-disabled="true">No place matches that name.</li>';
  }
  results.hidden = false;
  input.setAttribute('aria-expanded', 'true');
  const active = state.searchMatches[state.searchActive];
  if (active) input.setAttribute('aria-activedescendant', `place-${active.key.replace(/[^a-z0-9]/gi, '-')}`);
  else input.removeAttribute('aria-activedescendant');
}

function chooseSearchResult(key) {
  const input = byId('placeSearch');
  input.value = '';
  closeSearch();
  input.blur();
  selectPlace(key, { reveal: true });
}

// Search is wired first and only needs the municipality list, so it works even if later rendering fails.
function bindSearch() {
  const input = byId('placeSearch');
  input.addEventListener('input', () => {
    state.searchActive = 0;
    renderSearchResults();
  });
  input.addEventListener('focus', renderSearchResults);
  input.addEventListener('keydown', (event) => {
    const count = state.searchMatches.length;
    if (event.key === 'ArrowDown' && count) {
      event.preventDefault();
      state.searchActive = (state.searchActive + 1) % count;
      renderSearchResults();
    } else if (event.key === 'ArrowUp' && count) {
      event.preventDefault();
      state.searchActive = (state.searchActive - 1 + count) % count;
      renderSearchResults();
    } else if (event.key === 'Enter' && count) {
      event.preventDefault();
      chooseSearchResult(state.searchMatches[Math.max(0, state.searchActive)].key);
    } else if (event.key === 'Escape') {
      input.value = '';
      closeSearch();
    }
  });
  input.addEventListener('blur', () => setTimeout(closeSearch, 150));
  byId('placeResults').addEventListener('mousedown', (event) => {
    const option = event.target.closest('[data-key]');
    if (!option) return;
    event.preventDefault();
    chooseSearchResult(option.dataset.key);
  });
}

/* State changes */

// Keep the chosen pollutant and primary view in the shareable URL.
function writeHash() {
  const params = new URLSearchParams();
  if (state.pollutant) params.set('pollutant', state.pollutant);
  if (state.view === 'municipalities') params.set('view', state.view);
  history.replaceState(null, '', `#${params}`);
}

function chooseInitialPollutant() {
  const series = seriesList();
  const params = new URLSearchParams(location.hash.slice(1));
  const requested = params.get('pollutant');
  if (params.get('view') === 'municipalities') state.view = 'municipalities';
  if (series.includes(state.pollutant)) return;
  state.pollutant = series.includes(requested) ? requested
    : series.reduce((best, key) => (rankedCities(key).length > rankedCities(best).length ? key : best), series[0]) || null;
}

function render() {
  renderStatus();
  renderTabs();
  if (!state.pollutant) byId('pollutantTabs').innerHTML = `<p class="tabs-note">No pollutants measured in ${windowPhrase()}.</p>`;
  renderHeading();
  paintMap();
  document.querySelectorAll('[data-view]').forEach((button) => {
    button.setAttribute('aria-pressed', String(button.dataset.view === state.view));
  });
  byId('pollutantBar').hidden = state.view === 'municipalities';
  document.querySelector('.workspace').classList.toggle('is-municipalities', state.view === 'municipalities');
  renderPanel();
  renderCallout();
  writeHash();
}

function setView(view) {
  state.view = view;
  render();
  if (view === 'map') {
    setTimeout(() => {
      state.map?.resize();
      if (state.selected) focusPlace(state.selected);
      else if (state.map) showBelgium();
    });
  }
}

function setPollutant(series) {
  state.pollutant = series;
  render();
  byId('rankingView').scrollTop = 0;
}

function selectPlace(key, { reveal = false } = {}) {
  const previous = state.selected;
  state.selected = key;
  setFlag(previous, 'selected', false);
  setFlag(key, 'selected', true);
  state.map?.getSource(POINTS)?.setData(pointData());
  renderHeading();
  renderPanel();
  renderCallout();
  const panel = key ? byId('cityPanel') : byId('rankingView');
  panel.scrollTop = 0;
  if (key) {
    if (state.view === 'map') focusPlace(key);
    if (reveal && isStacked()) panel.scrollIntoView({ behavior: motionAllowed() ? 'smooth' : 'auto', block: 'start' });
  } else if (previous && state.view === 'map') {
    showBelgium({ animate: true });
  }
}

async function refresh() {
  try {
    state.data = await loadJson('/api/current');
    byId('errorBanner').hidden = true;
  } catch (error) {
    console.error(error);
    return;
  }
  indexCities();
  chooseInitialPollutant();
  render();
}

function bindEvents() {
  byId('themeToggle').addEventListener('click', toggleTheme);
  document.querySelector('.view-switch').addEventListener('click', (event) => {
    const button = event.target.closest('[data-view]');
    if (button) setView(button.dataset.view);
  });
  byId('pollutantTabs').addEventListener('click', (event) => {
    const button = event.target.closest('[data-series]');
    if (button) setPollutant(button.dataset.series);
  });
  byId('rankingView').addEventListener('click', (event) => {
    const button = event.target.closest('[data-key]');
    if (button) selectPlace(button.dataset.key);
  });
  byId('cityPanel').addEventListener('click', (event) => {
    const target = event.target.closest('[data-series], [data-action]');
    if (target?.dataset.series) setPollutant(target.dataset.series);
    else if (target?.dataset.action === 'back') selectPlace(null);
  });
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && state.selected && event.target !== byId('placeSearch')) selectPlace(null);
  });
}

function showError(message) {
  byId('errorBanner').textContent = message;
  byId('errorBanner').hidden = false;
}

async function start() {
  applyTheme(preferredTheme());
  bindEvents();
  bindSearch();
  initialiseMap();
  try {
    state.geometry = await loadJson('/assets/municipalities.min.geojson');
    indexGeometry();
  } catch (error) {
    console.error(error);
    showError("Couldn't load the municipality map. Reload the page to try again.");
    return;
  }
  try {
    state.data = await loadJson('/api/current');
  } catch (error) {
    console.error(error);
    showError("Couldn't load the latest air-quality data. The page will retry every minute.");
  }
  indexCities();
  chooseInitialPollutant();
  render();

  await state.mapReady;
  addDataLayers();
  state.mapBuilt = true;
  bindMapEvents();
  showBelgium();
  render();
  setInterval(refresh, REFRESH_MS);
}

start().catch((error) => {
  console.error(error);
  showError('Something went wrong while drawing the dashboard. Reload the page to try again.');
});
