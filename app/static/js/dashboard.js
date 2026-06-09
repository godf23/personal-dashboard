const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

let addLocType = "weather";
let currentView = "dashboard";
let weatherData = [];
let newsData = [];
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

function formatNewsArticle(a, expanded) {
  const source = a.source ? `<span class="news-source-badge">${escapeHtml(a.source)}</span>` : "";
  const cls = expanded ? "news-article" : "";
  const tag = expanded ? "div" : "li";
  const desc = escapeHtml(a.description || "");
  const img = escapeHtml(a.image_url || "");
  return `<${tag} class="${cls} news-hover-item"
    data-title="${escapeHtml(a.title)}"
    data-url="${escapeHtml(a.url)}"
    data-source="${escapeHtml(a.source || "")}"
    data-desc="${desc}"
    data-image="${img}">
    <a href="${escapeHtml(a.url)}" target="_blank" rel="noopener">${escapeHtml(a.title)}</a>
    <div class="news-source">${source}</div>
  </${tag}>`;
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
    const forecast = renderForecast(w.forecast_7day, !expanded);
    return `<div class="weather-card ${mood}" data-id="${w.id}">
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
        <div class="weather-footer">${w.active_sources}/${w.total_sources} sources${w.cached ? " (cached)" : ""}</div>
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
    const articles = (f.articles || []).map((a) => formatNewsArticle(a, expanded)).join("");
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

function renderLinksTo(gridSel, links) {
  const grid = $(gridSel);
  if (!grid) return;
  if (!links.length) {
    grid.innerHTML = '<p class="empty-state">No links yet. Click Add Link.</p>';
    return;
  }
  grid.innerHTML = links.map((l) => {
    const favicon = l.icon_url || iconUrl("ui", "external-link");
    return `<div class="link-card" data-id="${l.id}">
      <button class="icon-btn link-delete" data-delete-link="${l.id}" type="button">
        <img class="icon-ui" src="${iconUrl("ui", "close")}" alt="" width="14" height="14">
      </button>
      <a href="#" data-open-link="${l.id}" data-url="${escapeHtml(l.url)}">
        <img class="link-favicon" src="${escapeHtml(favicon)}" alt="" width="20" height="20" loading="lazy">
        ${escapeHtml(l.title)}
      </a>
      <div class="link-meta">${l.click_count} clicks</div>
    </div>`;
  }).join("");
}

function renderAllWeather() {
  renderWeatherTo("#weather-grid", weatherData, false);
  renderWeatherTo("#weather-full-grid", weatherData, true);
}

function renderAllNews() {
  renderNewsTo("#news-grid", newsData, false);
  renderNewsTo("#news-full-grid", newsData, true);
}

function renderAllLinks(links) {
  renderLinksTo("#links-grid", links);
  renderLinksTo("#links-full-grid", links);
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

function showView(view) {
  currentView = view;
  $$(".view-panel").forEach((el) => el.classList.add("hidden"));
  const target = $(`#view-${view}`);
  if (target) target.classList.remove("hidden");
  $$(".nav-item").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.view === view);
  });
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

async function loadNews() {
  try {
    newsData = await api("/api/news");
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
  const links = await api(`/api/links?sort=${sort}`);
  renderAllLinks(links);
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
  else await loadNews();
}

async function removeLocation(type, id) {
  const path = type === "weather" ? `/api/weather/locations/${id}` : `/api/news/locations/${id}`;
  await api(path, { method: "DELETE" });
  await loadSettingsLocs();
  if (type === "weather") await loadWeather();
  else await loadNews();
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

$("#menu-btn").addEventListener("click", openDrawer);
$("#close-settings").addEventListener("click", closeDrawer);
$("#drawer-overlay").addEventListener("click", closeDrawer);

$$(".nav-item, .back-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    const view = btn.dataset.view;
    if (view) showView(view);
  });
});

$("#add-link-btn").addEventListener("click", () => $("#add-link-modal").showModal());
$("#add-link-full-btn")?.addEventListener("click", () => $("#add-link-modal").showModal());
$("#cancel-link").addEventListener("click", () => $("#add-link-modal").close());

$("#add-link-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  await api("/api/links", {
    method: "POST",
    body: JSON.stringify({ title: fd.get("title"), url: fd.get("url") }),
  });
  $("#add-link-modal").close();
  e.target.reset();
  await loadLinks();
});

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

document.addEventListener("click", async (e) => {
  const openBtn = e.target.closest("[data-open-link]");
  if (openBtn) {
    e.preventDefault();
    const id = openBtn.dataset.openLink;
    const { url } = await api(`/api/links/${id}/click`, { method: "POST" });
    window.open(url, "_blank");
    await loadLinks();
    return;
  }

  const delLink = e.target.closest("[data-delete-link]");
  if (delLink) {
    await api(`/api/links/${delLink.dataset.deleteLink}`, { method: "DELETE" });
    await loadLinks();
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
  }
});

async function init() {
  initMouseBackground();
  initNewsPreview();
  await loadSettings();
  await Promise.all([loadWeather(), loadNews(), loadLinks()]);
  setInterval(loadWeather, 600000);
  setInterval(loadNews, 300000);
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
