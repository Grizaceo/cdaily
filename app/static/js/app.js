// ── State ─────────────────────────────────────────────────────────────────────
const state = {
    activeCategory: null,   // null = All
    query: "",
    unreadOnly: false,
    starredOnly: false,
    articles: [],
    stats: {},
    lastRefresh: null,
};

// ── Constants ───────────────────────────────────────────────────────────────
const CATEGORIES = [
    { key: null,           label: "All",      emoji: "📰" },
    { key: "news",        label: "News",     emoji: "📰" },
    { key: "tech",        label: "Tech",     emoji: "💻" },
    { key: "science",     label: "Science",  emoji: "🔬" },
    { key: "business",    label: "Biz",      emoji: "💼" },
    { key: "culture",     label: "Culture",  emoji: "🎭" },
    { key: "security",    label: "Sec",      emoji: "🔐" },
];

// ── Init ────────────────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
    initFilters();
    bindEvents();
    loadData();
    startAutoRefresh();
});

// ── Filter Pills ────────────────────────────────────────────────────────────
function initFilters() {
    const bar = document.getElementById("filter-bar");
    bar.innerHTML = "";
    CATEGORIES.forEach(({ key, label, emoji }) => {
        const btn = document.createElement("button");
        btn.className = "filter-pill";
        btn.dataset.cat = key ?? "";
        btn.innerHTML = `${emoji} ${label}`;
        bar.appendChild(btn);
    });
}

// ── Event Bindings ──────────────────────────────────────────────────────────
function bindEvents() {
    // Category pills
    document.getElementById("filter-bar").addEventListener("click", (e) => {
        const pill = e.target.closest(".filter-pill");
        if (!pill) return;
        setCategory(pill.dataset.cat || null);
    });

    // Search with debounce
    const searchInput = document.getElementById("search-input");
    let debounceTimer;
    searchInput.addEventListener("input", () => {
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(() => {
            state.query = searchInput.value.trim();
            loadArticles();
        }, 300);
    });

    // Mark all read
    document.getElementById("mark-all-btn").addEventListener("click", async () => {
        if (!confirm("¿Marcar todos como leídos?")) return;
        await api("POST", "/api/articles/read-all");
        loadData();
        toast("Todos marcados como leídos");
    });

    // Refresh / force scan
    document.getElementById("refresh-btn").addEventListener("click", async () => {
        setRefreshIndicator(true);
        await api("POST", "/api/scan");
        await loadData();
        setRefreshIndicator(false);
        toast("Feed actualizado");
    });

    // Settings modal binding
    const settingsBtn = document.getElementById("settings-btn");
    const settingsModal = document.getElementById("settings-modal");
    const settingsCloseBtn = document.getElementById("settings-close-btn");
    const settingsForm = document.getElementById("settings-form");
    const settingsTestBtn = document.getElementById("settings-test-btn");
    const authTypeSelect = document.getElementById("ai-auth-type");
    const authHeaderNameContainer = document.getElementById("auth-header-name-container");
    const apiKeyContainer = document.getElementById("api-key-container");
    const alertContainer = document.getElementById("settings-alert-container");

    const updateAuthFieldsVisibility = () => {
        const type = authTypeSelect.value;
        if (type === "none") {
            authHeaderNameContainer.hidden = true;
            apiKeyContainer.hidden = true;
        } else if (type === "bearer") {
            authHeaderNameContainer.hidden = true;
            apiKeyContainer.hidden = false;
        } else if (type === "custom") {
            authHeaderNameContainer.hidden = false;
            apiKeyContainer.hidden = false;
        }
    };

    authTypeSelect.addEventListener("change", updateAuthFieldsVisibility);

    const showAlert = (message, type = "success") => {
        alertContainer.textContent = message;
        alertContainer.className = `settings-alert ${type}`;
        alertContainer.hidden = false;
    };

    const hideAlert = () => {
        alertContainer.hidden = true;
        alertContainer.textContent = "";
    };

    settingsBtn.addEventListener("click", async () => {
        hideAlert();
        settingsModal.hidden = false;
        try {
            const config = await api("GET", "/api/settings");
            document.getElementById("ai-enabled").checked = !!config.enabled;
            document.getElementById("ai-endpoint").value = config.endpoint || "";
            document.getElementById("ai-api-key").value = config.api_key || "";
            document.getElementById("ai-model").value = config.model || "";
            document.getElementById("ai-prompt").value = config.system_prompt || "";
            document.getElementById("ai-max-chars").value = config.max_content_chars || 12000;
            authTypeSelect.value = config.auth_type || "none";
            document.getElementById("ai-auth-header-name").value = config.auth_header_name || "";
            updateAuthFieldsVisibility();
        } catch (err) {
            showAlert("No se pudo cargar la configuración de la IA", "error");
        }
    });

    settingsCloseBtn.addEventListener("click", () => {
        settingsModal.hidden = true;
    });

    // Close when clicking outside card
    settingsModal.addEventListener("click", (e) => {
        if (e.target === settingsModal) {
            settingsModal.hidden = true;
        }
    });

    const getFormData = () => {
        return {
            enabled: document.getElementById("ai-enabled").checked,
            endpoint: document.getElementById("ai-endpoint").value.trim(),
            api_key: document.getElementById("ai-api-key").value.trim(),
            model: document.getElementById("ai-model").value.trim(),
            system_prompt: document.getElementById("ai-prompt").value.trim(),
            max_content_chars: parseInt(document.getElementById("ai-max-chars").value) || 12000,
            auth_type: authTypeSelect.value,
            auth_header_name: document.getElementById("ai-auth-header-name").value.trim()
        };
    };

    settingsTestBtn.addEventListener("click", async () => {
        hideAlert();
        settingsTestBtn.textContent = "Probando...";
        settingsTestBtn.disabled = true;
        try {
            const payload = getFormData();
            const res = await api("POST", "/api/settings/test", payload);
            if (res.ok) {
                showAlert(res.message, "success");
            } else {
                showAlert(res.error || "Error desconocido al probar conexión", "error");
            }
        } catch (err) {
            showAlert(`Error de red: ${err.message}`, "error");
        } finally {
            settingsTestBtn.textContent = "Probar Conexión";
            settingsTestBtn.disabled = false;
        }
    });

    settingsForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        hideAlert();
        const saveBtn = document.getElementById("settings-save-btn");
        saveBtn.textContent = "Guardando...";
        saveBtn.disabled = true;
        try {
            const payload = getFormData();
            const res = await api("POST", "/api/settings", payload);
            if (res.ok) {
                toast("Configuración de IA guardada");
                settingsModal.hidden = true;
            } else {
                showAlert(res.error || "Error al guardar configuración", "error");
            }
        } catch (err) {
            showAlert(`Error de red: ${err.message}`, "error");
        } finally {
            saveBtn.textContent = "Guardar";
            saveBtn.disabled = false;
        }
    });

    // Article card interactions (delegated)
    document.getElementById("articles-grid").addEventListener("click", async (e) => {
        const card = e.target.closest(".article-card");
        if (!card) return;
        const id = parseInt(card.dataset.id);
        if (!id) return;

        if (e.target.closest(".btn-read")) {
            e.stopPropagation();
            e.preventDefault();
            await api("POST", `/api/articles/${id}/read`);
            card.classList.add("is-read");
            updateUnreadCount(-1);
        } else if (e.target.closest(".btn-star")) {
            e.stopPropagation();
            e.preventDefault();
            const res = await api("POST", `/api/articles/${id}/star`);
            card.classList.toggle("is-starred", res.starred);
        } else if (e.target.closest(".btn-summarize")) {
            e.stopPropagation();
            e.preventDefault();
            const btn = e.target.closest(".btn-summarize");
            const summaryContainer = card.querySelector(".ai-summary-container");

            if (!summaryContainer.hidden) {
                summaryContainer.hidden = true;
                return;
            }

            btn.classList.add("spinning");
            summaryContainer.innerHTML = "<small>Generando resumen...</small>";
            summaryContainer.hidden = false;

            try {
                const res = await api("POST", `/api/articles/${id}/summarize`);
                if (res.ok) {
                    // The summary from the backend can contain newlines -> convert to paragraphs
                    summaryContainer.innerHTML = escHtml(res.summary)
                        .split("\n")
                        .filter(l => l.trim())
                        .map(l => `<p>${l}</p>`)
                        .join("");
                } else {
                    summaryContainer.innerHTML = `<small class="error-text">Error: ${escHtml(res.error)}</small>`;
                }
            } catch (err) {
                summaryContainer.innerHTML = `<small class="error-text">Error de red</small>`;
            } finally {
                btn.classList.remove("spinning");
            }
        } else if (e.target.closest(".rating-star")) {
            e.stopPropagation();
            e.preventDefault();
            const star = e.target.closest(".rating-star");
            const rating = parseInt(star.dataset.rating);
            const currentRating = parseInt(card.dataset.rating || "0");
            const nextRating = currentRating === rating ? null : rating;
            try {
                const res = await api("POST", `/api/articles/${id}/rate`, { rating: nextRating });
                const newRating = res.rating ?? null;
                card.dataset.rating = newRating ?? "";
                renderRatingStars(card.querySelector(".rating-control"), newRating);
            } catch (err) {
                toast("No se pudo guardar la nota");
            }
        } else if (e.target.closest(".article-link")) {
            // Mark as read when clicking the title link
            await api("POST", `/api/articles/${id}/read`);
            card.classList.add("is-read");
            updateUnreadCount(-1);
        }
    });
}

// ── Data Loading ────────────────────────────────────────────────────────────
async function loadData() {
    const [articlesRes, statsRes] = await Promise.all([
        loadArticles(),
        api("GET", "/api/stats"),
    ]);
    state.stats = statsRes;
    renderFilters();
    renderStatusBar();
}

async function loadArticles() {
    const params = new URLSearchParams();
    if (state.activeCategory && state.activeCategory !== "starred") params.set("cat", state.activeCategory);
    if (state.query)            params.set("q", state.query);
    if (state.unreadOnly)       params.set("unread", "1");
    if (state.starredOnly || state.activeCategory === "starred") params.set("starred", "1");

    const res = await api("GET", `/api/articles?${params}`);
    state.articles = res.articles;
    state.lastRefresh = new Date();
    renderArticles();
}

// ── Rendering ─────────────────────────────────────────────────────────────
function renderArticles() {
    const grid = document.getElementById("articles-grid");
    const empty = document.getElementById("empty-state");

    if (state.articles.length === 0) {
        grid.innerHTML = "";
        empty.hidden = false;
        return;
    }
    empty.hidden = true;

    const query = state.query.toLowerCase();

    grid.innerHTML = state.articles.map(article => {
        const isRead = article.is_read ? "is-read" : "";
        const isStarred = article.is_starred ? "is-starred" : "";
        const imgHtml = article.image_url
            ? `<div class="card-image" style="background-image: ${safeCssImageUrl(article.image_url)}"></div>`
            : `<div class="card-image is-placeholder" data-id="${article.id}">
                 <div class="placeholder-icon">🖼️</div>
               </div>`;
        const titleHtml = query
            ? highlightMatches(escHtml(article.title), query)
            : escHtml(article.title);
        const categoriesHtml = Array.isArray(article.categories) && article.categories.length
            ? `<div class="card-tags">${article.categories.slice(0, 4).map(tag => `<span class="card-tag">${escHtml(tag)}</span>`).join("")}</div>`
            : "";
        const ratingHtml = `
            <div class="rating-control" data-rating="${article.user_rating ?? ""}">
                ${renderRatingStarsHtml(article.user_rating)}
            </div>
        `;

        return `
            <article class="article-card ${isRead} ${isStarred}"
                     data-id="${article.id}"
                     data-rating="${article.user_rating ?? ""}">
                ${imgHtml}
                <div class="card-content">
                    <div class="card-header">
                        <span class="card-emoji">${article.emoji}</span>
                        <span class="card-meta">
                            <span class="card-blog">${escHtml(article.blog_name)}</span>
                            <span class="card-date">${formatDate(article.published_date)}</span>
                        </span>
                        <div class="card-actions">
                            <button class="btn-icon btn-summarize" title="Resumir con IA">✨</button>
                            <button class="btn-icon btn-star ${article.is_starred ? "active" : ""}" title="Para leer">★</button>
                            <button class="btn-icon btn-read" title="Marcar leído">✕</button>
                        </div>
                    </div>
                    <a class="article-link" href="${escHtml(article.url)}" target="_blank" rel="noopener">
                        <h2 class="card-title">${titleHtml}</h2>
                    </a>
                    ${ratingHtml}
                    <div class="ai-summary-container" hidden></div>
                    ${categoriesHtml}
                </div>
            </article>
        `;
    }).join("");

    // Trigger on-demand fetching for placeholders
    document.querySelectorAll(".card-image.is-placeholder").forEach(el => {
        fetchImageOnDemand(parseInt(el.dataset.id), el);
    });
}

function renderRatingStarsHtml(rating) {
    const value = Number.isInteger(rating) ? rating : 0;
    let html = "";
    for (let i = 1; i <= 5; i++) {
        const active = i <= value ? "active" : "";
        html += `<button class="rating-star ${active}" data-rating="${i}" title="Nota ${i}/5" aria-label="Nota ${i} de 5">★</button>`;
    }
    return html;
}

function renderRatingStars(container, rating) {
    if (!container) return;
    container.dataset.rating = rating ?? "";
    container.innerHTML = renderRatingStarsHtml(rating);
}

async function fetchImageOnDemand(id, el) {
    try {
        const res = await api("GET", `/api/articles/${id}/image`);
        if (res.image_url) {
            const cssUrl = safeCssImageUrl(res.image_url);
            if (cssUrl) {
                el.style.backgroundImage = cssUrl;
                el.classList.remove("is-placeholder");
                el.innerHTML = ""; // Clear placeholder icon
            } else {
                // Leave placeholder but maybe change icon to indicate none found
                el.querySelector(".placeholder-icon").textContent = "🗞️";
            }
        }
    } catch (err) {
        console.error("Failed to fetch image on demand", err);
    }
}

function renderFilters() {
    document.querySelectorAll(".filter-pill").forEach(pill => {
        const cat = pill.dataset.cat || null;
        const isActive = cat === state.activeCategory;
        pill.classList.toggle("active", isActive);

        // Update count badge
        const count = cat ? (state.stats.by_category?.[cat] ?? 0) : state.stats.total ?? 0;
        const existingBadges = pill.querySelectorAll(".badge");
        existingBadges.forEach(b => b.remove());
        if (count > 0) {
            const badge = document.createElement("span");
            badge.className = "badge";
            badge.textContent = count;
            pill.appendChild(badge);
        }
    });
}

function renderStatusBar() {
    document.getElementById("unread-count").textContent =
        `${state.stats.total ?? 0} unread`;
    const lastScan = document.getElementById("last-scan");
    if (state.lastRefresh) {
        const t = state.lastRefresh.toLocaleTimeString("es-CL", { hour: "2-digit", minute: "2-digit" });
        lastScan.textContent = `Last scan: ${t}`;
    }
}

// ── Helpers ─────────────────────────────────────────────────────────────────
function setCategory(cat) {
    state.activeCategory = cat;
    renderFilters();
    loadArticles();
}

function updateUnreadCount(delta) {
    if (typeof state.stats.total !== "number") return;
    state.stats.total = Math.max(0, state.stats.total + delta);
    renderStatusBar();
    renderFilters();
}

function startAutoRefresh() {
    // Default 60 seconds from backend config if injected, else 60s
    const intervalSec = (() => {
        try {
            // If a server-rendered script exists with config, honour it; otherwise default 60
            return window.CDAILY_REFRESH_INTERVAL || 60;
        } catch (e) {
            return 60;
        }
    })();
    setInterval(async () => {
        await loadData();
    }, intervalSec * 1000);
}

function setRefreshIndicator(active) {
    const btn = document.getElementById("refresh-btn");
    btn.classList.toggle("spinning", active);
}

async function api(method, path, body = null) {
    const opts = { method, headers: {} };
    if (body) {
        opts.headers["Content-Type"] = "application/json";
        opts.body = JSON.stringify(body);
    }
    const res = await fetch(path, opts);
    if (!res.ok) {
        const text = await res.text().catch(() => "");
        throw new Error(`API ${method} ${path} → ${res.status}: ${text}`);
    }
    return res.json();
}

function toast(msg) {
    const container = document.getElementById("toast-container");
    const el = document.createElement("div");
    el.className = "toast";
    el.textContent = msg;
    container.appendChild(el);
    setTimeout(() => el.remove(), 4000);
}

function escHtml(str) {
    if (str == null) return "";
    const d = document.createElement("div");
    d.textContent = String(str);
    return d.innerHTML;
}

/**
 * Safely format a URL for use inside CSS url().
 * Only allows http/https URLs — rejects javascript:, data:, file:, etc.
 */
function safeCssImageUrl(url) {
    if (!url) return null;
    const str = String(url).trim();
    // Only http and https are safe for background-image
    if (!str.startsWith("http://") && !str.startsWith("https://")) return null;
    // Escape single quotes and parentheses for CSS safety
    return `url('${str.replace(/'/g, "%27").replace(/\(/g, "%28").replace(/\)/g, "%29")}')`;
}

function formatDate(iso) {
    if (!iso) return "";
    const d = new Date(iso);
    if (isNaN(d)) return iso;
    return d.toLocaleDateString("es-CL", { month: "short", day: "numeric" });
}

function truncate(text, maxLen) {
    if (!text || text.length <= maxLen) return text || "";
    return text.substring(0, maxLen).replace(/\s+\S*$/, "") + "…";
}

function highlightMatches(text, query) {
    if (!query) return text;
    const safeQuery = query.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const re = new RegExp(`(${safeQuery})`, "gi");
    return text.replace(re, "<mark>$1</mark>");
}
