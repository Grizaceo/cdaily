// ── State ─────────────────────────────────────────────────────────────────────
const state = {
    activeCategory: null,   // null = All
    query: "",
    unreadOnly: false,
    starredOnly: false,
    articles: [],
    stats: {},
    lastRefresh: null,
    // pagination
    limit: 50,
    offset: 0,
    hasMore: false,
    loadingMore: false,
    feedError: null,
    renderedCount: 0,
    // monotonically increasing token: each new load invalidates in-flight requests
    loadToken: 0,
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
    initInfiniteScroll();
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
    // Retry button (initial load error)
    document.getElementById("retry-btn").addEventListener("click", () => {
        state.feedError = null;
        loadData();
    });

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
        try {
            const result = await api("POST", "/api/scan");
            if (!result.ok) {
                throw new Error(result.error || result.stderr || "Error en scan");
            }
            await loadData();
            toast("Feed actualizado");
        } catch (error) {
            const message = error instanceof Error ? error.message : "Error en scan";
            toast(`Error en scan: ${message}`);
        } finally {
            setRefreshIndicator(false);
        }
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

    const presetSelect = document.getElementById("ai-preset");
    const presets = {
        openrouter: {
            endpoint: "https://openrouter.ai/api/v1/chat/completions",
            model: "google/gemini-2.5-flash",
            auth_type: "bearer"
        },
        openai: {
            endpoint: "https://api.openai.com/v1/chat/completions",
            model: "gpt-4o-mini",
            auth_type: "bearer"
        },
        deepseek: {
            endpoint: "https://api.deepseek.com/chat/completions",
            model: "deepseek-chat",
            auth_type: "bearer"
        },
        ollama: {
            endpoint: "http://localhost:11434/v1/chat/completions",
            model: "llama3",
            auth_type: "none"
        },
        "lm-studio": {
            endpoint: "http://localhost:12345/v1/chat/completions",
            model: "qwen2.5-7b-instruct-1m",
            auth_type: "none"
        }
    };

    presetSelect.addEventListener("change", () => {
        const val = presetSelect.value;
        if (presets[val]) {
            const p = presets[val];
            document.getElementById("ai-endpoint").value = p.endpoint;
            document.getElementById("ai-model").value = p.model;
            authTypeSelect.value = p.auth_type;
            updateAuthFieldsVisibility();
        }
    });

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
            document.getElementById("ai-preferred-language").value = config.preferred_language || "English";
            authTypeSelect.value = config.auth_type || "none";
            document.getElementById("ai-auth-header-name").value = config.auth_header_name || "";
            
            // Detect preset
            let detected = "custom";
            for (const [key, p] of Object.entries(presets)) {
                if (config.endpoint === p.endpoint && config.auth_type === p.auth_type) {
                    detected = key;
                    break;
                }
            }
            presetSelect.value = detected;

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
            preferred_language: document.getElementById("ai-preferred-language").value.trim() || "English",
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

    // ── Sources Modal Binding & Logic ─────────────────────────────────
    const sourcesBtn = document.getElementById("sources-btn");
    const sourcesModal = document.getElementById("sources-modal");
    const sourcesCloseBtn = document.getElementById("sources-close-btn");
    const sourcesForm = document.getElementById("sources-form");
    const sourcesListBody = document.getElementById("sources-list-body");
    const sourcesAlertContainer = document.getElementById("sources-alert-container");

    const showSourcesAlert = (message, type = "success") => {
        sourcesAlertContainer.textContent = message;
        sourcesAlertContainer.className = `settings-alert ${type}`;
        sourcesAlertContainer.hidden = false;
    };

    const hideSourcesAlert = () => {
        sourcesAlertContainer.hidden = true;
        sourcesAlertContainer.textContent = "";
    };

    const formatDate = (dateStr) => {
        if (!dateStr) return "Nunca";
        try {
            const date = new Date(dateStr);
            return date.toLocaleString("es-CL", {
                day: "2-digit",
                month: "2-digit",
                hour: "2-digit",
                minute: "2-digit"
            });
        } catch (e) {
            return dateStr;
        }
    };

    const loadAndRenderSources = async () => {
        sourcesListBody.innerHTML = `<tr><td colspan="4" style="text-align: center; color: var(--text-muted);">Cargando fuentes...</td></tr>`;
        try {
            const blogs = await api("GET", "/api/blogs");
            if (blogs.length === 0) {
                sourcesListBody.innerHTML = `<tr><td colspan="4" style="text-align: center; color: var(--text-muted);">No hay fuentes registradas.</td></tr>`;
                return;
            }

            sourcesListBody.innerHTML = blogs.map(blog => {
                const displayUrl = blog.feed_url || blog.url;
                const truncatedUrl = displayUrl.length > 40 ? displayUrl.substring(0, 37) + "..." : displayUrl;
                const lastScannedText = formatDate(blog.last_scanned);

                return `
                    <tr class="source-row">
                        <td class="source-cell-name"><strong>${escHtml(blog.name)}</strong></td>
                        <td class="source-cell-url"><a href="${escHtml(blog.url)}" target="_blank" title="${escHtml(displayUrl)}">${escHtml(truncatedUrl)}</a></td>
                        <td class="source-cell-date">${lastScannedText}</td>
                        <td class="source-cell-actions">
                            <button class="btn-icon btn-delete-source" data-id="${blog.id}" title="Eliminar Fuente">🗑️</button>
                        </td>
                    </tr>
                `;
            }).join("");
        } catch (err) {
            sourcesListBody.innerHTML = `<tr><td colspan="4" style="text-align: center; color: var(--accent-humor);">Error al cargar fuentes: ${err.message}</td></tr>`;
        }
    };

    sourcesBtn.addEventListener("click", () => {
        hideSourcesAlert();
        sourcesModal.hidden = false;
        loadAndRenderSources();
    });

    sourcesCloseBtn.addEventListener("click", () => {
        sourcesModal.hidden = true;
    });

    sourcesModal.addEventListener("click", (e) => {
        if (e.target === sourcesModal) {
            sourcesModal.hidden = true;
        }
    });

    sourcesForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        hideSourcesAlert();
        const addBtn = document.getElementById("source-add-btn");
        const originalText = addBtn.textContent;
        addBtn.textContent = "Añadiendo...";
        addBtn.disabled = true;
        try {
            const payload = {
                name: document.getElementById("source-name").value.trim(),
                url: document.getElementById("source-url").value.trim(),
                feed_url: document.getElementById("source-feed-url").value.trim() || null,
                scrape_selector: document.getElementById("source-selector").value.trim() || null
            };
            const res = await api("POST", "/api/blogs", payload);
            toast("Fuente agregada con éxito");
            sourcesForm.reset();
            await loadAndRenderSources();
        } catch (err) {
            showSourcesAlert(err.message || "Error al añadir la fuente", "error");
        } finally {
            addBtn.textContent = originalText;
            addBtn.disabled = false;
        }
    });

    sourcesListBody.addEventListener("click", async (e) => {
        const btn = e.target.closest(".btn-delete-source");
        if (!btn) return;
        const blogId = btn.dataset.id;
        if (!blogId) return;
        
        if (!confirm("¿Estás seguro de que deseas eliminar esta fuente de noticias?")) return;
        
        btn.disabled = true;
        btn.textContent = "⏳";
        try {
            await api("DELETE", `/api/blogs/${blogId}`);
            toast("Fuente eliminada con éxito");
            await loadAndRenderSources();
        } catch (err) {
            showSourcesAlert(err.message || "Error al eliminar la fuente", "error");
            btn.disabled = false;
            btn.textContent = "🗑️";
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
            try {
                await api("POST", `/api/articles/${id}/read`);
                card.classList.add("is-read");
                updateUnreadCount(-1);
            } catch (err) {
                toast("No se pudo marcar como leído");
            }
        } else if (e.target.closest(".btn-star")) {
            e.stopPropagation();
            e.preventDefault();
            try {
                const res = await api("POST", `/api/articles/${id}/star`);
                card.classList.toggle("is-starred", res.starred);
            } catch (err) {
                toast("No se pudo cambiar la estrella");
            }
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
        } else if (e.target.closest(".btn-translate")) {
            e.stopPropagation();
            e.preventDefault();
            const btn = e.target.closest(".btn-translate");
            const translationContainer = card.querySelector(".ai-translation-container");

            if (!translationContainer.hidden) {
                translationContainer.hidden = true;
                return;
            }

            btn.classList.add("spinning");
            translationContainer.innerHTML = "<small>Traduciendo...</small>";
            translationContainer.hidden = false;

            try {
                const res = await api("POST", `/api/articles/${id}/translate`);
                if (res.ok) {
                    translationContainer.innerHTML = escHtml(res.translation)
                        .split("\n")
                        .filter(l => l.trim())
                        .map(l => `<p>${l}</p>`)
                        .join("");
                } else {
                    translationContainer.innerHTML = `<small class="error-text">Error: ${escHtml(res.error)}</small>`;
                }
            } catch (err) {
                translationContainer.innerHTML = `<small class="error-text">Error de red</small>`;
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
            try {
                await api("POST", `/api/articles/${id}/read`);
                card.classList.add("is-read");
                updateUnreadCount(-1);
            } catch (err) {
                /* navigation proceeds regardless; only the optimistic state fails */
            }
        }
    });
}

// ── Infinite scroll (lazy pagination) ───────────────────────────────────────
function initInfiniteScroll() {
    const sentinel = document.getElementById("scroll-sentinel");
    if (!sentinel || !("IntersectionObserver" in window)) return;

    const io = new IntersectionObserver((entries) => {
        for (const entry of entries) {
            if (entry.isIntersecting && state.hasMore && !state.loadingMore) {
                loadArticles({ append: true });
            }
        }
    }, { rootMargin: "400px 0px" });
    io.observe(sentinel);
}

// ── Data Loading ────────────────────────────────────────────────────────────
async function loadData() {
    state.offset = 0;
    const [articlesRes, statsRes] = await Promise.all([
        loadArticles(),
        api("GET", "/api/stats"),
    ]);
    state.stats = statsRes;
    renderFilters();
    renderStatusBar();
}

async function loadArticles({ append = false } = {}) {
    const myToken = ++state.loadToken;
    if (!append) {
        state.offset = 0;
    }
    const params = new URLSearchParams();
    if (state.activeCategory && state.activeCategory !== "starred") params.set("cat", state.activeCategory);
    if (state.query)            params.set("q", state.query);
    if (state.unreadOnly)       params.set("unread", "1");
    if (state.starredOnly || state.activeCategory === "starred") params.set("starred", "1");
    params.set("limit", String(state.limit));
    params.set("offset", String(state.offset));

    if (append) {
        state.loadingMore = true;
        setLoadingMore(true);
    } else {
        setLoading(true);
    }

    try {
        const res = await api("GET", `/api/articles?${params}`);
        // Discard if a newer load (search / filter / refresh) superseded this one
        if (myToken !== state.loadToken) return;
        state.lastRefresh = new Date();
        state.feedError = null;
        const incoming = res.articles || [];
        if (append) {
            state.articles = state.articles.concat(incoming);
        } else {
            state.articles = incoming;
        }
        const fetched = res.count ?? incoming.length;
        state.offset += fetched;
        state.hasMore = fetched >= state.limit;
        renderArticles({ append });
    } catch (err) {
        // Discard stale errors so they don't clobber a newer load's UI state
        if (myToken !== state.loadToken) return;
        state.feedError = err.message || "Error al cargar artículos";
        showFeedError(state.feedError);
        if (!append) {
            state.articles = [];
            renderArticles({ append: false });
        }
    } finally {
        if (myToken === state.loadToken) {
            if (append) {
                state.loadingMore = false;
                setLoadingMore(false);
            } else {
                setLoading(false);
            }
        }
    }
}

// ── Rendering ─────────────────────────────────────────────────────────────
function renderArticles({ append = false } = {}) {
    const grid = document.getElementById("articles-grid");
    const empty = document.getElementById("empty-state");
    const loading = document.getElementById("loading-state");
    const loadingMoreEl = document.getElementById("loading-more");
    const errorEl = document.getElementById("error-state");

    if (!append) {
        grid.innerHTML = "";
        state.renderedCount = 0;
    }

    if (state.feedError && state.articles.length === 0) {
        empty.hidden = true;
        loading.hidden = true;
        errorEl.hidden = false;
        return;
    }
    errorEl.hidden = true;

    if (state.articles.length === 0) {
        empty.hidden = false;
        loading.hidden = true;
        return;
    }
    empty.hidden = true;

    const query = state.query.toLowerCase();

    let html;
    if (append) {
        const nextSlice = state.articles.slice(state.renderedCount);
        html = nextSlice.map(a => buildCardHtml(a, query)).join("");
        grid.insertAdjacentHTML("beforeend", html);
    } else {
        html = state.articles.map(a => buildCardHtml(a, query)).join("");
        grid.innerHTML = html;
    }
    state.renderedCount = state.articles.length;

    // Trigger on-demand fetching for placeholders
    document.querySelectorAll(".card-image.is-placeholder").forEach(el => {
        fetchImageOnDemand(parseInt(el.dataset.id), el);
    });

    // Toggle loading-more indicator
    loadingMoreEl.hidden = !state.hasMore && !state.loadingMore;
    loadingMoreEl.querySelector(".spinner-sm").hidden = !state.loadingMore;
    loadingMoreEl.querySelector(".loading-text").textContent =
        state.hasMore ? (state.loadingMore ? "Cargando más..." : "") : "";
}

function buildCardHtml(article, query) {
    const isRead = article.is_read ? "is-read" : "";
    const isStarred = article.is_starred ? "is-starred" : "";
    const cssUrl = safeCssImageUrl(article.image_url);
    const imgHtml = cssUrl
        ? `<div class="card-image" style="background-image: ${cssUrl}"></div>`
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
                    <span class="card-emoji" aria-hidden="true">${article.emoji}</span>
                    <span class="card-meta">
                        <span class="card-blog">${escHtml(article.blog_name)}</span>
                        <span class="card-date">${formatDate(article.published_date)}</span>
                    </span>
                    <div class="card-actions">
                        <button class="btn-icon btn-summarize" title="Resumir con IA" aria-label="Resumir con IA">✨</button>
                        <button class="btn-icon btn-translate" title="Traducir con IA" aria-label="Traducir con IA">🌐</button>
                        <button class="btn-icon btn-star ${article.is_starred ? "active" : ""}" title="Para leer" aria-label="Marcar para leer">★</button>
                        <button class="btn-icon btn-read" title="Marcar leído" aria-label="Marcar leído">✕</button>
                    </div>
                </div>
                <a class="article-link" href="${escHtml(article.url)}" target="_blank" rel="noopener">
                    <h2 class="card-title">${titleHtml}</h2>
                </a>
                ${ratingHtml}
                <div class="ai-summary-container" hidden></div>
                <div class="ai-translation-container" hidden></div>
                ${categoriesHtml}
            </div>
        </article>
    `;
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
        const cssUrl = res.image_url ? safeCssImageUrl(res.image_url) : null;
        if (cssUrl) {
            // Preload to detect broken images (og:image 404 / dead link)
            const probe = new Image();
            probe.onload = () => {
                el.style.backgroundImage = cssUrl;
                el.classList.remove("is-placeholder");
                el.innerHTML = "";
            };
            probe.onerror = () => showPlaceholderFallback(el);
            probe.src = res.image_url;
        } else {
            showPlaceholderFallback(el);
        }
    } catch (err) {
        console.error("Failed to fetch image on demand", err);
        showPlaceholderFallback(el);
    }
}

// Low-opacity static paper icon — no pulsing loop
function showPlaceholderFallback(el) {
    el.classList.remove("is-placeholder");
    el.innerHTML = `<div class="placeholder-icon" style="animation: none; opacity: 0.15;">🗞️</div>`;
}

// ── Loading / Error UI helpers ─────────────────────────────────────────────
function setLoading(active) {
    const el = document.getElementById("loading-state");
    if (el) el.hidden = !active;
}

function setLoadingMore(active) {
    const el = document.getElementById("loading-more");
    if (!el) return;
    el.hidden = !state.hasMore && !active;
    el.querySelector(".spinner-sm").hidden = !active;
    el.querySelector(".loading-text").textContent =
        state.hasMore ? (active ? "Cargando más..." : "") : "";
}

function showFeedError(message) {
    const el = document.getElementById("error-state");
    if (!el) return;
    el.hidden = false;
    const msg = el.querySelector(".error-message");
    if (msg) msg.textContent = message || "Error al cargar el feed";
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
