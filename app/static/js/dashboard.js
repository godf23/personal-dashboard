const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

let addLocType = "weather";
let currentView = "dashboard";
let weatherData = [];
let newsData = [];
let newsPrefs = null;
let savedArticles = [];
let newsSearchQuery = "";
let newsTab = "feed";
let savedTagFilter = "";
let savedSearchQuery = "";
let expandedClusters = new Set();
let pendingSaveArticle = null;
let linksTree = { folders: [], links: [] };
let collapsedFolders = new Set();
let linksSearchQuery = "";
let pendingFolderLinkIds = null;
let dragPayload = null;
const previewCache = new Map();

async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || res.statusText);
  }
  return res.json();
}

function iconUrl(folder, name) {
  return `/static/icons/${folder}/${name}.png`;
}

function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function wxMoodClass(w) {
  const icon = w.icon_key || "unknown";
  const rain = w.rain_chance_pct || 0;
  if (icon === "thunderstorm") return "wx-storm";
  if (["rain", "drizzle", "showers"].includes(icon) || rain >= 55) return "wx-rain";
  if (icon === "snow") return "wx-snow";
  if (icon === "fog") return "wx-fog";
  if (icon === "clear") return "wx-sunny";
  if (icon === "partly_cloudy") return "wx-partly";
  if (icon === "cloudy") return "wx-cloudy";
  return "wx-default";
}

function weatherFxHtml(mood) {
  if (mood === "wx-sunny") {
    return `<div class="wx-fx"><div class="wx-sun"></div></div>`;
  }
  if (mood === "wx-rain" || mood === "wx-storm") {
    const drops = Array.from({ length: 14 }, (_, i) => {
      const left = 4 + (i * 7) % 92;
      const delay = (i * 0.17) % 1.2;
      const dur = 0.7 + (i % 4) * 0.15;
      return `<div class="wx-drop" style="left:${left}%;animation-duration:${dur}s;animation-delay:${delay}s"></div>`;
    }).join("");
    const bolt = mood === "wx-storm" ? `<div class="wx-lightning"></div>` : "";
    return `<div class="wx-fx">${drops}${bolt}</div>`;
  }
  if (mood === "wx-snow") {
    const flakes = Array.from({ length: 12 }, (_, i) => {
      const left = 5 + (i * 8) % 90;
      const delay = (i * 0.25) % 1.5;
      const dur = 2 + (i % 3) * 0.4;
      return `<div class="wx-flake" style="left:${left}%;animation-duration:${dur}s;animation-delay:${delay}s"></div>`;
    }).join("");
    return `<div class="wx-fx">${flakes}</div>`;
  }
  if (mood === "wx-cloudy" || mood === "wx-partly") {
    return `<div class="wx-fx"><div class="wx-cloud wx-cloud-1"></div><div class="wx-cloud wx-cloud-2"></div></div>`;
  }
  if (mood === "wx-fog") {
    return `<div class="wx-fx"><div class="wx-fog-layer"></div><div class="wx-fog-layer"></div><div class="wx-fog-layer"></div></div>`;
  }
  return `<div class="wx-fx"></div>`;
}

function fmtStat(value, suffix = "") {
  if (value == null || value === "") return "—";
  return `${value}${suffix}`;
}

function weatherStat(label, value) {
  return `<div class="weather-detail-stat"><label>${escapeHtml(label)}</label><span>${escapeHtml(String(value))}</span></div>`;
}

function renderWeatherDetailHtml(w) {
  const icon = w.icon_key || "unknown";
  const pollenParts = [];
  if (w.pollen_summary) pollenParts.push(`Overall: ${w.pollen_summary}`);
  if (w.grass_pollen != null) pollenParts.push(`Grass: ${w.grass_pollen}`);
  if (w.tree_pollen != null) pollenParts.push(`Tree: ${w.tree_pollen}`);
  if (w.weed_pollen != null) pollenParts.push(`Weed: ${w.weed_pollen}`);
  const pollen = pollenParts.length ? pollenParts.join(" · ") : "Not available for this area";

  const stageLabels = {
    trimmed_mean: "Trimmed mean",
    bias: "Bias correction",
    xgboost: "XGBoost ensemble",
    kalman: "XGBoost + Kalman",
  };
  const pipelineStage = stageLabels[w.pipeline_stage] || w.pipeline_stage || "—";
  const upgrade =
    w.days_until_upgrade != null
      ? `${w.days_until_upgrade} day(s) to next stage`
      : "Maximum stage";
  const sourceScores = w.source_scores
    ? Object.entries(w.source_scores)
        .map(([name, score]) => `${name}: ${(score * 100).toFixed(0)}%`)
        .join(" · ")
    : "—";

  const stats = [
    weatherStat("Pipeline", pipelineStage),
    weatherStat("Obs station", fmtStat(w.observation_station)),
    weatherStat("Local history", w.observation_days != null ? `${w.observation_days} days` : "—"),
    weatherStat("Next upgrade", upgrade),
    weatherStat("Source scores", sourceScores),
    weatherStat("Feels like", fmtStat(w.feels_like_f, "°F")),
    weatherStat("Humidity", fmtStat(w.humidity_pct, "%")),
    weatherStat("Rain chance", fmtStat(w.rain_chance_pct, "%")),
    weatherStat("Wind", w.wind_mph != null ? `${w.wind_mph} mph` : "—"),
    weatherStat("Wind dir", fmtStat(w.wind_direction)),
    weatherStat("Pressure", w.pressure_hpa != null ? `${w.pressure_hpa} hPa` : "—"),
    weatherStat("Dew point", fmtStat(w.dew_point_f, "°F")),
    weatherStat("UV index", fmtStat(w.uv_index_max ?? w.uv_index)),
    weatherStat("Cloud cover", fmtStat(w.cloud_cover_pct, "%")),
    weatherStat("Sunrise", fmtStat(w.sunrise)),
    weatherStat("Sunset", fmtStat(w.sunset)),
    weatherStat("Pollen", pollen),
  ].join("");

  return `
    <div class="weather-detail-hero">
      <img class="icon-weather" src="${iconUrl("weather", icon)}" alt="" width="48" height="48">
      <div>
        <div class="weather-detail-temp">${w.temperature_f}°F</div>
        <div class="weather-uncertainty">±${w.uncertainty_f}°F (${Math.round((w.confidence_level || 0.9) * 100)}%) · ${escapeHtml(w.summary)}</div>
      </div>
    </div>
    <div class="weather-detail-grid">${stats}</div>
    <div class="weather-detail-section">
      <h4>7-day forecast</h4>
      ${renderForecast(w.forecast_7day, false)}
    </div>
    <div class="weather-footer">${w.active_sources}/${w.total_sources} sources${w.cached ? " (cached)" : ""}</div>
  `;
}

function openWeatherDetail(w) {
  if (!w || w.error) return;
  const modal = $("#weather-detail-modal");
  const title = $("#weather-detail-title");
  const body = $("#weather-detail-body");
  if (!modal || !title || !body) return;
  title.textContent = w.location;
  body.innerHTML = renderWeatherDetailHtml(w);
  modal.showModal();
}

function renderForecast(days, compact) {
  if (!days?.length) return "";
  const cls = compact ? "forecast-strip compact" : "forecast-strip";
  const items = days.map((d) => {
    const icon = d.icon_key || "unknown";
    const rain = d.rain_chance_pct > 0
      ? `<div class="forecast-rain">${d.rain_chance_pct}%</div>`
      : "";
    return `<div class="forecast-day">
      <span class="forecast-dow">${escapeHtml(d.day)}</span>
      <img class="icon-weather" src="${iconUrl("weather", icon)}" alt="" width="20" height="20">
      <div class="forecast-temps">
        <span class="forecast-hi">${d.high_f ?? "--"}°</span>
        <span class="forecast-lo">${d.low_f ?? "--"}°</span>
      </div>
      ${rain}
    </div>`;
  }).join("");
  return `<div class="${cls}">${items}</div>`;
}

function isWeatherNewsArticle(a) {
  const src = (a.source || "").toLowerCase();
  return /weather\.com|accuweather|wunderground|weather\.gov|theweather\.com|weatherbug/.test(src);
}

function newsClusterKey(item) {
  return `cluster:${item.title}`;
}

function highlightMatch(text, query) {
  if (!text || !query) return escapeHtml(text);
  const lower = text.toLowerCase();
  const q = query.toLowerCase();
  const idx = lower.indexOf(q);
  if (idx < 0) return escapeHtml(text);
  return `${escapeHtml(text.slice(0, idx))}<mark class="news-match">${escapeHtml(text.slice(idx, idx + q.length))}</mark>${escapeHtml(text.slice(idx + q.length))}`;
}

function articleMatchesSearch(a, query) {
  if (!query) return true;
  const q = query.toLowerCase();
  return [a.title, a.description, a.source].some((f) => (f || "").toLowerCase().includes(q));
}

function itemMatchesSearch(item, query) {
  if (!query) return true;
  if (item.type === "cluster") {
    if ((item.title || "").toLowerCase().includes(query.toLowerCase())) return true;
    return (item.articles || []).some((a) => articleMatchesSearch(a, query));
  }
  return articleMatchesSearch(item, query);
}

function filterFeedItems(items) {
  return (items || []).filter((item) => {
    if (item.type === "cluster") return itemMatchesSearch(item, newsSearchQuery);
    if (isWeatherNewsArticle(item)) return false;
    return itemMatchesSearch(item, newsSearchQuery);
  });
}

function formatNewsArticle(a, expanded, forceDiv = false) {
  const source = a.source ? `<span class="news-source-badge">${escapeHtml(a.source)}</span>` : "";
  const cls = expanded || forceDiv ? "news-article" : "";
  const tag = expanded || forceDiv ? "div" : "li";
  const unreadCls = a.read ? "" : " news-article--unread";
  const savedCls = a.saved ? " news-save-btn--saved" : "";
  const desc = escapeHtml(a.description || "");
  const img = escapeHtml(a.image_url || "");
  const headline = highlightMatch(a.title, newsSearchQuery);
  const articlePayload = encodeURIComponent(
    JSON.stringify({
      url: a.url,
      title: a.title,
      source: a.source || "",
      description: a.description || "",
      image_url: a.image_url || "",
      published_at: a.published_at || "",
    })
  );
  return `<${tag} class="${cls} news-hover-item${unreadCls}"
    data-title="${escapeHtml(a.title)}"
    data-url="${escapeHtml(a.url)}"
    data-source="${escapeHtml(a.source || "")}"
    data-desc="${desc}"
    data-image="${img}">
    <div class="news-article-row">
      <button type="button" class="news-save-btn${savedCls}" data-save-article="${articlePayload}" aria-label="Save article">★</button>
      <a class="news-article-link" href="${escapeHtml(a.url)}" target="_blank" rel="noopener" data-news-link>
        <span class="news-headline">${headline}</span>
        <div class="news-source">${source}</div>
      </a>
    </div>
  </${tag}>`;
}

function formatNewsCluster(item, expanded) {
  const key = newsClusterKey(item);
  const isOpen = expandedClusters.has(key);
  const unreadCls = item.read ? "" : " news-article--unread";
  const tag = expanded ? "div" : "li";
  const extra = Math.max(0, (item.source_count || 1) - 1);
  const headline = highlightMatch(item.title, newsSearchQuery);
  const primary = (item.articles || [])[0] || item;
  const articlePayload = encodeURIComponent(
    JSON.stringify({
      url: primary.url,
      title: item.title,
      source: primary.source || "",
      description: primary.description || "",
      image_url: primary.image_url || "",
      published_at: primary.published_at || "",
    })
  );
  const savedCls = item.saved ? " news-save-btn--saved" : "";
  const altItems = isOpen
    ? (item.articles || []).map((a) => formatNewsArticle(a, expanded, true)).join("")
    : "";
  return `<${tag} class="news-cluster news-hover-item${unreadCls}" data-cluster-key="${escapeHtml(key)}"
    data-title="${escapeHtml(item.title)}"
    data-url="${escapeHtml(primary.url || "")}"
    data-source="${escapeHtml(primary.source || "")}"
    data-desc="${escapeHtml(primary.description || "")}"
    data-image="${escapeHtml(primary.image_url || "")}">
    <div class="news-article-row">
      <button type="button" class="news-save-btn${savedCls}" data-save-article="${articlePayload}" aria-label="Save article">★</button>
      <div class="news-cluster-body">
        <button type="button" class="news-cluster-header" data-toggle-cluster="${escapeHtml(key)}">
          <span class="news-headline">${headline}</span>
          ${extra > 0 ? `<span class="news-cluster-badge">+${extra} sources</span>` : ""}
        </button>
        ${isOpen ? `<div class="news-cluster-items">${altItems}</div>` : ""}
      </div>
    </div>
  </${tag}>`;
}

function formatNewsItem(item, expanded) {
  if (item.type === "cluster") return formatNewsCluster(item, expanded);
  if (isWeatherNewsArticle(item)) return "";
  return formatNewsArticle(item, expanded);
}

function renderSavedNewsList() {
  const list = $("#saved-news-list");
  if (!list) return;
  const q = savedSearchQuery.toLowerCase();
  let items = savedArticles;
  if (savedTagFilter) items = items.filter((a) => (a.tags || []).includes(savedTagFilter));
  if (q) {
    items = items.filter(
      (a) =>
        (a.title || "").toLowerCase().includes(q) ||
        (a.source || "").toLowerCase().includes(q) ||
        (a.notes || "").toLowerCase().includes(q)
    );
  }
  if (!items.length) {
    list.innerHTML = '<p class="empty-state">No saved articles yet</p>';
    return;
  }
  list.innerHTML = items
    .map(
      (a) => `<article class="saved-news-item" data-saved-id="${a.id}">
      <div class="saved-news-item-header">
        <a href="${escapeHtml(a.url)}" target="_blank" rel="noopener" class="saved-news-title">${escapeHtml(a.title)}</a>
        <button type="button" class="icon-btn" data-delete-saved="${a.id}" aria-label="Delete">
          <img class="icon-ui" src="${iconUrl("ui", "close")}" alt="" width="14" height="14">
        </button>
      </div>
      <div class="saved-news-meta">${escapeHtml(a.source || "")} · ${escapeHtml((a.saved_at || "").slice(0, 10))}</div>
      <div class="saved-news-tags">${(a.tags || []).map((t) => `<span class="saved-tag-chip">${escapeHtml(t)}</span>`).join("")}</div>
      <label class="saved-notes-label">Notes
        <textarea class="saved-notes-input" data-saved-notes="${a.id}" rows="2">${escapeHtml(a.notes || "")}</textarea>
      </label>
    </article>`
    )
    .join("");
  renderSavedTagChips();
}

function renderSavedTagChips() {
  const el = $("#saved-tag-chips");
  if (!el) return;
  const tags = new Set();
  savedArticles.forEach((a) => (a.tags || []).forEach((t) => tags.add(t)));
  const chips = [`<button type="button" class="news-chip${!savedTagFilter ? " active" : ""}" data-saved-tag="">All</button>`];
  [...tags].sort().forEach((t) => {
    chips.push(
      `<button type="button" class="news-chip${savedTagFilter === t ? " active" : ""}" data-saved-tag="${escapeHtml(t)}">${escapeHtml(t)}</button>`
    );
  });
  el.innerHTML = chips.join("");
}

function setNewsTab(tab) {
  newsTab = tab;
  $$(".news-tab").forEach((btn) => btn.classList.toggle("active", btn.dataset.newsTab === tab));
  $("#news-full-feed")?.classList.toggle("hidden", tab !== "feed");
  $("#news-full-saved")?.classList.toggle("hidden", tab !== "saved");
  if (tab === "saved") renderSavedNewsList();
}

function syncNewsSearchInputs() {
  const dash = $("#news-search");
  const full = $("#news-search-full");
  if (dash) dash.value = newsSearchQuery;
  if (full) full.value = newsSearchQuery;
}

function markReadLocal(url) {
  newsData.forEach((feed) => {
    (feed.articles || []).forEach((item) => {
      if (item.type === "cluster") {
        (item.articles || []).forEach((a) => {
          if (a.url === url) a.read = true;
        });
        if ((item.articles || []).every((a) => a.read)) item.read = true;
      } else if (item.url === url) {
        item.read = true;
      }
    });
  });
}

async function markNewsRead(url) {
  if (!url) return;
  try {
    await api("/api/news/read", { method: "POST", body: JSON.stringify({ url }) });
    markReadLocal(url);
    renderAllNews();
  } catch {
    /* ignore */
  }
}

async function loadNewsPrefs() {
  try {
    newsPrefs = await api("/api/news/prefs");
    updateAgeChips();
  } catch {
    newsPrefs = null;
  }
}

async function loadSavedArticles() {
  try {
    savedArticles = await api("/api/news/saved");
  } catch {
    savedArticles = [];
  }
  renderSavedNewsList();
}

function renderNewsFilterToggles() {
  const sourcesEl = $("#news-source-toggles");
  const catsEl = $("#news-category-toggles");
  if (!sourcesEl || !catsEl) return;
  Promise.all([api("/api/news/sources"), api("/api/news/categories")])
    .then(([sources, categories]) => {
      const sp = (newsPrefs && newsPrefs.source_prefs) || {};
      sourcesEl.innerHTML = sources.length
        ? sources
            .map((s) => {
              const w = sp[s] ?? 0;
              return `<div class="news-source-toggle" data-source="${escapeHtml(s)}">
              <span>${escapeHtml(s)}</span>
              <select class="news-source-weight" data-source-select="${escapeHtml(s)}">
                <option value="1" ${w >= 1 ? "selected" : ""}>Prioritize</option>
                <option value="0" ${w === 0 ? "selected" : ""}>Neutral</option>
                <option value="-1" ${w <= -1 ? "selected" : ""}>Block</option>
              </select>
            </div>`;
            })
            .join("")
        : '<p class="muted-text">Refresh news to discover sources</p>';
      const cp = (newsPrefs && newsPrefs.category_prefs) || {};
      catsEl.innerHTML = categories.length
        ? categories
            .map(
              (c) => `<label class="news-category-toggle">
              <input type="checkbox" data-category-toggle="${escapeHtml(c)}" ${cp[c] !== false ? "checked" : ""}>
              ${escapeHtml(c)}
            </label>`
            )
            .join("")
        : '<p class="muted-text">No categories in recent feeds</p>';
    })
    .catch(() => {});
}

async function openNewsFilters() {
  if (!newsPrefs) await loadNewsPrefs();
  if (!newsPrefs) return;
  const age = newsPrefs.age_filter || { mode: "7d", days: 7 };
  $$(`input[name="news-age"]`).forEach((r) => {
    r.checked = r.value === age.mode;
  });
  const daysInput = $("#news-age-days");
  if (daysInput) daysInput.value = age.days || 7;
  const bl = $("#news-blacklist-input");
  if (bl) bl.value = (newsPrefs.keyword_blacklist || []).join("\n");
  renderNewsFilterToggles();
  $("#news-filters-modal")?.showModal();
}

async function applyNewsFilters(e) {
  e?.preventDefault();
  const ageMode = document.querySelector('input[name="news-age"]:checked')?.value || "7d";
  let days = 7;
  if (ageMode === "24h") days = 1;
  else if (ageMode === "7d") days = 7;
  else if (ageMode === "30d") days = 30;
  else days = parseInt($("#news-age-days")?.value || "7", 10) || 7;
  const blacklist = ($("#news-blacklist-input")?.value || "")
    .split("\n")
    .map((s) => s.trim())
    .filter(Boolean);
  const source_prefs = {};
  $$("[data-source-select]").forEach((sel) => {
    source_prefs[sel.dataset.sourceSelect] = parseInt(sel.value, 10);
  });
  const category_prefs = {};
  $$("[data-category-toggle]").forEach((cb) => {
    category_prefs[cb.dataset.categoryToggle] = cb.checked;
  });
  newsPrefs = await api("/api/news/prefs", {
    method: "POST",
    body: JSON.stringify({ age_filter: { mode: ageMode, days }, keyword_blacklist: blacklist, source_prefs, category_prefs }),
  });
  $("#news-filters-modal")?.close();
  updateAgeChips();
  await loadNews(true);
}

function updateAgeChips() {
  const mode = newsPrefs?.age_filter?.mode || "7d";
  $$(".news-age-chips .news-chip").forEach((chip) => {
    chip.classList.toggle("active", chip.dataset.ageMode === mode);
  });
}

async function quickSetAgeMode(mode) {
  const days = mode === "24h" ? 1 : mode === "30d" ? 30 : 7;
  newsPrefs = await api("/api/news/prefs", {
    method: "POST",
    body: JSON.stringify({ age_filter: { mode, days } }),
  });
  updateAgeChips();
  await loadNews(true);
}

function openSaveModal(article) {
  pendingSaveArticle = article;
  const title = $("#news-save-title");
  if (title) title.textContent = article.title || article.url;
  const form = $("#news-save-form");
  if (form) {
    form.tags.value = "";
    form.notes.value = "";
  }
  $("#news-save-modal")?.showModal();
}

async function submitSaveArticle(e) {
  e.preventDefault();
  if (!pendingSaveArticle) return;
  const fd = new FormData(e.target);
  const tags = String(fd.get("tags") || "")
    .split(",")
    .map((t) => t.trim())
    .filter(Boolean);
  await api("/api/news/saved", {
    method: "POST",
    body: JSON.stringify({ ...pendingSaveArticle, tags, notes: fd.get("notes") || "" }),
  });
  pendingSaveArticle = null;
  $("#news-save-modal")?.close();
  await loadSavedArticles();
  await loadNews(false);
}

function renderWeatherTo(gridSel, items, expanded) {
  const grid = $(gridSel);
  if (!grid) return;
  if (!items.length) {
    grid.innerHTML = '<p class="empty-state">Add a location to see weather</p>';
    return;
  }
  grid.innerHTML = items.map((w) => {
    if (w.error) {
      return `<div class="weather-card" data-id="${w.id}">
        <button class="icon-btn card-remove" data-remove-weather="${w.id}" type="button">
          <img class="icon-ui" src="${iconUrl("ui", "close")}" alt="" width="16" height="16">
        </button>
        <div class="weather-card-body">
          <div class="loc-name">${escapeHtml(w.location)}</div>
          <p class="error-text">${escapeHtml(w.error)}</p>
        </div>
      </div>`;
    }
    const icon = w.icon_key || "unknown";
    const mood = wxMoodClass(w);
    const wind = w.wind_mph != null
      ? `<span><img class="icon-ui" src="${iconUrl("ui", "wind")}" alt="" width="14" height="14">${w.wind_mph} mph</span>`
      : "";
    const forecast = expanded
      ? renderForecast(w.forecast_7day, false)
      : renderForecast((w.forecast_7day || []).slice(0, 4), true);
    const clickCls = " weather-card-clickable";
    const detailAttr = ` data-weather-id="${w.id}"`;
    return `<div class="weather-card ${mood}${clickCls}" data-id="${w.id}"${detailAttr}>
      ${weatherFxHtml(mood)}
      <button class="icon-btn card-remove" data-remove-weather="${w.id}" type="button">
        <img class="icon-ui" src="${iconUrl("ui", "close")}" alt="" width="16" height="16">
      </button>
      <div class="weather-card-body">
        <div class="loc-name">${escapeHtml(w.location)}</div>
        <div class="weather-temp">${w.temperature_f}°F</div>
        <div class="weather-uncertainty">±${w.uncertainty_f}°F</div>
        <div class="weather-summary">
          <img class="icon-weather" src="${iconUrl("weather", icon)}" alt="" width="${expanded ? 32 : 22}" height="${expanded ? 32 : 22}">
          ${escapeHtml(w.summary)}
        </div>
        <div class="weather-meta">
          <span><img class="icon-ui" src="${iconUrl("ui", "humidity")}" alt="" width="14" height="14">${w.humidity_pct}%</span>
          <span><img class="icon-ui" src="${iconUrl("ui", "rain")}" alt="" width="14" height="14">${w.rain_chance_pct}%</span>
          ${wind}
        </div>
        ${forecast}
        ${expanded ? `<div class="weather-footer">${w.active_sources}/${w.total_sources} sources${w.cached ? " (cached)" : ""}</div>` : ""}
      </div>
    </div>`;
  }).join("");
}

function renderNewsTo(gridSel, feeds, expanded) {
  const grid = $(gridSel);
  if (!grid) return;
  if (!feeds.length) {
    grid.innerHTML = '<p class="empty-state">Add a location to see news</p>';
    return;
  }
  if (feeds.length === 1 && feeds[0].error && !feeds[0].id) {
    grid.innerHTML = `<p class="empty-state">${escapeHtml(feeds[0].error)}</p>`;
    return;
  }
  grid.innerHTML = feeds.map((f) => {
    if (f.error && !f.articles?.length) {
      return `<div class="news-card" data-id="${f.id}">
        <button class="icon-btn card-remove" data-remove-news="${f.id}" type="button">
          <img class="icon-ui" src="${iconUrl("ui", "close")}" alt="" width="16" height="16">
        </button>
        <div class="loc-name">${escapeHtml(f.label)}</div>
        <p class="error-text">${escapeHtml(f.error)}</p>
      </div>`;
    }
    const articles = filterFeedItems(f.articles)
      .map((a) => formatNewsItem(a, expanded))
      .filter(Boolean)
      .join("");
    const listTag = expanded ? "div" : "ul";
    return `<div class="news-card" data-id="${f.id}">
      <button class="icon-btn card-remove" data-remove-news="${f.id}" type="button">
        <img class="icon-ui" src="${iconUrl("ui", "close")}" alt="" width="16" height="16">
      </button>
      <div class="loc-name">${escapeHtml(f.label)}</div>
      <${listTag}>${articles || '<p class="empty-state">No headlines</p>'}</${listTag}>
    </div>`;
  }).join("");
}

function linkMatchesSearch(link) {
  if (!linksSearchQuery) return true;
  const q = linksSearchQuery.toLowerCase();
  return [link.title, link.url, link.description].some((f) =>
    (f || "").toLowerCase().includes(q)
  );
}

function folderLinkCount(folder) {
  let n = folder.links?.length || 0;
  for (const child of folder.children || []) n += folderLinkCount(child);
  return n;
}

function folderHasVisibleContent(folder) {
  const linksVisible = (folder.links || []).some(linkMatchesSearch);
  const childrenVisible = (folder.children || []).some(folderHasVisibleContent);
  return linksVisible || childrenVisible;
}

function renderLinkCard(link) {
  if (!linkMatchesSearch(link)) return "";
  const favicon = link.icon_url || iconUrl("ui", "external-link");
  const desc = link.description
    ? `<div class="link-description">${escapeHtml(link.description)}</div>`
    : "";
  return `<div class="link-card" data-id="${link.id}" data-open-link="${link.id}" data-url="${escapeHtml(link.url)}"
    draggable="true" data-drag-type="link" data-drag-id="${link.id}" role="link" tabindex="0">
    <button class="icon-btn link-delete" data-delete-link="${link.id}" type="button" aria-label="Delete link">
      <img class="icon-ui" src="${iconUrl("ui", "close")}" alt="" width="14" height="14">
    </button>
    <div class="link-card-body">
      <div class="link-title-row">
        <img class="link-favicon" src="${escapeHtml(favicon)}" alt="" width="20" height="20" loading="lazy">
        <span>${escapeHtml(link.title)}</span>
      </div>
      ${desc}
      <div class="link-meta">${link.click_count} clicks</div>
    </div>
  </div>`;
}

function renderFolderNode(folder, depth = 0) {
  if (linksSearchQuery && !folderHasVisibleContent(folder)) return "";
  const collapsed = collapsedFolders.has(folder.id) && !linksSearchQuery;
  const count = folderLinkCount(folder);
  const chevron = collapsed ? "▸" : "▾";
  const linksHtml = (folder.links || []).map(renderLinkCard).filter(Boolean).join("");
  const childrenHtml = (folder.children || [])
    .map((c) => renderFolderNode(c, depth + 1))
    .filter(Boolean)
    .join("");
  return `<div class="link-folder" data-folder-id="${folder.id}" style="--folder-depth:${depth}">
    <div class="folder-header" data-folder-header="${folder.id}" data-drag-type="folder" data-drag-id="${folder.id}" draggable="true">
      <button type="button" class="folder-toggle" data-toggle-folder="${folder.id}" aria-label="Toggle folder">${chevron}</button>
      <span class="folder-name" data-rename-folder="${folder.id}">${escapeHtml(folder.name)}</span>
      <span class="folder-count">${count}</span>
      <button type="button" class="icon-btn folder-delete" data-delete-folder="${folder.id}" aria-label="Delete folder">
        <img class="icon-ui" src="${iconUrl("ui", "close")}" alt="" width="12" height="12">
      </button>
    </div>
    <div class="folder-children${collapsed ? " collapsed" : ""}">
      <div class="folder-links">${linksHtml}</div>
      ${childrenHtml}
    </div>
  </div>`;
}

function renderLinksTree(containerSel) {
  const grid = $(containerSel);
  if (!grid) return;
  const hasFolders = (linksTree.folders || []).length > 0;
  const hasLinks = (linksTree.links || []).length > 0;
  if (!hasFolders && !hasLinks) {
    grid.innerHTML = '<p class="empty-state">No links yet. Click Add Link.</p>';
    return;
  }
  const foldersHtml = (linksTree.folders || [])
    .map((f) => renderFolderNode(f, 0))
    .filter(Boolean)
    .join("");
  const rootLinks = (linksTree.links || []).map(renderLinkCard).filter(Boolean).join("");
  grid.innerHTML = `<div class="links-tree-root">${foldersHtml}<div class="links-root-items">${rootLinks}</div></div>`;
  if (!rootLinks && !foldersHtml && linksSearchQuery) {
    grid.innerHTML = '<p class="empty-state">No matching links</p>';
  }
}

function syncLinksSearchInputs() {
  const a = $("#links-search");
  const b = $("#links-search-full");
  if (a) a.value = linksSearchQuery;
  if (b) b.value = linksSearchQuery;
}

function collectFolderIds(folders, acc = []) {
  for (const f of folders || []) {
    acc.push(f.id);
    collectFolderIds(f.children, acc);
  }
  return acc;
}

function isFolderDescendant(folderId, ancestorId, folders) {
  for (const f of folders || []) {
    if (f.id === ancestorId) {
      return collectFolderIds(f.children, []).includes(folderId);
    }
    if (isFolderDescendant(folderId, ancestorId, f.children)) return true;
  }
  return false;
}

function allFoldersFlat(folders, acc = []) {
  for (const f of folders || []) {
    acc.push(f);
    allFoldersFlat(f.children, acc);
  }
  return acc;
}

function renderAllWeather() {
  renderWeatherTo("#weather-grid", weatherData, false);
  renderWeatherTo("#weather-full-grid", weatherData, true);
}

function renderAllNews() {
  renderNewsTo("#news-grid", newsData, false);
  if (newsTab === "feed") {
    renderNewsTo("#news-full-grid", newsData, true);
  }
}

function renderAllLinks() {
  renderLinksTree("#links-grid");
  renderLinksTree("#links-full-grid");
}

function renderLocList(containerId, items, type) {
  const ul = $(containerId);
  if (!ul) return;
  ul.innerHTML = items.map((loc) =>
    `<li>
      <span>${escapeHtml(loc.label)}</span>
      <button class="icon-btn" data-remove-${type}="${loc.id}" type="button">
        <img class="icon-ui" src="${iconUrl("ui", "close")}" alt="" width="14" height="14">
      </button>
    </li>`
  ).join("");
}

function showView(view, opts = {}) {
  currentView = view;
  $$(".view-panel").forEach((el) => el.classList.add("hidden"));
  const target = $(`#view-${view}`);
  if (target) target.classList.remove("hidden");
  $$(".nav-item").forEach((btn) => {
    const v = btn.dataset.view;
    const tab = btn.dataset.newsTab;
    let active = false;
    if (view === v) {
      if (view === "news") {
        active = tab ? tab === (opts.tab || newsTab) : (opts.tab || newsTab) === "feed";
      } else {
        active = !tab;
      }
    }
    btn.classList.toggle("active", active);
  });
  if (view === "news") {
    setNewsTab(opts.tab || newsTab || "feed");
    renderAllNews();
  }
  closeDrawer();
  hideNewsPreview();
  window.scrollTo({ top: 0, behavior: "smooth" });
}

async function loadWeather() {
  try {
    weatherData = await api("/api/weather");
    renderAllWeather();
  } catch (e) {
    const msg = `<p class="error-text">${escapeHtml(e.message)}</p>`;
    $("#weather-grid").innerHTML = msg;
    const full = $("#weather-full-grid");
    if (full) full.innerHTML = msg;
  }
}

async function loadNews(refresh = false) {
  try {
    const q = refresh ? "?refresh=true" : "";
    newsData = await api(`/api/news${q}`);
    renderAllNews();
  } catch (e) {
    const msg = `<p class="error-text">${escapeHtml(e.message)}</p>`;
    $("#news-grid").innerHTML = msg;
    const full = $("#news-full-grid");
    if (full) full.innerHTML = msg;
  }
}

async function loadLinks() {
  const sort = localStorage.getItem("linksSort") || $("#sort-select").value;
  $("#sort-select").value = sort;
  const fullSort = $("#sort-select-full");
  if (fullSort) fullSort.value = sort;
  linksTree = await api(`/api/links/tree?sort=${encodeURIComponent(sort)}`);
  renderAllLinks();
}

async function createFolder(name, parentId = null) {
  await api("/api/links/folders", {
    method: "POST",
    body: JSON.stringify({ name, parent_id: parentId }),
  });
  await loadLinks();
}

function openFolderFromLinksModal(linkIdA, linkIdB) {
  pendingFolderLinkIds = [linkIdA, linkIdB];
  const input = $("#folder-from-links-ids");
  if (input) input.value = `${linkIdA},${linkIdB}`;
  $("#folder-from-links-modal")?.showModal();
}

async function importLinksFile(file) {
  const ext = (file.name.split(".").pop() || "").toLowerCase();
  const format = ext === "html" || ext === "htm" ? "html" : "json";
  const fd = new FormData();
  fd.append("file", file);
  const res = await fetch(`/api/links/import?format=${format}`, { method: "POST", body: fd });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || res.statusText);
  }
  return res.json();
}

function downloadExport(format) {
  window.location.href = `/api/links/export?format=${format}`;
}

function initLinksDnD() {
  document.addEventListener("dragstart", (e) => {
    const card = e.target.closest("[data-drag-type]");
    if (!card) return;
    dragPayload = {
      type: card.dataset.dragType,
      id: Number(card.dataset.dragId),
    };
    e.dataTransfer.effectAllowed = "move";
    e.dataTransfer.setData("text/plain", String(dragPayload.id));
  });

  document.addEventListener("dragend", () => {
    dragPayload = null;
    $$(".drag-over").forEach((el) => el.classList.remove("drag-over"));
  });

  document.addEventListener("dragover", (e) => {
    const target = e.target.closest("[data-folder-header], .link-card[data-drag-type='link']");
    if (!target || !dragPayload) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
    $$(".drag-over").forEach((el) => el.classList.remove("drag-over"));
    target.classList.add("drag-over");
  });

  document.addEventListener("dragleave", (e) => {
    const target = e.target.closest("[data-folder-header], .link-card");
    if (target) target.classList.remove("drag-over");
  });

  document.addEventListener("drop", async (e) => {
    const folderHeader = e.target.closest("[data-folder-header]");
    const linkCard = e.target.closest(".link-card[data-drag-type='link']");
    $$(".drag-over").forEach((el) => el.classList.remove("drag-over"));
    if (!dragPayload) return;
    e.preventDefault();

    if (dragPayload.type === "link" && folderHeader) {
      const folderId = Number(folderHeader.dataset.folderHeader);
      await api(`/api/links/${dragPayload.id}`, {
        method: "PATCH",
        body: JSON.stringify({ folder_id: folderId }),
      });
      await loadLinks();
      return;
    }

    if (dragPayload.type === "link" && linkCard) {
      const targetId = Number(linkCard.dataset.dragId);
      if (targetId !== dragPayload.id) {
        openFolderFromLinksModal(dragPayload.id, targetId);
      }
      return;
    }

    if (dragPayload.type === "folder" && folderHeader) {
      const targetFolderId = Number(folderHeader.dataset.folderHeader);
      if (dragPayload.id === targetFolderId) return;
      if (isFolderDescendant(targetFolderId, dragPayload.id, linksTree.folders)) return;
      await api(`/api/links/folders/${dragPayload.id}`, {
        method: "PATCH",
        body: JSON.stringify({ parent_id: targetFolderId }),
      });
      await loadLinks();
    }
  });
}

async function loadSettingsLocs() {
  const weather = await api("/api/weather/locations");
  const news = await api("/api/news/locations");
  renderLocList("#settings-weather-locs", weather, "weather");
  renderLocList("#settings-news-locs", news, "news");
}

async function loadSettings() {
  const s = await api("/api/settings");
  $("#default-sort-select").value = s.default_links_sort || "most_used";
  const sort = localStorage.getItem("linksSort") || s.default_links_sort || "most_used";
  $("#sort-select").value = sort;
  await loadSettingsLocs();
}

async function addLocation(type, label) {
  const path = type === "weather" ? "/api/weather/locations" : "/api/news/locations";
  await api(path, { method: "POST", body: JSON.stringify({ label }) });
  await loadSettingsLocs();
  if (type === "weather") await loadWeather();
  else await loadNews(true);
}

async function removeLocation(type, id) {
  const path = type === "weather" ? `/api/weather/locations/${id}` : `/api/news/locations/${id}`;
  await api(path, { method: "DELETE" });
  await loadSettingsLocs();
  if (type === "weather") await loadWeather();
  else await loadNews(true);
}

function openDrawer() {
  $("#settings-drawer").classList.remove("hidden");
  $("#drawer-overlay").classList.remove("hidden");
}

function closeDrawer() {
  $("#settings-drawer").classList.add("hidden");
  $("#drawer-overlay").classList.add("hidden");
}

function hideNewsPreview() {
  const el = $("#news-preview");
  if (el) {
    el.classList.add("hidden");
    el.setAttribute("aria-hidden", "true");
  }
}

async function enrichPreview(item) {
  const url = item.dataset.url;
  let image = item.dataset.image || "";
  let desc = item.dataset.desc || "";
  if ((!image || !desc) && url) {
    if (previewCache.has(url)) {
      const cached = previewCache.get(url);
      image = image || cached.image_url || "";
      desc = desc || cached.description || "";
    } else {
      try {
        const data = await api(`/api/news/preview?url=${encodeURIComponent(url)}`);
        previewCache.set(url, data);
        image = image || data.image_url || "";
        desc = desc || data.description || "";
      } catch {
        previewCache.set(url, {});
      }
    }
  }
  return {
    title: item.dataset.title,
    source: item.dataset.source,
    image,
    desc: desc || "Open article for full story.",
  };
}

function showNewsPreview(item, x, y) {
  const el = $("#news-preview");
  if (!el) return;
  enrichPreview(item).then((data) => {
    const imgHtml = data.image
      ? `<img class="news-preview-img" src="${escapeHtml(data.image)}" alt="">`
      : `<div class="news-preview-img"></div>`;
    el.innerHTML = `${imgHtml}
      <div class="news-preview-body">
        <p class="news-preview-title">${escapeHtml(data.title)}</p>
        <p class="news-preview-desc">${escapeHtml(data.desc)}</p>
        ${data.source ? `<div class="news-preview-source">${escapeHtml(data.source)}</div>` : ""}
      </div>`;
    el.classList.remove("hidden");
    el.setAttribute("aria-hidden", "false");
    const pad = 16;
    const rect = el.getBoundingClientRect();
    let left = x + pad;
    let top = y + pad;
    if (left + rect.width > window.innerWidth - pad) {
      left = x - rect.width - pad;
    }
    if (top + rect.height > window.innerHeight - pad) {
      top = y - rect.height - pad;
    }
    el.style.left = `${Math.max(pad, left)}px`;
    el.style.top = `${Math.max(pad, top)}px`;
  });
}

function initNewsPreview() {
  document.addEventListener("mouseover", (e) => {
    const item = e.target.closest(".news-hover-item");
    if (item) {
      showNewsPreview(item, e.clientX, e.clientY);
      return;
    }
    if (!e.target.closest("#news-preview")) {
      hideNewsPreview();
    }
  });
  document.addEventListener("mousemove", (e) => {
    const item = e.target.closest(".news-hover-item");
    if (item) {
      const el = $("#news-preview");
      if (el && !el.classList.contains("hidden")) {
        const pad = 16;
        let left = e.clientX + pad;
        let top = e.clientY + pad;
        const rect = el.getBoundingClientRect();
        if (left + rect.width > window.innerWidth - pad) left = e.clientX - rect.width - pad;
        if (top + rect.height > window.innerHeight - pad) top = e.clientY - rect.height - pad;
        el.style.left = `${Math.max(pad, left)}px`;
        el.style.top = `${Math.max(pad, top)}px`;
      }
    }
  });
}

$("#close-weather-detail")?.addEventListener("click", () => {
  $("#weather-detail-modal")?.close();
});

$("#menu-btn").addEventListener("click", openDrawer);
$("#close-settings").addEventListener("click", closeDrawer);
$("#drawer-overlay").addEventListener("click", closeDrawer);

$$(".nav-item, .back-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    const view = btn.dataset.view;
    if (view) showView(view, { tab: btn.dataset.newsTab });
  });
});

$$(".news-tab").forEach((btn) => {
  btn.addEventListener("click", () => setNewsTab(btn.dataset.newsTab));
});

$("#news-search")?.addEventListener("input", (e) => {
  newsSearchQuery = e.target.value.trim();
  syncNewsSearchInputs();
  renderAllNews();
});

$("#news-search-full")?.addEventListener("input", (e) => {
  newsSearchQuery = e.target.value.trim();
  syncNewsSearchInputs();
  renderAllNews();
});

$("#saved-search")?.addEventListener("input", (e) => {
  savedSearchQuery = e.target.value.trim();
  renderSavedNewsList();
});

$("#news-filters-btn")?.addEventListener("click", openNewsFilters);
$("#news-filters-btn-full")?.addEventListener("click", openNewsFilters);
$("#close-news-filters")?.addEventListener("click", () => $("#news-filters-modal")?.close());
$("#cancel-news-filters")?.addEventListener("click", () => $("#news-filters-modal")?.close());
$("#news-filters-form")?.addEventListener("submit", applyNewsFilters);

$$(".news-age-chips .news-chip").forEach((chip) => {
  chip.addEventListener("click", () => quickSetAgeMode(chip.dataset.ageMode));
});

$("#cancel-news-save")?.addEventListener("click", () => {
  pendingSaveArticle = null;
  $("#news-save-modal")?.close();
});
$("#news-save-form")?.addEventListener("submit", submitSaveArticle);

$("#add-link-btn").addEventListener("click", () => $("#add-link-modal").showModal());
$("#add-link-full-btn")?.addEventListener("click", () => $("#add-link-modal").showModal());
$("#cancel-link").addEventListener("click", () => $("#add-link-modal").close());

$("#add-link-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  await api("/api/links", {
    method: "POST",
    body: JSON.stringify({
      title: fd.get("title"),
      url: fd.get("url"),
      description: fd.get("description") || "",
    }),
  });
  $("#add-link-modal").close();
  e.target.reset();
  await loadLinks();
});

function openNewFolderModal() {
  $("#new-folder-modal")?.showModal();
}

$("#new-folder-btn")?.addEventListener("click", openNewFolderModal);
$("#new-folder-full-btn")?.addEventListener("click", openNewFolderModal);
$("#cancel-folder")?.addEventListener("click", () => $("#new-folder-modal")?.close());
$("#new-folder-form")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const name = new FormData(e.target).get("name");
  await createFolder(String(name).trim());
  $("#new-folder-modal")?.close();
  e.target.reset();
});

$("#cancel-folder-from-links")?.addEventListener("click", () => {
  pendingFolderLinkIds = null;
  $("#folder-from-links-modal")?.close();
});
$("#folder-from-links-form")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const ids = pendingFolderLinkIds || String(fd.get("link_ids") || "").split(",").map(Number);
  if (ids.length !== 2) return;
  await api("/api/links/folders/from-links", {
    method: "POST",
    body: JSON.stringify({
      link_ids: ids,
      name: fd.get("name") || "New folder",
    }),
  });
  pendingFolderLinkIds = null;
  $("#folder-from-links-modal")?.close();
  e.target.reset();
  await loadLinks();
});

function bindLinksSearchInput(sel) {
  $(sel)?.addEventListener("input", (e) => {
    linksSearchQuery = e.target.value.trim();
    syncLinksSearchInputs();
    renderAllLinks();
  });
}
bindLinksSearchInput("#links-search");
bindLinksSearchInput("#links-search-full");

function bindImportButton(btnSel, fileSel) {
  const btn = $(btnSel);
  const file = $(fileSel);
  if (!btn || !file) return;
  btn.addEventListener("click", () => file.click());
  file.addEventListener("change", async () => {
    const f = file.files?.[0];
    if (!f) return;
    try {
      const result = await importLinksFile(f);
      alert(`Imported ${result.imported} links (${result.skipped} skipped, ${result.folders_created} folders)`);
      await loadLinks();
    } catch (err) {
      alert(err.message || "Import failed");
    }
    file.value = "";
  });
}
bindImportButton("#links-import-btn", "#links-import-file");
bindImportButton("#links-import-full-btn", "#links-import-file-full");

$("#links-export-json")?.addEventListener("click", () => downloadExport("json"));
$("#links-export-html")?.addEventListener("click", () => downloadExport("html"));
$("#links-export-json-full")?.addEventListener("click", () => downloadExport("json"));
$("#links-export-html-full")?.addEventListener("click", () => downloadExport("html"));

$$(".add-loc-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    addLocType = btn.dataset.type;
    $("#add-loc-title").textContent =
      addLocType === "weather" ? "Add Weather Location" : "Add News Location";
    $("#add-loc-modal").showModal();
  });
});

$("#cancel-loc").addEventListener("click", () => $("#add-loc-modal").close());

$("#add-loc-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  await addLocation(addLocType, fd.get("label"));
  $("#add-loc-modal").close();
  e.target.reset();
});

$("#settings-weather-add").addEventListener("click", async () => {
  const input = $("#settings-weather-input");
  if (input.value.trim()) {
    await addLocation("weather", input.value.trim());
    input.value = "";
  }
});

$("#settings-news-add").addEventListener("click", async () => {
  const input = $("#settings-news-input");
  if (input.value.trim()) {
    await addLocation("news", input.value.trim());
    input.value = "";
  }
});

$("#default-sort-select").addEventListener("change", async (e) => {
  await api("/api/settings", {
    method: "POST",
    body: JSON.stringify({ default_links_sort: e.target.value }),
  });
});

function bindSortSelect(sel) {
  $(sel)?.addEventListener("change", async (e) => {
    localStorage.setItem("linksSort", e.target.value);
    const other = sel === "#sort-select" ? "#sort-select-full" : "#sort-select";
    const otherEl = $(other);
    if (otherEl) otherEl.value = e.target.value;
    await loadLinks();
  });
}

bindSortSelect("#sort-select");
bindSortSelect("#sort-select-full");

async function openLinkCard(card) {
  const id = card.dataset.openLink;
  if (!id) return;
  const { url } = await api(`/api/links/${id}/click`, { method: "POST" });
  window.open(url, "_blank");
  await loadLinks();
}

document.addEventListener("click", async (e) => {
  const weatherCard = e.target.closest("[data-weather-id]");
  if (weatherCard && !e.target.closest("button, .icon-btn")) {
    const id = Number(weatherCard.dataset.weatherId);
    const w = weatherData.find((item) => item.id === id);
    if (w) openWeatherDetail(w);
    return;
  }

  const openCard = e.target.closest(".link-card[data-open-link]");
  if (openCard && !e.target.closest("[data-delete-link]")) {
    e.preventDefault();
    await openLinkCard(openCard);
    return;
  }

  const delLink = e.target.closest("[data-delete-link]");
  if (delLink) {
    await api(`/api/links/${delLink.dataset.deleteLink}`, { method: "DELETE" });
    await loadLinks();
    return;
  }

  const toggleFolder = e.target.closest("[data-toggle-folder]");
  if (toggleFolder) {
    e.preventDefault();
    const id = Number(toggleFolder.dataset.toggleFolder);
    if (collapsedFolders.has(id)) collapsedFolders.delete(id);
    else collapsedFolders.add(id);
    renderAllLinks();
    return;
  }

  const delFolder = e.target.closest("[data-delete-folder]");
  if (delFolder) {
    e.preventDefault();
    if (!confirm("Delete this folder? Links will move to the parent folder.")) return;
    await api(`/api/links/folders/${delFolder.dataset.deleteFolder}`, { method: "DELETE" });
    await loadLinks();
    return;
  }

  const renameFolder = e.target.closest("[data-rename-folder]");
  if (renameFolder && e.detail === 2) {
    const id = Number(renameFolder.dataset.renameFolder);
    const next = prompt("Rename folder", renameFolder.textContent);
    if (next && next.trim()) {
      await api(`/api/links/folders/${id}`, {
        method: "PATCH",
        body: JSON.stringify({ name: next.trim() }),
      });
      await loadLinks();
    }
    return;
  }

  const rmWeather = e.target.closest("[data-remove-weather]");
  if (rmWeather) {
    await removeLocation("weather", rmWeather.dataset.removeWeather);
    return;
  }

  const rmNews = e.target.closest("[data-remove-news]");
  if (rmNews) {
    await removeLocation("news", rmNews.dataset.removeNews);
    return;
  }

  const newsLink = e.target.closest("[data-news-link]");
  if (newsLink) {
    markNewsRead(newsLink.getAttribute("href"));
    return;
  }

  const saveBtn = e.target.closest("[data-save-article]");
  if (saveBtn) {
    e.preventDefault();
    e.stopPropagation();
    try {
      const article = JSON.parse(decodeURIComponent(saveBtn.dataset.saveArticle));
      openSaveModal(article);
    } catch {
      /* ignore */
    }
    return;
  }

  const clusterToggle = e.target.closest("[data-toggle-cluster]");
  if (clusterToggle) {
    e.preventDefault();
    const key = clusterToggle.dataset.toggleCluster;
    if (expandedClusters.has(key)) expandedClusters.delete(key);
    else expandedClusters.add(key);
    renderAllNews();
    return;
  }

  const delSaved = e.target.closest("[data-delete-saved]");
  if (delSaved) {
    await api(`/api/news/saved/${delSaved.dataset.deleteSaved}`, { method: "DELETE" });
    await loadSavedArticles();
    await loadNews(false);
    return;
  }

  const savedTagChip = e.target.closest("[data-saved-tag]");
  if (savedTagChip) {
    savedTagFilter = savedTagChip.dataset.savedTag || "";
    renderSavedNewsList();
  }
});

document.addEventListener(
  "blur",
  async (e) => {
    const notes = e.target.closest("[data-saved-notes]");
    if (!notes) return;
    const id = notes.dataset.savedNotes;
    await api(`/api/news/saved/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ notes: notes.value }),
    });
    await loadSavedArticles();
  },
  true
);

document.addEventListener("keydown", async (e) => {
  if (e.key !== "Enter" && e.key !== " ") return;
  const card = e.target.closest(".link-card[data-open-link]");
  if (!card || e.target.closest("[data-delete-link]")) return;
  e.preventDefault();
  await openLinkCard(card);
});

const NEWS_REFRESH_MS = 5 * 60 * 60 * 1000; // 5 hours

function initGoogleSearch() {
  const form = $("#google-search-form");
  const input = $("#google-search-input");
  if (!form || !input) return;

  const saved = sessionStorage.getItem("googleSearchQuery");
  if (saved) input.value = saved;

  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const q = input.value.trim();
    if (!q) return;
    sessionStorage.setItem("googleSearchQuery", q);
    window.open(`https://www.google.com/search?q=${encodeURIComponent(q)}`, "_blank", "noopener");
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "/" && currentView === "dashboard") {
      const tag = document.activeElement?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
      e.preventDefault();
      input.focus();
      return;
    }
    if (e.key === "Escape" && document.activeElement === input) {
      input.blur();
    }
  });
}

async function init() {
  initMouseBackground();
  initGoogleSearch();
  initNewsPreview();
  initLinksDnD();
  initUpdateChecker();
  await loadSettings();
  await loadNewsPrefs();
  await Promise.all([loadWeather(), loadNews(), loadLinks(), loadSavedArticles()]);
  setInterval(loadWeather, 600000);
  setInterval(() => loadNews(false), NEWS_REFRESH_MS);
}

const UPDATE_POLL_MS = 300000;
let updateApplying = false;

function dismissUpdate(sha) {
  if (sha) sessionStorage.setItem("dismissedUpdate", sha);
  $("#update-toast")?.classList.add("hidden");
}

function showUpdateToast(status) {
  const toast = $("#update-toast");
  const msg = $("#update-toast-msg");
  if (!toast || !msg || !status.update_available) return;
  if (sessionStorage.getItem("dismissedUpdate") === status.remote_sha) return;

  const local = status.local_short_sha || "local";
  const remote = status.remote_short_sha || "new";
  const text = status.message
    ? `${status.message} (${local} → ${remote})`
    : `Version ${local} → ${remote}`;
  msg.textContent = text;
  toast.classList.remove("hidden");
}

async function checkForUpdates() {
  if (updateApplying) return;
  try {
    const status = await api("/api/updates/check");
    if (status.update_available) {
      showUpdateToast(status);
    } else {
      $("#update-toast")?.classList.add("hidden");
    }
  } catch {
    /* ignore */
  }
}

async function applyUpdate() {
  if (updateApplying) return;
  const toast = $("#update-toast");
  const msg = $("#update-toast-msg");
  updateApplying = true;
  toast?.classList.add("updating");
  if (msg) msg.textContent = "Downloading update…";

  try {
    const result = await api("/api/updates/apply", { method: "POST" });
    if (result.restarted) {
      if (msg) msg.textContent = "Updated — restarting…";
      setTimeout(() => location.reload(), 4000);
      return;
    }
    if (result.restart_required) {
      if (msg) msg.textContent = "Updated. Restart start.py to finish.";
      toast?.classList.remove("updating");
      updateApplying = false;
      return;
    }
    if (msg) msg.textContent = result.message || "Already up to date.";
    toast?.classList.add("hidden");
  } catch (e) {
    if (msg) msg.textContent = e.message || "Update failed";
    toast?.classList.remove("updating");
  }
  updateApplying = false;
}

function initUpdateChecker() {
  $("#update-apply-btn")?.addEventListener("click", applyUpdate);
  $("#update-dismiss-btn")?.addEventListener("click", async () => {
    try {
      const status = await api("/api/updates/check");
      dismissUpdate(status.remote_sha);
    } catch {
      $("#update-toast")?.classList.add("hidden");
    }
  });
  checkForUpdates();
  setInterval(checkForUpdates, UPDATE_POLL_MS);
}

function initMouseBackground() {
  const bg = $("#mouse-bg");
  if (!bg) return;
  let raf = 0;
  const update = (x, y) => {
    bg.style.setProperty("--mouse-x", `${x}px`);
    bg.style.setProperty("--mouse-y", `${y}px`);
  };
  document.addEventListener("mousemove", (e) => {
    if (raf) return;
    raf = requestAnimationFrame(() => {
      update(e.clientX, e.clientY);
      raf = 0;
    });
  });
  update(window.innerWidth / 2, window.innerHeight / 2);
}

init();
