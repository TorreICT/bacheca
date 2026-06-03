(function (window) {
    var Bacheca = window.Bacheca = window.Bacheca || {};
    Bacheca.components = Bacheca.components || {};

    var dom = Bacheca.utils.dom;

    function setLoading() {
        setCompactMode(false);
        renderUnavailableMessage(false);
        dom.setText(dom.byId("meals-status"), "Caricamento");
        renderStats("stats-pranzo", null);
        renderStats("stats-cena", null);
        renderMenu("menu-pranzo", null);
        renderMenu("menu-cena", null);
    }

    function render(data) {
        var errors = data && data.errors ? data.errors : [];
        var stats = data && data.stats ? data.stats : null;
        var menu = data && data.menu ? data.menu : null;
        var compactNoMenu = !!(data && data.compactNoMenu);

        dom.setText(dom.byId("meals-status"), errors.length ? "Dati parziali" : "Aggiornato");
        setCompactMode(compactNoMenu);

        renderStats("stats-pranzo", stats && stats.pranzo);
        renderStats("stats-cena", stats && stats.cena);

        if (compactNoMenu) {
            clearMenu("menu-pranzo");
            clearMenu("menu-cena");
            renderUnavailableMessage(true);
            return;
        }

        renderUnavailableMessage(false);
        renderMenu("menu-pranzo", menu && menu.pranzo);
        renderMenu("menu-cena", menu && menu.cena);
    }

    function setCompactMode(enabled) {
        var panel = dom.byId("meals-panel");
        if (!panel) {
            return;
        }
        if (enabled) {
            dom.addClass(panel, "is-menu-unavailable-compact");
        } else {
            dom.removeClass(panel, "is-menu-unavailable-compact");
        }
    }

    function renderUnavailableMessage(show) {
        var panel = dom.byId("meals-panel");
        var existing = dom.byId("menu-unavailable-message");
        var message;

        if (existing && existing.parentNode) {
            existing.parentNode.removeChild(existing);
        }

        if (!show || !panel) {
            return;
        }

        message = dom.create("div", "menu-unavailable-message", "Il menu non \u00e8 ancora disponibile");
        message.id = "menu-unavailable-message";
        panel.appendChild(message);
    }

    function renderStats(id, mealStats) {
        var mount = dom.byId(id);
        var items = mealStats && mealStats.items ? mealStats.items : [];

        dom.clear(mount);

        if (!items.length) {
            mount.appendChild(dom.emptyState("Presenze non disponibili"));
            return;
        }

        items.forEach(function (item) {
            mount.appendChild(createStatItem(item));
        });
    }

    function createStatItem(item) {
        var root = dom.create("div", "stat-item");
        var canvas = dom.create("canvas", "stat-ring-canvas");
        var image = dom.create("img", "stat-ring-icon");
        var value = dom.create("strong", "stat-ring-value", item.value);

        root.setAttribute("role", "img");
        root.setAttribute("aria-label", item.label + ": " + item.value);
        root.title = item.label + ": " + item.value;
        canvas.width = 180;
        canvas.height = 180;
        image.src = item.icon;
        image.alt = item.label;
        value.style.color = item.color || "#ffffff";

        root.appendChild(canvas);
        root.appendChild(image);
        root.appendChild(value);
        drawRing(canvas, item);
        return root;
    }

    function drawRing(canvas, item) {
        var ctx = canvas.getContext ? canvas.getContext("2d") : null;
        var value = parseInt(item.value, 10);
        var max = parseInt(item.max, 10);
        var percent;

        if (!ctx) {
            return;
        }

        value = isNaN(value) ? 0 : value;
        max = isNaN(max) || max <= 0 ? 1 : max;
        percent = Math.max(0, Math.min(value / max, 1));

        ctx.clearRect(0, 0, 180, 180);
        ctx.lineWidth = 12;
        ctx.strokeStyle = "#333333";
        ctx.beginPath();
        ctx.arc(90, 90, 72, -Math.PI / 2, (Math.PI * 3) / 2);
        ctx.stroke();

        if (percent <= 0) {
            return;
        }

        ctx.strokeStyle = item.color || "#8cc04d";
        ctx.lineCap = "round";
        ctx.beginPath();
        ctx.arc(90, 90, 72, -Math.PI / 2, (percent * Math.PI * 2) - (Math.PI / 2));
        ctx.stroke();
    }

    function renderMenu(id, mealMenu) {
        var mount = dom.byId(id);

        clearMenu(id);

        if (!mealMenu || !mealMenu.available) {
            mount.appendChild(dom.emptyState("Il menu non \u00e8 ancora uscito"));
            return;
        }

        dom.addClass(mount, "is-available");
        mealMenu.sections.forEach(function (section) {
            mount.appendChild(createMenuSection(section));
        });
    }

    function clearMenu(id) {
        var mount = dom.byId(id);
        dom.clear(mount);
        dom.removeClass(mount, "is-available");
    }

    function createMenuSection(section) {
        var root = dom.create("div", "menu-section");
        var title = dom.create("h4", "menu-section-label", section.label);
        var list = dom.create("ul");

        section.items.forEach(function (item) {
            list.appendChild(dom.create("li", "", item));
        });

        root.appendChild(title);
        root.appendChild(list);
        return root;
    }

    Bacheca.components.meals = {
        setLoading: setLoading,
        render: render
    };
})(window);
