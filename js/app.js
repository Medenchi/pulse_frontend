(function () {
    "use strict";

    // ==================== SUPABASE ====================
    const SUPABASE_URL = "https://qsvztyhszwauwkxfmirs.supabase.co";
    const SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InFzdnp0eWhzendhdXdreGZtaXJzIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzU4MzY0NDQsImV4cCI6MjA5MTQxMjQ0NH0.JSGPwP0WWw02C4UWhLGcjlLH_1zoHgmv07hLGc045Ss";
    const { createClient } = window.supabase;
    const db = createClient(SUPABASE_URL, SUPABASE_KEY);

    // ==================== TELEGRAM ====================
    var tg = window.Telegram && window.Telegram.WebApp ? window.Telegram.WebApp : null;
    if (tg) {
        tg.ready();
        tg.expand();
        try { tg.disableVerticalSwipes(); } catch(e) {}
        try { tg.setHeaderColor("#050507"); } catch(e) {}
        try { tg.setBackgroundColor("#050507"); } catch(e) {}
    }

    // ==================== ADMINS ====================
    var ADMIN_IDS = [926176803, 7994155248];

    // ==================== STATE ====================
    var state = {
        current: "home",
        prev: null,
        services: [],
        builds: [],
        readyBuilds: [],
        portfolio: [],
        portfolioFilter: "all",
        orders: [],
        userId: 0,
        username: "",
        fullName: "",
        isAdmin: false,
        loaded: {
            services:     false,
            builds:       false,
            readyBuilds:  false,
            portfolio:    false
        },
        config: {
            bot_username:        "PulseComputersShop_bot",
            manager_deeplink:    "https://t.me/PulseComputersShop_bot?start=manager",
            admin_personal_link: "https://t.me/Pulse_Gadgets1",
            taplink_url:         "https://pulsegadgets.taplink.ws"
        },
        admin: {
            currentTab:  "a-dashboard",
            services:    [],
            builds:      [],
            readyBuilds: [],
            orders:      [],
            portfolio:   [],
            users:       []
        }
    };

    // Данные из Telegram
    if (tg && tg.initDataUnsafe && tg.initDataUnsafe.user) {
        var tgUser     = tg.initDataUnsafe.user;
        state.userId   = tgUser.id || 0;
        state.username = tgUser.username || "";
        state.fullName = (tgUser.first_name || "") + (tgUser.last_name ? " " + tgUser.last_name : "");
    }

    // Проверка админа
    if (state.userId && ADMIN_IDS.indexOf(Number(state.userId)) !== -1) {
        state.isAdmin = true;
    }

    // ==================== CONSTANTS ====================
    var TABS = ["home", "services", "builds", "ready-builds", "portfolio", "more", "admin"];

    var CATEGORY_LABELS = {
        build:   "Сборка",
        repair:  "Ремонт",
        upgrade: "Апгрейд",
        custom:  "Кастом",
        general: "Другое"
    };

    var STATUS_MAP = {
        processing:    "В обработке",
        delivery:      "Доставка",
        diagnostics:   "Диагностика",
        in_progress:   "В работе",
        ready:         "Готов к выдаче",
        delayed:       "Задерживается",
        waiting_parts: "Ожидание запчастей",
        completed:     "Завершен",
        cancelled:     "Отменен"
    };

    var TYPE_MAP = {
        repair:       "Ремонт",
        build:        "Сборка ПК",
        buyout:       "Скупка",
        custom_build: "Кастом сборка",
        service:      "Услуга",
        ready_build:  "Готовая сборка"
    };

    // ==================== DOM ====================
    function $(s)  { return document.querySelector(s); }
    function $$(s) { return document.querySelectorAll(s); }

    function esc(s) {
        if (s === null || s === undefined) return "";
        var d = document.createElement("div");
        d.textContent = String(s);
        return d.innerHTML;
    }

    function fmt(n) {
        if (!n && n !== 0) return "0";
        return Math.round(n).toString().replace(/\B(?=(\d{3})+(?!\d))/g, "\u00a0");
    }

    function fmtDate(iso) {
        if (!iso) return "";
        try {
            var d = new Date(iso);
            return d.toLocaleString("ru-RU", {
                day: "2-digit", month: "2-digit", year: "numeric",
                hour: "2-digit", minute: "2-digit"
            });
        } catch(e) { return iso.slice(0, 10); }
    }

    function clamp(str, max) {
        if (!str) return "";
        return str.length > max ? str.slice(0, max) + "…" : str;
    }

    // ==================== UI ====================
    var _toastTimer = null;
    function toast(msg, type) {
        var old = $(".toast");
        if (old) old.remove();
        if (_toastTimer) clearTimeout(_toastTimer);
        var icons = { success: "ph-check-circle", error: "ph-x-circle", warning: "ph-warning" };
        var el = document.createElement("div");
        el.className = "toast toast-" + (type || "success");
        el.innerHTML = '<i class="ph-bold ' + (icons[type] || icons.success) + '"></i><span>' + esc(msg) + '</span>';
        document.body.appendChild(el);
        requestAnimationFrame(function() { el.classList.add("toast-show"); });
        _toastTimer = setTimeout(function() {
            el.classList.remove("toast-show");
            setTimeout(function() { if (el.parentNode) el.remove(); }, 300);
        }, 3000);
    }

    function openModal(title, html) {
        $("#modalTitle").textContent = title;
        $("#modalBody").innerHTML = html;
        $("#modalOverlay").classList.remove("hidden");
        document.body.style.overflow = "hidden";
    }

    function closeModal() {
        $("#modalOverlay").classList.add("hidden");
        document.body.style.overflow = "";
        setTimeout(function() {
            var mb = $("#modalBody");
            if (mb) mb.innerHTML = "";
        }, 200);
    }

    function openViewer(item) {
        var img  = $("#viewerImage");
        var info = $("#viewerInfo");
        if (typeof item === "string") {
            img.src = item;
            info.classList.add("hidden");
        } else {
            img.src = item.url || "";
            $("#viewerTitle").textContent       = item.title || "";
            $("#viewerDescription").textContent = item.description || "";
            $("#viewerCategory").textContent    = CATEGORY_LABELS[item.category] || item.category || "";
            if (item.title || item.description) info.classList.remove("hidden");
            else info.classList.add("hidden");
        }
        $("#imageViewer").classList.remove("hidden");
        document.body.style.overflow = "hidden";
    }

    function closeViewer() {
        $("#imageViewer").classList.add("hidden");
        setTimeout(function() { $("#viewerImage").src = ""; }, 200);
        $("#viewerInfo").classList.add("hidden");
        document.body.style.overflow = "";
    }

    function setLoading(el, gridSpan) {
        if (typeof el === "string") el = $(el);
        if (!el) return;
        el.innerHTML = '<div class="loading-spinner"' + (gridSpan ? ' style="grid-column:1/-1"' : '') + '></div>';
    }

    function setEmpty(el, icon, text, sub) {
        if (typeof el === "string") el = $(el);
        if (!el) return;
        el.innerHTML =
            '<div class="portfolio-empty">' +
            '<i class="' + icon + '"></i>' +
            '<p>' + esc(text) + '</p>' +
            (sub ? '<span style="font-size:0.75rem;color:var(--w30);margin-top:4px;display:block;">' + esc(sub) + '</span>' : '') +
            '</div>';
    }

    function setBtnLoading(btn, loading) {
        if (!btn) return;
        if (loading) {
            btn.disabled = true;
            btn.dataset.orig = btn.innerHTML;
            btn.innerHTML = '<div class="loading-spinner" style="width:18px;height:18px;margin:0 auto;padding:0;"></div>';
        } else {
            btn.disabled = false;
            btn.innerHTML = btn.dataset.orig || "Отправить";
        }
    }

    function statusBadge(status) {
        return '<span class="o-status s-' + status + '">' + esc(STATUS_MAP[status] || status) + '</span>';
    }

    // ==================== CONFIG ====================
    function loadConfig() {
        if (state.isAdmin) {
            var btn = $("#adminNavBtn");
            if (btn) btn.classList.remove("hidden");
        }
        updateDynamicLinks();
    }

    function updateDynamicLinks() {
        $$("[data-manager-link]").forEach(function(el) { el.href = state.config.manager_deeplink || "#"; });
        $$("[data-admin-link]").forEach(function(el)   { el.href = state.config.admin_personal_link || "#"; });
        $$("[data-taplink]").forEach(function(el)      { el.href = state.config.taplink_url || "#"; });
    }

    // ==================== SPLASH ====================
    function initSplash() {
        var logo = $("#splashLogo");
        if (!logo) return;
        logo.onerror = function() {
            var s = $("#splashScreen"); if (s) s.classList.add("hidden");
            var a = $("#app"); if (a) a.classList.remove("hidden");
        };
        logo.onload = function() {
            setTimeout(function() {
                var s = $("#splashScreen");
                if (!s) return;
                s.style.transition = "opacity 0.4s ease";
                s.style.opacity    = "0";
                setTimeout(function() {
                    s.classList.add("hidden");
                    var a = $("#app"); if (a) a.classList.remove("hidden");
                }, 400);
            }, 1400);
        };
        if (logo.complete && logo.naturalWidth > 0) logo.onload();
    }

    // ==================== NAVIGATION ====================
    function nav(id) {
        if (id === state.current) return;
        if (id === "admin" && !state.isAdmin) { toast("Нет доступа", "error"); return; }
        state.prev = state.current;
        $$(".section").forEach(function(s) { s.classList.remove("active"); });
        var target = $("#section-" + id);
        if (!target) return;
        target.classList.add("active");
        if (TABS.indexOf(id) !== -1) {
            $$(".nav-btn").forEach(function(b) { b.classList.remove("active"); });
            var nb = $('[data-section="' + id + '"]');
            if (nb) nb.classList.add("active");
        }
        state.current = id;
        window.scrollTo({ top: 0, behavior: "instant" });

        if (id === "services"     && !state.loaded.services)    loadServices();
        if (id === "builds"       && !state.loaded.builds)      loadBuilds();
        if (id === "ready-builds" && !state.loaded.readyBuilds) loadReadyBuilds();
        if (id === "portfolio"    && !state.loaded.portfolio)   loadPortfolio();
        if (id === "orders")  loadOrders();
        if (id === "admin")   adminLoadTab(state.admin.currentTab);

        updateBackButton();
    }

    function updateBackButton() {
        if (!tg || !tg.BackButton) return;
        if (state.current === "home") tg.BackButton.hide();
        else tg.BackButton.show();
    }

    function getBackTarget() {
        var map = {
            "service-form":  "services",
            "build-form":    "builds",
            "ready-builds":  "more",
            "buyout":        "more",
            "products":      "more",
            "delivery":      "more",
            "orders":        "more",
            "contacts":      "more",
            "admin":         "home"
        };
        return map[state.current] || "home";
    }

    function initNavigation() {
        $$(".nav-btn").forEach(function(btn) {
            btn.addEventListener("click", function() {
                var s = this.getAttribute("data-section");
                if (s) nav(s);
            });
        });
        document.addEventListener("click", function(e) {
            var el = e.target.closest("[data-navigate]");
            if (el) { e.preventDefault(); nav(el.getAttribute("data-navigate")); }
        });
    }

    // ==================== SUPABASE HELPERS ====================
    async function sbSelect(table, opts) {
        opts = opts || {};
        if (opts.count) {
            var r = await db.from(table).select("*", { count: "exact", head: true });
            if (r.error) throw r.error;
            return r.count || 0;
        }
        var q = db.from(table).select(opts.select || "*");
        if (opts.eq)    q = q.eq(opts.eq[0], opts.eq[1]);
        if (opts.order) q = q.order(opts.order, { ascending: !!opts.asc });
        if (opts.limit) q = q.limit(opts.limit);
        var result = await q;
        if (result.error) throw result.error;
        return result.data || [];
    }

    async function sbInsert(table, payload) {
        var r = await db.from(table).insert([payload]).select();
        if (r.error) throw r.error;
        return r.data[0];
    }

    async function sbUpdate(table, payload, col, val) {
        var r = await db.from(table).update(payload).eq(col, val).select();
        if (r.error) throw r.error;
        return r.data ? r.data[0] : null;
    }

    async function sbDelete(table, col, val) {
        var r = await db.from(table).delete().eq(col, val);
        if (r.error) throw r.error;
        return true;
    }

    function portfolioUrl(filename) {
        if (!filename) return "";
        if (filename.startsWith("http")) return filename;
        return SUPABASE_URL + "/storage/v1/object/public/portfolio/" + filename;
    }

    // ==================== STORAGE UPLOAD ====================
    async function uploadToStorage(bucket, file, folder) {
        folder = folder || "";
        var ext      = file.name.split('.').pop();
        var filename = (folder ? folder + "/" : "") + Date.now() + "_" + Math.random().toString(36).slice(2, 8) + "." + ext;
        var result   = await db.storage.from(bucket).upload(filename, file, { upsert: false });
        if (result.error) throw result.error;
        var pub = db.storage.from(bucket).getPublicUrl(filename);
        return pub.data.publicUrl;
    }

    // ==================== ORDERS ====================
    async function submitOrder(type, pay, details, price, contact, delivery) {
        if (!state.userId) { toast("Откройте через Telegram", "error"); return null; }
        try {
            var row = await sbInsert("orders", {
                user_id:       state.userId,
                order_type:    type,
                payment_type:  pay,
                details:       details || "",
                total_price:   price || 0,
                contact_info:  contact || "",
                delivery_info: delivery || "",
                status:        "processing",
                created_at:    new Date().toISOString(),
                updated_at:    new Date().toISOString()
            });
            toast("Заявка #" + row.id + " создана!", "success");
            return row;
        } catch(e) {
            console.error("submitOrder:", e);
            toast("Ошибка отправки", "error");
            return null;
        }
    }

    // ==================== SERVICES ====================
    async function loadServices() {
        var el = $("#servicesList");
        setLoading(el);
        try {
            state.services = await sbSelect("services", { order: "id", asc: true });
            state.loaded.services = true;
            renderServices();
        } catch(e) {
            console.error(e);
            setEmpty(el, "ph-light ph-warning-circle", "Не удалось загрузить услуги", "Попробуйте позже");
        }
    }

    function renderServices() {
        var el   = $("#servicesList");
        var list = state.services;
        if (!list.length) { setEmpty(el, "ph-light ph-wrench", "Услуги скоро появятся"); return; }
        var html = "";
        list.forEach(function(s, i) {
            html +=
                '<div class="svc-card" data-si="' + i + '">' +
                '<div class="svc-icon"><i class="' + esc(s.icon || "ph-bold ph-wrench") + '"></i></div>' +
                '<div class="svc-body">' +
                '<h3>' + esc(s.title) + '</h3>' +
                '<p class="svc-desc">' + esc(clamp(s.description, 70)) + '</p>' +
                '<div class="svc-footer">' +
                '<span class="svc-price">' + esc(s.price_text) + '</span>' +
                '<span class="svc-pay-badge ' + (s.payment === "prepay" ? "prepay" : "postpay") + '">' +
                (s.payment === "prepay" ? "Предоплата" : "По факту") +
                '</span>' +
                '</div></div>' +
                '<i class="ph-bold ph-caret-right svc-arrow"></i>' +
                '</div>';
        });
        el.innerHTML = html;
        $$(".svc-card").forEach(function(card) {
            card.addEventListener("click", function() {
                var idx = parseInt(this.getAttribute("data-si"), 10);
                if (state.services[idx]) openServiceForm(state.services[idx]);
            });
        });
    }

    // ==================== SERVICE FORM ====================
    function openServiceForm(service) {
        var container = $("#serviceFormContainer");
        var titleEl   = $("#serviceFormServiceName");
        if (titleEl) titleEl.textContent = service.title + " — " + service.price_text;

        var fields = [];
        if (service.form_fields) {
            if (typeof service.form_fields === "string") {
                try { fields = JSON.parse(service.form_fields); } catch(e) { fields = []; }
            } else {
                fields = service.form_fields;
            }
        }

        var html =
            '<input type="hidden" id="svcFormServiceId"    value="' + service.id + '">' +
            '<input type="hidden" id="svcFormServiceTitle" value="' + esc(service.title) + '">' +
            '<input type="hidden" id="svcFormServicePrice" value="' + (service.price_from || 0) + '">' +
            '<input type="hidden" id="svcFormPayment"      value="' + esc(service.payment || "postpay") + '">';

        fields.forEach(function(f) {
            html += '<div class="form-group"><label>' + esc(f.label) + (f.required ? ' <span class="req">*</span>' : '') + '</label>';
            if (f.type === "textarea") {
                html += '<textarea class="svc-field" data-field-id="' + esc(f.id) + '" rows="3" placeholder="' + esc(f.placeholder || "") + '"' + (f.required ? " required" : "") + '></textarea>';
            } else if (f.type === "select") {
                html += '<select class="svc-field" data-field-id="' + esc(f.id) + '"' + (f.required ? " required" : "") + '><option value="">— Выберите —</option>';
                (f.options || []).forEach(function(o) { html += '<option value="' + esc(o) + '">' + esc(o) + '</option>'; });
                html += '</select>';
            } else {
                html += '<input type="' + (f.type || "text") + '" class="svc-field" data-field-id="' + esc(f.id) + '" placeholder="' + esc(f.placeholder || "") + '"' + (f.required ? " required" : "") + '>';
            }
            html += '</div>';
        });

        html += '<button type="submit" class="btn btn-primary btn-block" style="margin-top:8px;"><i class="ph-bold ph-paper-plane-tilt"></i> Отправить заявку</button>';
        container.innerHTML = html;
        nav("service-form");
    }

    function initServiceForm() {
        var form = $("#serviceForm");
        if (!form) return;
        form.addEventListener("submit", async function(e) {
            e.preventDefault();
            var title   = ($("#svcFormServiceTitle") || {}).value || "";
            var price   = parseFloat(($("#svcFormServicePrice") || {}).value) || 0;
            var payment = ($("#svcFormPayment") || {}).value || "postpay";
            var fieldEls = form.querySelectorAll(".svc-field");
            var details  = "Услуга: " + title + "\n";
            var contact  = "";
            var allOk    = true;

            fieldEls.forEach(function(fel) {
                var fid = fel.getAttribute("data-field-id");
                var val = fel.value.trim();
                if (fel.required && !val) { allOk = false; fel.classList.add("input-error"); }
                else fel.classList.remove("input-error");
                if (fid === "contact") contact = val;
                if (val) {
                    var lbl  = fid;
                    var prev = fel.previousElementSibling;
                    if (prev && prev.tagName === "LABEL") lbl = prev.textContent.replace("*", "").trim();
                    details += lbl + ": " + val + "\n";
                }
            });

            if (!allOk) { toast("Заполните все обязательные поля", "error"); return; }
            var btn = form.querySelector('button[type="submit"]');
            setBtnLoading(btn, true);
            var result = await submitOrder("service", payment, details.trim(), price, contact);
            setBtnLoading(btn, false);
            if (result) { $("#serviceFormContainer").innerHTML = ""; nav("services"); }
        });
    }

    // ==================== BUILDS (конфигуратор) ====================
    async function loadBuilds() {
        var el = $("#buildsList");
        setLoading(el);
        try {
            state.builds = await sbSelect("builds", { order: "price", asc: true });
            state.loaded.builds = true;
            renderBuilds();
        } catch(e) {
            console.error(e);
            setEmpty(el, "ph-light ph-warning-circle", "Не удалось загрузить сборки");
        }
    }

    function renderBuilds() {
        var el   = $("#buildsList");
        var list = state.builds;
        if (!list.length) { setEmpty(el, "ph-light ph-desktop-tower", "Сборки скоро появятся"); return; }
        var html = "";
        list.forEach(function(b, i) {
            html +=
                '<div class="build-card" data-bi="' + i + '">' +
                '<div class="build-top">' +
                '<span class="build-name">' + esc(b.name) + '</span>' +
                '<span class="build-tag">'  + esc(b.tier) + '</span>' +
                '</div>' +
                '<div class="build-desc">'  + esc(b.description) + '</div>' +
                '<div class="build-bottom">' +
                '<span class="build-price">' + esc(b.price_text) + '</span>' +
                '<button class="btn btn-primary btn-small bo-btn" data-bi="' + i + '">Заказать</button>' +
                '</div></div>';
        });
        el.innerHTML = html;
        $$(".build-card").forEach(function(card) {
            card.addEventListener("click", function(e) {
                if (e.target.closest(".bo-btn")) return;
                var idx = parseInt(this.getAttribute("data-bi"), 10);
                if (state.builds[idx]) openBuildDetail(state.builds[idx]);
            });
        });
        $$(".bo-btn").forEach(function(btn) {
            btn.addEventListener("click", function(e) {
                e.stopPropagation();
                var idx = parseInt(this.getAttribute("data-bi"), 10);
                if (state.builds[idx]) openBuildForm(state.builds[idx]);
            });
        });
    }

    function openBuildDetail(build) {
        var ml   = state.config.manager_deeplink || "#";
        var html =
            '<p style="color:var(--w40);font-size:0.84rem;margin-bottom:16px;line-height:1.55;">' + esc(build.description) + '</p>' +
            '<div style="text-align:center;padding:18px;background:var(--surface3);border-radius:var(--r);margin-bottom:16px;border:1px solid var(--border);">' +
            '<div style="font-family:var(--mono);font-size:1.35rem;font-weight:800;color:var(--w95);">' + esc(build.price_text) + '</div>' +
            '<div style="font-size:0.72rem;color:var(--w40);margin-top:4px;">Сборка + комплектующие</div>' +
            '</div>' +
            '<div style="display:flex;flex-direction:column;gap:8px;">' +
            '<button class="btn btn-primary btn-block" id="mdlOrderBuild"><i class="ph-bold ph-shopping-cart-simple"></i> Заказать сборку</button>' +
            '<a href="' + esc(ml) + '" class="btn btn-ghost btn-block" target="_blank"><i class="ph-bold ph-chat-circle-dots"></i> Рассрочка / Доли</a>' +
            '</div>';
        openModal(build.name, html);
        setTimeout(function() {
            var btn = $("#mdlOrderBuild");
            if (btn) btn.addEventListener("click", function() { closeModal(); openBuildForm(build); });
        }, 60);
    }

    function openBuildForm(build) {
        var form = $("#buildForm");
        if (form) form.reset();
        $("#buildTypeId").value    = build.id;
        $("#buildTypeName").value  = build.name;
        $("#buildTypePrice").value = build.price;
        $("#buildFormTypeName").textContent = build.name + " — " + build.price_text;
        $("#buildBudget").value    = build.price;
        var cdek = $("#cdekFields");
        if (cdek) cdek.classList.add("hidden");
        removeCdekRequired();
        nav("build-form");
    }

    function openCustomBuildForm() {
        var form = $("#buildForm");
        if (form) form.reset();
        $("#buildTypeId").value    = "0";
        $("#buildTypeName").value  = "Индивидуальная сборка";
        $("#buildTypePrice").value = "0";
        $("#buildFormTypeName").textContent = "Индивидуальная сборка";
        $("#buildBudget").value    = "";
        var cdek = $("#cdekFields");
        if (cdek) cdek.classList.add("hidden");
        removeCdekRequired();
        nav("build-form");
    }

    function addCdekRequired() {
        ["#buildDeliveryFio", "#buildDeliveryAddress", "#buildDeliveryPhone"].forEach(function(s) {
            var el = $(s); if (el) el.required = true;
        });
    }
    function removeCdekRequired() {
        ["#buildDeliveryFio", "#buildDeliveryAddress", "#buildDeliveryPhone"].forEach(function(s) {
            var el = $(s); if (el) el.required = false;
        });
    }

    function initBuildForm() {
        var form           = $("#buildForm");
        if (!form) return;
        var deliverySelect = $("#buildDeliveryType");
        var cdek           = $("#cdekFields");
        if (deliverySelect) {
            deliverySelect.addEventListener("change", function() {
                if (this.value === "СДЭК") { cdek.classList.remove("hidden"); addCdekRequired(); }
                else { cdek.classList.add("hidden"); removeCdekRequired(); }
            });
        }
        form.addEventListener("submit", async function(e) {
            e.preventDefault();
            var typeName     = ($("#buildTypeName")     || {}).value || "";
            var contact      = ($("#buildContact")      || {}).value.trim();
            var budget       = parseInt(($("#buildBudget") || {}).value, 10) || 0;
            var tasks        = ($("#buildTasks")        || {}).value || "";
            var color        = ($("#buildColor")        || {}).value.trim();
            var rgb          = ($("#buildRGB")          || {}).value || "";
            var vinyl        = ($("#buildVinyl")        || {}).value || "";
            var deliveryType = ($("#buildDeliveryType") || {}).value || "";
            var notes        = ($("#buildNotes")        || {}).value.trim();
            if (!contact || !budget || !tasks) { toast("Заполните обязательные поля", "error"); return; }
            var details =
                "Тип: "         + typeName +
                "\nБюджет: "    + fmt(budget) + " руб." +
                "\nЗадача: "    + tasks +
                "\nЦвет: "      + (color || "не указан") +
                "\nПодсветка: " + rgb +
                "\nКастом: "    + vinyl +
                "\nДоставка: "  + deliveryType;
            if (notes) details += "\nПожелания: " + notes;
            var deliveryInfo = "";
            if (deliveryType === "СДЭК") {
                var fio   = ($("#buildDeliveryFio")     || {}).value.trim();
                var addr  = ($("#buildDeliveryAddress") || {}).value.trim();
                var phone = ($("#buildDeliveryPhone")   || {}).value.trim();
                if (!fio || !addr || !phone) { toast("Заполните данные доставки", "error"); return; }
                deliveryInfo = "СДЭК\nФИО: " + fio + "\nАдрес: " + addr + "\nТелефон: " + phone;
            }
            var btn = form.querySelector('button[type="submit"]');
            setBtnLoading(btn, true);
            var result = await submitOrder("build", "prepay", details, budget, contact, deliveryInfo);
            setBtnLoading(btn, false);
            if (result) {
                form.reset();
                if (cdek) cdek.classList.add("hidden");
                removeCdekRequired();
                nav("builds");
            }
        });
        var customBtn = $("#openCustomBuildForm");
        if (customBtn) customBtn.addEventListener("click", openCustomBuildForm);
    }

    // ==================== BUILDS SWITCHER ====================
    function initBuildsSwitcher() {
        var btnConf  = $("#switchConfigurator");
        var btnReady = $("#switchReady");
        var secConf  = $("#configuratorSection");
        var secReady = $("#readySection");
        if (!btnConf || !btnReady) return;

        btnConf.addEventListener("click", function() {
            btnConf.classList.add("active");
            btnReady.classList.remove("active");
            secConf.classList.remove("hidden");
            secReady.classList.add("hidden");
        });

        btnReady.addEventListener("click", function() {
            btnReady.classList.add("active");
            btnConf.classList.remove("active");
            secReady.classList.remove("hidden");
            secConf.classList.add("hidden");
            if (!state.loaded.readyBuilds) loadReadyBuilds();
            else renderReadyBuilds();
        });
    }

    // ==================== READY BUILDS ====================
    async function loadReadyBuilds() {
        var els = ["#readyBuildsList", "#readyBuildsListFull"];
        els.forEach(function(s) { var e = $(s); if (e) setLoading(e); });
        try {
            state.readyBuilds = await sbSelect("ready_builds", { order: "created_at", asc: false });
            state.loaded.readyBuilds = true;
            renderReadyBuilds();
        } catch(e) {
            console.error(e);
            els.forEach(function(s) {
                var el = $(s);
                if (el) setEmpty(el, "ph-light ph-warning-circle", "Не удалось загрузить готовые сборки");
            });
        }
    }

    function renderReadyBuilds() {
        var list    = state.readyBuilds;
        var targets = ["#readyBuildsList", "#readyBuildsListFull"];

        targets.forEach(function(sel) {
            var el = $(sel);
            if (!el) return;
            if (!list.length) {
                setEmpty(el, "ph-light ph-package", "Готовых сборок пока нет", "Загляните позже");
                return;
            }
            var html = "";
            list.forEach(function(b, i) {
                var statusLabel = b.status === "available" ? "В наличии" : b.status === "reserved" ? "Забронировано" : "Продано";
                var statusClass = b.status === "available" ? "rb-status-available" : b.status === "reserved" ? "rb-status-reserved" : "rb-status-sold";
                html +=
                    '<div class="rb-card" data-rbi="' + i + '">' +
                    // ✅ ОБНОВЛЕНО: фото с плейсхолдером
                    (b.image_url
                        ? '<div class="rb-img-wrap"><img src="' + esc(b.image_url) + '" alt="' + esc(b.name) + '" loading="lazy"></div>'
                        : '<div class="rb-img-placeholder"><i class="ph-light ph-image-broken"></i><span>Фото скоро появится — мы работаем над этим 📸</span></div>'
                    ) +
                    '<div class="rb-body">' +
                    '<div class="rb-top">' +
                    '<span class="rb-name">' + esc(b.name) + '</span>' +
                    '<span class="rb-badge ' + statusClass + '">' + statusLabel + '</span>' +
                    '</div>' +
                    (b.specs ? '<p class="rb-specs">' + esc(clamp(b.specs, 120)) + '</p>' : '') +
                    '<div class="rb-bottom">' +
                    '<span class="rb-price">' + (b.price ? fmt(b.price) + '\u00a0руб.' : 'По запросу') + '</span>' +
                    (b.status === "available" ?
                        '<button class="btn btn-primary btn-small rb-order-btn" data-rbi="' + i + '">Купить</button>' :
                        '<button class="btn btn-ghost btn-small" disabled>' + statusLabel + '</button>'
                    ) +
                    '</div></div></div>';
            });
            el.innerHTML = html;

            el.querySelectorAll(".rb-card").forEach(function(card) {
                card.addEventListener("click", function(e) {
                    if (e.target.closest(".rb-order-btn")) return;
                    var idx = parseInt(this.getAttribute("data-rbi"), 10);
                    if (state.readyBuilds[idx]) openReadyBuildDetail(state.readyBuilds[idx]);
                });
            });
            el.querySelectorAll(".rb-order-btn").forEach(function(btn) {
                btn.addEventListener("click", function(e) {
                    e.stopPropagation();
                    var idx = parseInt(this.getAttribute("data-rbi"), 10);
                    if (state.readyBuilds[idx]) openReadyBuildOrder(state.readyBuilds[idx]);
                });
            });
        });
    }

    function openReadyBuildDetail(build) {
        var statusLabel = build.status === "available" ? "В наличии" : build.status === "reserved" ? "Забронировано" : "Продано";
        var statusClass = build.status === "available" ? "rb-status-available" : "rb-status-sold";
        var html = "";
        if (build.image_url) {
            html += '<img src="' + esc(build.image_url) + '" style="width:100%;border-radius:var(--r);margin-bottom:14px;object-fit:cover;max-height:220px;" loading="lazy">';
        }
        html +=
            '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;">' +
            '<span class="rb-badge ' + statusClass + '">' + statusLabel + '</span>' +
            '<span style="font-family:var(--mono);font-size:1.1rem;font-weight:800;color:var(--w95);">' +
            (build.price ? fmt(build.price) + '\u00a0руб.' : 'По запросу') + '</span>' +
            '</div>';
        if (build.specs) {
            html +=
                '<div style="background:var(--surface3);border-radius:var(--r);padding:13px;border:1px solid var(--border);margin-bottom:14px;">' +
                '<div style="font-size:0.7rem;color:var(--w40);margin-bottom:6px;font-weight:600;text-transform:uppercase;letter-spacing:0.05em;">Комплектация</div>' +
                '<div style="font-size:0.78rem;white-space:pre-wrap;color:var(--w60);line-height:1.6;">' + esc(build.specs) + '</div>' +
                '</div>';
        }
        if (build.description) {
            html += '<p style="font-size:0.8rem;color:var(--w40);line-height:1.55;margin-bottom:14px;">' + esc(build.description) + '</p>';
        }
        if (build.status === "available") {
            html += '<button class="btn btn-primary btn-block" id="mdlBuyReady"><i class="ph-bold ph-shopping-cart-simple"></i> Купить сборку</button>';
        }
        openModal(build.name, html);
        setTimeout(function() {
            var btn = $("#mdlBuyReady");
            if (btn) btn.addEventListener("click", function() { closeModal(); openReadyBuildOrder(build); });
        }, 60);
    }

    function openReadyBuildOrder(build) {
        var html =
            '<div style="background:var(--surface3);border-radius:var(--r);padding:12px;margin-bottom:16px;border:1px solid var(--border);">' +
            '<div style="font-size:0.78rem;font-weight:700;color:var(--w80);">' + esc(build.name) + '</div>' +
            '<div style="font-family:var(--mono);font-size:1rem;font-weight:800;color:var(--accent-soft);margin-top:4px;">' +
            (build.price ? fmt(build.price) + '\u00a0руб.' : 'По запросу') + '</div>' +
            '</div>' +
            '<div class="form-group"><label>Контакт для связи <span class="req">*</span></label>' +
            '<input type="text" id="rbContact" placeholder="Телефон или @telegram"></div>' +
            '<div class="form-group"><label>Доставка</label>' +
            '<select id="rbDelivery">' +
            '<option value="Самовывоз">Самовывоз (Краснодар)</option>' +
            '<option value="СДЭК">СДЭК по России</option>' +
            '</select></div>' +
            '<div class="form-group"><label>Пожелания</label>' +
            '<textarea id="rbNotes" rows="2" placeholder="Доп. вопросы..."></textarea></div>' +
            '<button class="btn btn-primary btn-block" id="rbSubmitBtn" style="margin-top:8px;">' +
            '<i class="ph-bold ph-paper-plane-tilt"></i> Оформить заказ</button>';
        openModal("Купить: " + build.name, html);
        setTimeout(function() {
            var btn = $("#rbSubmitBtn");
            if (!btn) return;
            btn.addEventListener("click", async function() {
                var contact  = ($("#rbContact")  || {}).value.trim();
                var delivery = ($("#rbDelivery") || {}).value || "";
                var notes    = ($("#rbNotes")    || {}).value.trim();
                if (!contact) { toast("Укажите контакт", "error"); return; }
                var details =
                    "Готовая сборка: " + build.name +
                    "\nЦена: " + (build.price ? fmt(build.price) + " руб." : "По запросу") +
                    "\nДоставка: " + delivery +
                    (notes ? "\nПожелания: " + notes : "");
                setBtnLoading(btn, true);
                var result = await submitOrder("ready_build", "prepay", details, build.price || 0, contact, delivery);
                setBtnLoading(btn, false);
                if (result) closeModal();
            });
        }, 60);
    }

    // ==================== PORTFOLIO ====================
    async function loadPortfolio() {
        var grid = $("#portfolioGrid");
        setLoading(grid, true);
        try {
            var data = await sbSelect("portfolio", { order: "created_at", asc: false });
            state.portfolio = data.map(function(item) {
                return Object.assign({}, item, { url: portfolioUrl(item.filename) });
            });
            state.loaded.portfolio = true;
            renderPortfolio();
        } catch(e) {
            console.error(e);
            setEmpty(grid, "ph-light ph-image-broken", "Не удалось загрузить портфолио");
        }
    }

    function renderPortfolio() {
        var grid     = $("#portfolioGrid");
        var items    = state.portfolio;
        var filter   = state.portfolioFilter;
        var filtered = filter === "all" ? items : items.filter(function(x) { return x.category === filter; });
        if (!filtered.length) {
            setEmpty(grid,
                items.length ? "ph-light ph-funnel" : "ph-light ph-image-broken",
                items.length ? "Нет работ в этой категории" : "Портфолио пока пусто"
            );
            return;
        }
        var html = "";
        filtered.forEach(function(it, j) {
            html +=
                '<div class="p-card" data-pidx="' + j + '">' +
                '<img src="' + esc(it.url) + '" alt="' + esc(it.title || "") + '" loading="lazy">' +
                '<div class="p-card-info">' +
                '<h4>' + esc(it.title || "") + '</h4>' +
                (it.category ? '<span class="p-card-cat">' + esc(CATEGORY_LABELS[it.category] || it.category) + '</span>' : '') +
                '</div></div>';
        });
        grid.innerHTML   = html;
        grid._filtered   = filtered;
        $$(".p-card").forEach(function(card) {
            card.addEventListener("click", function() {
                var idx = parseInt(this.getAttribute("data-pidx"), 10);
                if (grid._filtered[idx]) openViewer(grid._filtered[idx]);
            });
        });
    }

    function initPortfolioFilter() {
        var bar = $("#portfolioFilter");
        if (!bar) return;
        bar.addEventListener("click", function(e) {
            var chip = e.target.closest(".chip");
            if (!chip) return;
            $$(".chip").forEach(function(c) { c.classList.remove("active"); });
            chip.classList.add("active");
            state.portfolioFilter = chip.getAttribute("data-filter") || "all";
            renderPortfolio();
        });
    }

    // ==================== USER ORDERS ====================
    async function loadOrders() {
        var el = $("#ordersList");
        setLoading(el);
        if (!state.userId) {
            setEmpty(el, "ph-light ph-user-circle", "Войдите через Telegram");
            return;
        }
        try {
            var data = await sbSelect("orders", {
                eq:    ["user_id", state.userId],
                order: "created_at",
                asc:   false
            });
            state.orders = data;
            renderOrders();
        } catch(e) {
            setEmpty(el, "ph-light ph-warning-circle", "Не удалось загрузить заказы");
        }
    }

    function renderOrders() {
        var el   = $("#ordersList");
        var list = state.orders;
        if (!list.length) {
            setEmpty(el, "ph-light ph-clipboard-text", "Заказов пока нет", "Они появятся здесь после оформления");
            return;
        }
        var html = "";
        list.forEach(function(o, i) {
            html +=
                '<div class="o-card" data-oi="' + i + '">' +
                '<div class="o-card-top">' +
                '<span class="o-num">#' + o.id + '</span>' +
                statusBadge(o.status) +
                '</div>' +
                '<div class="o-details">' +
                '<span>' + esc(TYPE_MAP[o.order_type] || o.order_type) + '</span>' +
                (o.total_price > 0 ? '<span>' + fmt(o.total_price) + '\u00a0руб.</span>' : '') +
                '<span>' + fmtDate(o.created_at) + '</span>' +
                '</div></div>';
        });
        el.innerHTML = html;
        $$(".o-card").forEach(function(card) {
            card.addEventListener("click", function() {
                var idx = parseInt(this.getAttribute("data-oi"), 10);
                if (state.orders[idx]) openOrderDetail(state.orders[idx]);
            });
        });
    }

    function openOrderDetail(order) {
        var fields = [
            ["Тип",    TYPE_MAP[order.order_type] || order.order_type],
            ["Статус", STATUS_MAP[order.status]   || order.status]
        ];
        if (order.total_price > 0) fields.push(["Сумма", fmt(order.total_price) + "\u00a0руб."]);
        fields.push(["Создан", fmtDate(order.created_at)]);
        if (order.contact_info) fields.push(["Контакт", order.contact_info]);

        var html = '<div style="margin-bottom:16px;">' + statusBadge(order.status) + '</div>';
        fields.forEach(function(f) {
            html +=
                '<div style="display:flex;justify-content:space-between;padding:9px 0;border-bottom:1px solid var(--border);">' +
                '<span style="font-size:0.8rem;color:var(--w40);">' + esc(f[0]) + '</span>' +
                '<span style="font-size:0.8rem;font-weight:600;color:var(--w80);text-align:right;max-width:60%;">' + esc(f[1]) + '</span>' +
                '</div>';
        });
        if (order.details) {
            html +=
                '<div style="margin-top:14px;background:var(--surface3);border-radius:var(--r);padding:13px;border:1px solid var(--border);">' +
                '<div style="font-size:0.7rem;color:var(--w40);margin-bottom:6px;font-weight:600;text-transform:uppercase;letter-spacing:0.05em;">Детали</div>' +
                '<div style="font-size:0.78rem;white-space:pre-wrap;color:var(--w60);line-height:1.6;">' + esc(order.details) + '</div>' +
                '</div>';
        }
        openModal("Заказ #" + order.id, html);
    }

    // ==================== BUYOUT ====================
    function initBuyoutForm() {
        var form = $("#buyoutForm");
        if (!form) return;
        form.addEventListener("submit", async function(e) {
            e.preventDefault();
            var contact    = ($("#buyoutContact")    || {}).value.trim();
            var deviceType = ($("#buyoutDeviceType") || {}).value || "";
            var condition  = ($("#buyoutCondition")  || {}).value || "";
            var defects    = (($("#buyoutDefects")   || {}).value || "").trim() || "нет";
            if (!contact || !deviceType || !condition) { toast("Заполните поля", "error"); return; }
            var details = "Устройство: " + deviceType + "\nСостояние: " + condition + "\nНеисправности: " + defects;
            var btn = form.querySelector('button[type="submit"]');
            setBtnLoading(btn, true);
            var result = await submitOrder("buyout", "evaluation", details, 0, contact);
            setBtnLoading(btn, false);
            if (result) { form.reset(); nav("more"); }
        });
    }

    // ================================================================
    //  ADMIN PANEL
    // ================================================================

    function adminLoadTab(tabId) {
        state.admin.currentTab = tabId;
        var loaders = {
            "a-dashboard": adminLoadStats,
            "a-services":  adminLoadServices,
            "a-builds":    adminLoadBuilds,
            "a-ready":     adminLoadReadyBuilds,
            "a-orders":    adminLoadOrders,
            "a-portfolio": adminLoadPortfolio,
            "a-users":     adminLoadUsers
        };
        if (loaders[tabId]) loaders[tabId]();
    }

    function initAdminTabs() {
        var tabsEl = $("#adminTabs");
        if (!tabsEl) return;
        tabsEl.addEventListener("click", function(e) {
            var tab = e.target.closest(".admin-tab");
            if (!tab) return;
            $$(".admin-tab").forEach(function(t) { t.classList.remove("active"); });
            tab.classList.add("active");
            var id = tab.getAttribute("data-atab");
            $$(".admin-panel").forEach(function(p) { p.classList.remove("active"); });
            var panel = $("#" + id);
            if (panel) panel.classList.add("active");
            adminLoadTab(id);
        });
    }

    // --- Stats ---
    async function adminLoadStats() {
        var el = $("#adminStatsGrid");
        setLoading(el);
        try {
            var results = await Promise.all([
                sbSelect("users",        { count: true }),
                sbSelect("orders",       { count: true }),
                sbSelect("portfolio",    { count: true }),
                sbSelect("services",     { count: true }),
                sbSelect("builds",       { count: true }),
                sbSelect("ready_builds", { count: true }),
                db.from("orders").select("*", { count: "exact", head: true }).eq("status", "processing").then(function(r) { return r.count || 0; }),
                db.from("orders").select("*", { count: "exact", head: true }).eq("status", "completed").then(function(r)  { return r.count || 0; }),
                db.from("orders").select("*", { count: "exact", head: true }).eq("status", "in_progress").then(function(r){ return r.count || 0; })
            ]);
            el.innerHTML =
                adminStat("Пользователей",  results[0], "ph-bold ph-users") +
                adminStat("Всего заказов",  results[1], "ph-bold ph-clipboard-text") +
                adminStat("В обработке",    results[6], "ph-bold ph-hourglass") +
                adminStat("В работе",       results[8], "ph-bold ph-wrench") +
                adminStat("Завершено",      results[7], "ph-bold ph-check-circle") +
                adminStat("Портфолио",      results[2], "ph-bold ph-images") +
                adminStat("Услуг",          results[3], "ph-bold ph-list-bullets") +
                adminStat("Конфиг сборок",  results[4], "ph-bold ph-desktop-tower") +
                adminStat("Готовых сборок", results[5], "ph-bold ph-package");
        } catch(e) {
            el.innerHTML = '<div class="portfolio-empty"><p>Ошибка загрузки статистики</p></div>';
        }
    }

    function adminStat(label, num, icon) {
        return '<div class="admin-stat">' +
            (icon ? '<i class="' + icon + '" style="font-size:1.1rem;color:var(--accent-soft);opacity:0.7;margin-bottom:6px;display:block;"></i>' : '') +
            '<div class="admin-stat-num">' + (num || 0) + '</div>' +
            '<div class="admin-stat-label">' + esc(label) + '</div>' +
            '</div>';
    }

    // --- Services Admin ---
    async function adminLoadServices() {
        var el = $("#adminServicesList");
        setLoading(el);
        try {
            state.admin.services = await sbSelect("services", { order: "id", asc: true });
            adminRenderServices();
        } catch(e) { setEmpty(el, "ph-light ph-warning-circle", "Ошибка загрузки"); }
    }

    function adminRenderServices() {
        var el   = $("#adminServicesList");
        var list = state.admin.services;
        if (!list.length) { setEmpty(el, "ph-light ph-wrench", "Услуг нет"); return; }
        var html = "";
        list.forEach(function(s) {
            html +=
                '<div class="admin-item">' +
                '<div class="admin-item-id">#' + s.id + '</div>' +
                '<div class="admin-item-info">' +
                '<div class="admin-item-title">' + esc(s.title) + '</div>' +
                '<div class="admin-item-sub">' + esc(s.price_text) + ' · ' + (s.payment === "prepay" ? "Предоплата" : "По факту") + '</div>' +
                '</div>' +
                '<div class="admin-item-actions">' +
                '<button class="btn btn-ghost btn-sm" onclick="window._adminEditService(' + s.id + ')"><i class="ph-bold ph-pencil-simple"></i></button>' +
                '<button class="btn btn-ghost btn-sm" style="color:#e17055;" onclick="window._adminDeleteService(' + s.id + ')"><i class="ph-bold ph-trash"></i></button>' +
                '</div></div>';
        });
        el.innerHTML = html;
    }

    function _svcFormHtml(s) {
        s = s || {};
        return '<div class="form-group"><label>Название *</label><input id="ae_svc_title" value="' + esc(s.title || "") + '" placeholder="Название услуги"></div>' +
            '<div class="form-group"><label>Описание</label><textarea id="ae_svc_desc" rows="2">' + esc(s.description || "") + '</textarea></div>' +
            '<div class="form-group"><label>Цена (текст)</label><input id="ae_svc_pt" value="' + esc(s.price_text || "") + '" placeholder="от 1 000 руб."></div>' +
            '<div class="form-group"><label>Мин. цена (число)</label><input type="number" id="ae_svc_pf" value="' + (s.price_from || 0) + '"></div>' +
            '<div class="form-group"><label>Оплата</label><select id="ae_svc_pay">' +
            '<option value="postpay"' + (s.payment === "postpay" ? " selected" : "") + '>По факту</option>' +
            '<option value="prepay"'  + (s.payment === "prepay"  ? " selected" : "") + '>Предоплата</option>' +
            '</select></div>';
    }

    window._adminEditService = function(id) {
        var svc = state.admin.services.find(function(s) { return s.id === id; });
        if (!svc) return;
        openModal("Редактировать услугу",
            _svcFormHtml(svc) +
            '<div style="display:flex;gap:8px;margin-top:16px;">' +
            '<button class="btn btn-primary" onclick="window._adminSaveService(' + id + ')">Сохранить</button>' +
            '<button class="btn btn-ghost"   onclick="closeModal()">Отмена</button></div>');
    };

    window._adminNewService = function() {
        openModal("Новая услуга",
            _svcFormHtml() +
            '<div style="display:flex;gap:8px;margin-top:16px;">' +
            '<button class="btn btn-primary" onclick="window._adminSaveService(0)">Добавить</button>' +
            '<button class="btn btn-ghost"   onclick="closeModal()">Отмена</button></div>');
    };

    window._adminSaveService = async function(id) {
        var payload = {
            title:       ($("#ae_svc_title") || {}).value || "",
            description: ($("#ae_svc_desc")  || {}).value || "",
            price_text:  ($("#ae_svc_pt")    || {}).value || "",
            price_from:  parseInt(($("#ae_svc_pf") || {}).value) || 0,
            payment:     ($("#ae_svc_pay")   || {}).value || "postpay"
        };
        if (!payload.title) { toast("Введите название", "error"); return; }
        try {
            if (id) { await sbUpdate("services", payload, "id", id); toast("Обновлено"); }
            else    { await sbInsert("services", payload);            toast("Добавлено"); }
            closeModal();
            state.loaded.services = false;
            adminLoadServices();
        } catch(e) { toast("Ошибка сохранения", "error"); }
    };

    window._adminDeleteService = async function(id) {
        if (!confirm("Удалить услугу #" + id + "?")) return;
        try {
            await sbDelete("services", "id", id);
            toast("Удалено");
            state.loaded.services = false;
            adminLoadServices();
        } catch(e) { toast("Ошибка", "error"); }
    };

    // --- Builds Admin ---
    async function adminLoadBuilds() {
        var el = $("#adminBuildsList");
        setLoading(el);
        try {
            state.admin.builds = await sbSelect("builds", { order: "price", asc: true });
            adminRenderBuilds();
        } catch(e) { setEmpty(el, "ph-light ph-warning-circle", "Ошибка загрузки"); }
    }

    function adminRenderBuilds() {
        var el   = $("#adminBuildsList");
        var list = state.admin.builds;
        if (!list.length) { setEmpty(el, "ph-light ph-desktop-tower", "Сборок нет"); return; }
        var html = "";
        list.forEach(function(b) {
            html +=
                '<div class="admin-item">' +
                '<div class="admin-item-id">#' + b.id + '</div>' +
                '<div class="admin-item-info">' +
                '<div class="admin-item-title">' + esc(b.name) + ' <span style="color:var(--accent-soft);font-size:0.65rem;">[' + esc(b.tier) + ']</span></div>' +
                '<div class="admin-item-sub">' + esc(b.price_text) + '</div>' +
                '</div>' +
                '<div class="admin-item-actions">' +
                '<button class="btn btn-ghost btn-sm" onclick="window._adminEditBuild(' + b.id + ')"><i class="ph-bold ph-pencil-simple"></i></button>' +
                '<button class="btn btn-ghost btn-sm" style="color:#e17055;" onclick="window._adminDeleteBuild(' + b.id + ')"><i class="ph-bold ph-trash"></i></button>' +
                '</div></div>';
        });
        el.innerHTML = html;
    }

    function _bldFormHtml(b) {
        b = b || {};
        return '<div class="form-group"><label>Название *</label><input id="ae_bld_name" value="' + esc(b.name || "") + '" placeholder="Игровой ПК"></div>' +
            '<div class="form-group"><label>Тег / Тип</label><input id="ae_bld_tier" value="' + esc(b.tier || "") + '" placeholder="Игры, Офис, Профи..."></div>' +
            '<div class="form-group"><label>Описание</label><textarea id="ae_bld_desc" rows="2">' + esc(b.description || "") + '</textarea></div>' +
            '<div class="form-group"><label>Цена (число)</label><input type="number" id="ae_bld_price" value="' + (b.price || 0) + '"></div>' +
            '<div class="form-group"><label>Цена (текст)</label><input id="ae_bld_pt" value="' + esc(b.price_text || "") + '" placeholder="от 40 000 руб."></div>';
    }

    window._adminEditBuild = function(id) {
        var bld = state.admin.builds.find(function(b) { return b.id === id; });
        if (!bld) return;
        openModal("Редактировать сборку",
            _bldFormHtml(bld) +
            '<div style="display:flex;gap:8px;margin-top:16px;">' +
            '<button class="btn btn-primary" onclick="window._adminSaveBuild(' + id + ')">Сохранить</button>' +
            '<button class="btn btn-ghost"   onclick="closeModal()">Отмена</button></div>');
    };

    window._adminNewBuild = function() {
        openModal("Новая конфиг-сборка",
            _bldFormHtml() +
            '<div style="display:flex;gap:8px;margin-top:16px;">' +
            '<button class="btn btn-primary" onclick="window._adminSaveBuild(0)">Добавить</button>' +
            '<button class="btn btn-ghost"   onclick="closeModal()">Отмена</button></div>');
    };

    window._adminSaveBuild = async function(id) {
        var payload = {
            name:        ($("#ae_bld_name")  || {}).value || "",
            tier:        ($("#ae_bld_tier")  || {}).value || "",
            description: ($("#ae_bld_desc")  || {}).value || "",
            price:       parseInt(($("#ae_bld_price") || {}).value) || 0,
            price_text:  ($("#ae_bld_pt")    || {}).value || ""
        };
        if (!payload.name) { toast("Введите название", "error"); return; }
        try {
            if (id) { await sbUpdate("builds", payload, "id", id); toast("Обновлено"); }
            else    { await sbInsert("builds", payload);            toast("Добавлено"); }
            closeModal();
            state.loaded.builds = false;
            adminLoadBuilds();
        } catch(e) { toast("Ошибка", "error"); }
    };

    window._adminDeleteBuild = async function(id) {
        if (!confirm("Удалить сборку #" + id + "?")) return;
        try {
            await sbDelete("builds", "id", id);
            toast("Удалено");
            state.loaded.builds = false;
            adminLoadBuilds();
        } catch(e) { toast("Ошибка", "error"); }
    };

    // --- Ready Builds Admin ---
    async function adminLoadReadyBuilds() {
        var el = $("#adminReadyList");
        setLoading(el);
        try {
            state.admin.readyBuilds = await sbSelect("ready_builds", { order: "created_at", asc: false });
            adminRenderReadyBuilds();
        } catch(e) { setEmpty(el, "ph-light ph-warning-circle", "Ошибка загрузки"); }
    }

    function adminRenderReadyBuilds() {
        var el   = $("#adminReadyList");
        var list = state.admin.readyBuilds;
        if (!list.length) { setEmpty(el, "ph-light ph-package", "Готовых сборок нет"); return; }
        var statusLabels = { available: "В наличии", reserved: "Забронировано", sold: "Продано" };
        var html = "";
        list.forEach(function(b) {
            html +=
                '<div class="admin-item">' +
                '<div class="admin-item-id">#' + b.id + '</div>' +
                '<div class="admin-item-info">' +
                '<div class="admin-item-title">' + esc(b.name) + '</div>' +
                '<div class="admin-item-sub">' + (b.price ? fmt(b.price) + '\u00a0руб.' : 'По запросу') + ' · ' + (statusLabels[b.status] || b.status) + '</div>' +
                '</div>' +
                '<div class="admin-item-actions">' +
                '<button class="btn btn-ghost btn-sm" onclick="window._adminEditReady(' + b.id + ')"><i class="ph-bold ph-pencil-simple"></i></button>' +
                '<button class="btn btn-ghost btn-sm" style="color:#e17055;" onclick="window._adminDeleteReady(' + b.id + ')"><i class="ph-bold ph-trash"></i></button>' +
                '</div></div>';
        });
        el.innerHTML = html;
    }

    // ✅ ОБНОВЛЕНО: форма с загрузкой файла вместо URL
    function _readyFormHtml(b) {
        b = b || {};
        var hasImg = b.image_url || "";
        return '<div class="form-group"><label>Фото сборки</label>' +
            '<div class="upload-area" id="readyUploadArea">' +
            '<input type="file" id="readyFileInput" accept="image/*">' +
            '<i class="ph-bold ph-image"></i>' +
            '<p>' + (hasImg ? 'Загрузить новое фото' : 'Нажмите или перетащите фото') + '</p>' +
            '<span>JPG, PNG, WEBP до 10 МБ</span>' +
            '</div>' +
            (hasImg
                ? '<div style="margin-top:8px;border-radius:var(--r);overflow:hidden;height:120px;"><img id="readyPreviewImg" src="' + esc(hasImg) + '" style="width:100%;height:100%;object-fit:cover;"></div>'
                : '<div id="readyPreview" class="hidden" style="margin-top:8px;border-radius:var(--r);overflow:hidden;height:120px;"><img id="readyPreviewImg" style="width:100%;height:100%;object-fit:cover;"></div>'
            ) +
            '<div class="upload-progress hidden" id="readyProgress"><div class="upload-progress-bar" id="readyProgressBar"></div></div>' +
            '</div>' +
            '<input type="hidden" id="ae_rb_img_existing" value="' + esc(hasImg) + '">' +
            '<div class="form-group"><label>Название *</label><input id="ae_rb_name" value="' + esc(b.name || "") + '" placeholder="RTX 4070 + Ryzen 5 7600X"></div>' +
            '<div class="form-group"><label>Комплектация</label><textarea id="ae_rb_specs" rows="5" placeholder="CPU: Intel i5-13600K\nGPU: RTX 4070\nRAM: 32GB DDR5\nSSD: 1TB NVMe">' + esc(b.specs || "") + '</textarea></div>' +
            '<div class="form-group"><label>Описание</label><textarea id="ae_rb_desc" rows="2">' + esc(b.description || "") + '</textarea></div>' +
            '<div class="form-group"><label>Цена (руб.)</label><input type="number" id="ae_rb_price" value="' + (b.price || "") + '" placeholder="150000"></div>' +
            '<div class="form-group"><label>Статус</label><select id="ae_rb_status">' +
            '<option value="available"' + (b.status === "available" ? " selected" : "") + '>✅ В наличии</option>' +
            '<option value="reserved"'  + (b.status === "reserved"  ? " selected" : "") + '>🔒 Забронировано</option>' +
            '<option value="sold"'      + (b.status === "sold"      ? " selected" : "") + '>❌ Продано</option>' +
            '</select></div>';
    }

    window._adminEditReady = function(id) {
        var b = state.admin.readyBuilds.find(function(x) { return x.id === id; });
        if (!b) return;
        openModal("Редактировать готовую сборку",
            _readyFormHtml(b) +
            '<div style="display:flex;gap:8px;margin-top:16px;">' +
            '<button class="btn btn-primary" onclick="window._adminSaveReady(' + id + ')">Сохранить</button>' +
            '<button class="btn btn-ghost"   onclick="closeModal()">Отмена</button></div>');
        // Вешаем превью после рендера
        setTimeout(function() {
            var input   = $("#readyFileInput");
            var preview = $("#readyPreview");
            var prevImg = $("#readyPreviewImg");
            if (!input) return;
            input.addEventListener("change", function() {
                var file = this.files[0];
                if (!file) return;
                var reader = new FileReader();
                reader.onload = function(e) {
                    prevImg.src = e.target.result;
                    if (preview) preview.classList.remove("hidden");
                };
                reader.readAsDataURL(file);
            });
        }, 60);
    };

    window._adminNewReady = function() {
        openModal("Новая готовая сборка",
            _readyFormHtml() +
            '<div style="display:flex;gap:8px;margin-top:16px;">' +
            '<button class="btn btn-primary" onclick="window._adminSaveReady(0)">Добавить</button>' +
            '<button class="btn btn-ghost"   onclick="closeModal()">Отмена</button></div>');
        // Вешаем превью после рендера
        setTimeout(function() {
            var input   = $("#readyFileInput");
            var preview = $("#readyPreview");
            var prevImg = $("#readyPreviewImg");
            if (!input) return;
            input.addEventListener("change", function() {
                var file = this.files[0];
                if (!file) return;
                var reader = new FileReader();
                reader.onload = function(e) {
                    prevImg.src = e.target.result;
                    if (preview) preview.classList.remove("hidden");
                };
                reader.readAsDataURL(file);
            });
        }, 60);
    };

    // ✅ ОБНОВЛЕНО: сохранение с загрузкой в Storage
    window._adminSaveReady = async function(id) {
        var input       = $("#readyFileInput");
        var file        = input && input.files && input.files[0];
        var existingUrl = ($("#ae_rb_img_existing") || {}).value || "";
        var priceVal    = parseInt(($("#ae_rb_price") || {}).value) || 0;

        var payload = {
            name:        ($("#ae_rb_name")   || {}).value || "",
            specs:       ($("#ae_rb_specs")  || {}).value || "",
            description: ($("#ae_rb_desc")   || {}).value || "",
            price:       priceVal || null,
            image_url:   existingUrl,
            status:      ($("#ae_rb_status") || {}).value || "available"
        };

        if (!payload.name) { toast("Введите название", "error"); return; }

        if (file) {
            if (file.size > 10 * 1024 * 1024) { toast("Файл слишком большой (макс. 10 МБ)", "error"); return; }
            var progress    = $("#readyProgress");
            var progressBar = $("#readyProgressBar");
            if (progress) progress.classList.remove("hidden");
            if (progressBar) progressBar.style.width = "30%";
            try {
                payload.image_url = await uploadToStorage("portfolio", file, "ready");
                if (progressBar) progressBar.style.width = "80%";
            } catch(e) {
                toast("Ошибка загрузки фото", "error");
                if (progress) progress.classList.add("hidden");
                return;
            }
        }

        try {
            if (id) { await sbUpdate("ready_builds", payload, "id", id); toast("Обновлено"); }
            else {
                await sbInsert("ready_builds", Object.assign({ created_at: new Date().toISOString() }, payload));
                toast("Добавлено");
            }
            closeModal();
            state.loaded.readyBuilds = false;
            state.readyBuilds        = [];
            adminLoadReadyBuilds();
        } catch(e) { toast("Ошибка сохранения", "error"); }
    };

    window._adminDeleteReady = async function(id) {
        if (!confirm("Удалить готовую сборку #" + id + "?")) return;
        try {
            await sbDelete("ready_builds", "id", id);
            toast("Удалено");
            state.loaded.readyBuilds = false;
            state.readyBuilds        = [];
            adminLoadReadyBuilds();
        } catch(e) { toast("Ошибка", "error"); }
    };

    // --- Orders Admin ---
    async function adminLoadOrders() {
        var el = $("#adminOrdersList");
        setLoading(el);
        try {
            state.admin.orders = await sbSelect("orders", { order: "created_at", asc: false });
            adminRenderOrders();
        } catch(e) { setEmpty(el, "ph-light ph-warning-circle", "Ошибка загрузки"); }
    }

    function adminRenderOrders() {
        var el   = $("#adminOrdersList");
        var list = state.admin.orders;
        if (!list.length) { setEmpty(el, "ph-light ph-clipboard-text", "Заказов нет"); return; }
        var html = "";
        list.forEach(function(o) {
            html +=
                '<div class="admin-item" style="cursor:pointer;" onclick="window._adminShowOrder(' + o.id + ')">' +
                '<div class="admin-item-id">#' + o.id + '</div>' +
                '<div class="admin-item-info">' +
                '<div class="admin-item-title">' + esc(TYPE_MAP[o.order_type] || o.order_type) + ' ' + statusBadge(o.status) + '</div>' +
                '<div class="admin-item-sub">' + esc(o.contact_info || "—") + ' · ' + fmt(o.total_price) + '\u00a0руб. · ' + fmtDate(o.created_at) + '</div>' +
                '</div>' +
                '<i class="ph-bold ph-caret-right" style="color:var(--w20);flex-shrink:0;"></i>' +
                '</div>';
        });
        el.innerHTML = html;
    }

    window._adminShowOrder = function(id) {
        var o = state.admin.orders.find(function(x) { return x.id === id; });
        if (!o) return;
        var statusOpts = "";
        Object.keys(STATUS_MAP).forEach(function(k) {
            statusOpts += '<option value="' + k + '"' + (o.status === k ? " selected" : "") + '>' + STATUS_MAP[k] + '</option>';
        });
        var html =
            '<div style="margin-bottom:14px;">' + statusBadge(o.status) + '</div>' +
            '<div style="font-size:0.82rem;color:var(--w60);line-height:2;margin-bottom:12px;">' +
            '<b>Тип:</b> '     + esc(TYPE_MAP[o.order_type] || o.order_type) + '<br>' +
            '<b>Контакт:</b> ' + esc(o.contact_info || "—") + '<br>' +
            '<b>Сумма:</b> '   + fmt(o.total_price) + '\u00a0руб.<br>' +
            '<b>Создан:</b> '  + fmtDate(o.created_at) + '<br>' +
            (o.delivery_info ? '<b>Доставка:</b> ' + esc(o.delivery_info) + '<br>' : '') +
            '</div>';
        if (o.details) {
            html += '<div style="padding:12px;background:var(--surface3);border-radius:8px;border:1px solid var(--border);font-size:0.78rem;white-space:pre-wrap;color:var(--w60);margin-bottom:14px;">' + esc(o.details) + '</div>';
        }
        html +=
            '<div class="form-group"><label>Изменить статус</label><select id="ae_order_status">' + statusOpts + '</select></div>' +
            '<div style="display:flex;gap:8px;margin-top:16px;">' +
            '<button class="btn btn-primary" onclick="window._adminChangeStatus(' + o.id + ')">Сохранить</button>' +
            '<button class="btn btn-ghost"   onclick="closeModal()">Закрыть</button></div>';
        openModal("Заказ #" + o.id, html);
    };

    window._adminChangeStatus = async function(id) {
        var status = ($("#ae_order_status") || {}).value;
        if (!status) return;
        try {
            await sbUpdate("orders", { status: status, updated_at: new Date().toISOString() }, "id", id);
            toast("Статус обновлён");
            closeModal();
            adminLoadOrders();
        } catch(e) { toast("Ошибка", "error"); }
    };

    // --- Portfolio Admin ---
    async function adminLoadPortfolio() {
        var el = $("#adminPortfolioList");
        setLoading(el);
        try {
            state.admin.portfolio = await sbSelect("portfolio", { order: "created_at", asc: false });
            adminRenderPortfolio();
        } catch(e) { setEmpty(el, "ph-light ph-warning-circle", "Ошибка загрузки"); }
    }

    function adminRenderPortfolio() {
        var el   = $("#adminPortfolioList");
        var list = state.admin.portfolio;
        if (!list.length) { setEmpty(el, "ph-light ph-images", "Портфолио пусто"); return; }
        var html = "";
        list.forEach(function(it) {
            var url = portfolioUrl(it.filename);
            html +=
                '<div class="admin-item">' +
                '<img src="' + esc(url) + '" style="width:48px;height:48px;object-fit:cover;border-radius:8px;flex-shrink:0;">' +
                '<div class="admin-item-info">' +
                '<div class="admin-item-title">' + esc(it.title || "Без названия") + '</div>' +
                '<div class="admin-item-sub">ID:' + it.id + ' · ' + esc(CATEGORY_LABELS[it.category] || it.category) + '</div>' +
                '</div>' +
                '<button class="btn btn-ghost btn-sm" style="color:#e17055;" onclick="window._adminDeletePortfolio(' + it.id + ')"><i class="ph-bold ph-trash"></i></button>' +
                '</div>';
        });
        el.innerHTML = html;
    }

    // ✅ ОБНОВЛЕНО: загрузка через Storage
    window._adminAddPortfolio = function() {
        openModal("Добавить в портфолио",
            '<div class="form-group"><label>Фото *</label>' +
            '<div class="upload-area" id="portfolioUploadArea">' +
            '<input type="file" id="portfolioFileInput" accept="image/*">' +
            '<i class="ph-bold ph-image"></i>' +
            '<p>Нажмите или перетащите фото</p>' +
            '<span>JPG, PNG, WEBP до 5 МБ</span>' +
            '</div>' +
            '<div id="portfolioPreview" class="hidden" style="margin-top:8px;border-radius:var(--r);overflow:hidden;aspect-ratio:16/9;background:var(--surface3);">' +
            '<img id="portfolioPreviewImg" style="width:100%;height:100%;object-fit:cover;">' +
            '</div>' +
            '<div class="upload-progress hidden" id="portfolioProgress"><div class="upload-progress-bar" id="portfolioProgressBar"></div></div>' +
            '</div>' +
            '<div class="form-group"><label>Название</label><input id="ae_p_title" placeholder="Игровая сборка RTX 4080"></div>' +
            '<div class="form-group"><label>Описание</label><textarea id="ae_p_desc" rows="2"></textarea></div>' +
            '<div class="form-group"><label>Категория</label><select id="ae_p_cat">' +
            '<option value="build">Сборка</option>' +
            '<option value="repair">Ремонт</option>' +
            '<option value="upgrade">Апгрейд</option>' +
            '<option value="custom">Кастом</option>' +
            '<option value="general">Другое</option>' +
            '</select></div>' +
            '<div style="display:flex;gap:8px;margin-top:6px;">' +
            '<button class="btn btn-primary" onclick="window._adminSavePortfolio()"><i class="ph-bold ph-upload-simple"></i> Загрузить</button>' +
            '<button class="btn btn-ghost" onclick="closeModal()">Отмена</button></div>'
        );
        setTimeout(function() {
            var input   = $("#portfolioFileInput");
            var preview = $("#portfolioPreview");
            var prevImg = $("#portfolioPreviewImg");
            if (!input) return;
            input.addEventListener("change", function() {
                var file = this.files[0];
                if (!file) return;
                var reader = new FileReader();
                reader.onload = function(e) {
                    prevImg.src = e.target.result;
                    preview.classList.remove("hidden");
                };
                reader.readAsDataURL(file);
            });
        }, 60);
    };

    // ✅ ОБНОВЛЕНО: сохранение портфолио через Storage
    window._adminSavePortfolio = async function() {
        var input    = $("#portfolioFileInput");
        var title    = ($("#ae_p_title") || {}).value.trim();
        var desc     = ($("#ae_p_desc")  || {}).value.trim();
        var category = ($("#ae_p_cat")   || {}).value || "general";
        var file     = input && input.files && input.files[0];
        if (!file) { toast("Выберите фото", "error"); return; }
        if (file.size > 5 * 1024 * 1024) { toast("Файл слишком большой (макс. 5 МБ)", "error"); return; }

        var progress    = $("#portfolioProgress");
        var progressBar = $("#portfolioProgressBar");
        if (progress) progress.classList.remove("hidden");
        if (progressBar) progressBar.style.width = "30%";

        try {
            var publicUrl = await uploadToStorage("portfolio", file);
            if (progressBar) progressBar.style.width = "70%";
            await sbInsert("portfolio", {
                filename:    publicUrl,
                title:       title,
                description: desc,
                category:    category,
                added_by:    state.userId,
                created_at:  new Date().toISOString()
            });
            if (progressBar) progressBar.style.width = "100%";
            toast("Фото загружено!", "success");
            setTimeout(function() { closeModal(); }, 400);
            state.portfolio        = [];
            state.loaded.portfolio = false;
            adminLoadPortfolio();
        } catch(e) {
            console.error(e);
            toast("Ошибка загрузки фото", "error");
            if (progress) progress.classList.add("hidden");
        }
    };

    window._adminDeletePortfolio = async function(id) {
        if (!confirm("Удалить работу #" + id + "?")) return;
        try {
            await sbDelete("portfolio", "id", id);
            toast("Удалено");
            state.portfolio        = [];
            state.loaded.portfolio = false;
            adminLoadPortfolio();
        } catch(e) { toast("Ошибка", "error"); }
    };

    // --- Users Admin ---
    async function adminLoadUsers() {
        var el = $("#adminUsersList");
        setLoading(el);
        try {
            state.admin.users = await sbSelect("users", { order: "last_active", asc: false });
            adminRenderUsers();
        } catch(e) { setEmpty(el, "ph-light ph-warning-circle", "Ошибка загрузки"); }
    }

    function adminRenderUsers() {
        var el   = $("#adminUsersList");
        var list = state.admin.users;
        if (!list.length) { setEmpty(el, "ph-light ph-users", "Пользователей нет"); return; }
        var html = "";
        list.forEach(function(u) {
            html +=
                '<div class="admin-item">' +
                '<div class="admin-item-id" style="font-size:0.6rem;">' + u.user_id + '</div>' +
                '<div class="admin-item-info">' +
                '<div class="admin-item-title">' + esc(u.full_name || "—") + '</div>' +
                '<div class="admin-item-sub">@' + esc(u.username || "—") + ' · ' + fmtDate(u.last_active) + '</div>' +
                '</div>' +
                '<a href="tg://user?id=' + u.user_id + '" class="btn btn-ghost btn-sm"><i class="ph-bold ph-telegram-logo"></i></a>' +
                '</div>';
        });
        el.innerHTML = html;
    }

    // ==================== MODAL / VIEWER ====================
    function initModal() {
        var closeBtn = $("#modalClose");
        if (closeBtn) closeBtn.addEventListener("click", closeModal);
        var overlay = $("#modalOverlay");
        if (overlay) overlay.addEventListener("click", function(e) {
            if (e.target === this) closeModal();
        });
    }

    function initViewer() {
        var closeBtn = $("#viewerClose");
        if (closeBtn) closeBtn.addEventListener("click", closeViewer);
        var viewer = $("#imageViewer");
        if (!viewer) return;
        var startY = 0, curY = 0;
        viewer.addEventListener("click", function(e) {
            if (e.target === viewer || e.target.classList.contains("viewer-img-wrap")) closeViewer();
        });
        viewer.addEventListener("touchstart", function(e) { startY = e.touches[0].clientY; curY = startY; }, { passive: true });
        viewer.addEventListener("touchmove",  function(e) { curY  = e.touches[0].clientY; },                { passive: true });
        viewer.addEventListener("touchend",   function()  { if (curY - startY > 80) closeViewer(); });
        var img = $("#viewerImage");
        if (img) img.addEventListener("click", function(e) {
            e.stopPropagation();
            var info = $("#viewerInfo");
            if (info) info.classList.toggle("hidden");
        });
    }

    function initKeyboard() {
        document.addEventListener("keydown", function(e) {
            if (e.key !== "Escape") return;
            var viewer = $("#imageViewer");
            var modal  = $("#modalOverlay");
            if (viewer && !viewer.classList.contains("hidden")) closeViewer();
            else if (modal && !modal.classList.contains("hidden")) closeModal();
        });
    }

    function initBackButton() {
        if (!tg || !tg.BackButton) return;
        tg.BackButton.onClick(function() {
            if (state.current === "home") { tg.close(); return; }
            nav(getBackTarget());
        });
    }

    function initAdminButtons() {
        var map = {
            "#adminAddService":       function() { window._adminNewService(); },
            "#adminAddBuild":         function() { window._adminNewBuild(); },
            "#adminAddReady":         function() { window._adminNewReady(); },
            "#adminAddPortfolio":     function() { window._adminAddPortfolio(); },
            "#adminRefreshStats":     adminLoadStats,
            "#adminRefreshOrders":    adminLoadOrders,
            "#adminRefreshPortfolio": adminLoadPortfolio,
            "#adminRefreshUsers":     adminLoadUsers,
            "#adminRefreshReady":     adminLoadReadyBuilds
        };
        Object.keys(map).forEach(function(sel) {
            var el = $(sel);
            if (el) el.addEventListener("click", map[sel]);
        });
    }

    // ==================== EXPOSE GLOBALS ====================
    window.closeModal  = closeModal;
    window.closeViewer = closeViewer;

    // ==================== MAIN ====================
    async function init() {
        initSplash();
        loadConfig();
        initNavigation();
        initModal();
        initViewer();
        initPortfolioFilter();
        initServiceForm();
        initBuildForm();
        initBuildsSwitcher();
        initBuyoutForm();
        initBackButton();
        initKeyboard();
        initAdminTabs();
        initAdminButtons();
        updateBackButton();
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }

})();
