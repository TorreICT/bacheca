(function (window) {
    var Bacheca = window.Bacheca = window.Bacheca || {};
    Bacheca.services = Bacheca.services || {};

    var config = window.BachecaConfig;
    var http = Bacheca.utils.http;
    var dateUtils = Bacheca.utils.date;

    var sectionOrder = [
        { keys: ["Piatto Unico", "Unico", "unico"], label: "Piatto unico" },
        { keys: ["Primo"], label: "Primo" },
        { keys: ["Secondo"], label: "Secondo" },
        { keys: ["Contorno"], label: "Contorno" },
        { keys: ["Dolce"], label: "Dolce" }
    ];

    function capitalizeDishName(name) {
        var text = String(name || "").replace(/^\s+|\s+$/g, "");
        if (!text) {
            return "";
        }
        return text.charAt(0).toUpperCase() + text.slice(1);
    }

    function normalizeDish(dish) {
        var name;
        if (!dish && dish !== 0) {
            return "";
        }
        if (typeof dish === "string") {
            name = capitalizeDishName(dish);
            return isUnavailableDishName(name) ? "" : name;
        }
        name = dish.piatto || dish.nome || "";
        name = capitalizeDishName(name);
        return isUnavailableDishName(name) ? "" : name;
    }

    function isUnavailableDishName(name) {
        var text = String(name || "").replace(/^\s+|\s+$/g, "").toLowerCase();
        text = text.replace(/\u00e8/g, "e").replace(/\u00e9/g, "e");
        if (!text || text === "-" || text === "n.d." || text === "nd") {
            return true;
        }
        return text.indexOf("menu non disponibile") !== -1 ||
            text.indexOf("menu non ancora") !== -1 ||
            text.indexOf("menu non e ancora") !== -1 ||
            text.indexOf("non disponibile") !== -1 ||
            text.indexOf("non ancora uscito") !== -1 ||
            text.indexOf("nessun menu") !== -1;
    }

    function normalizeMeal(rawMeal) {
        var sections = [];
        var i;
        var items;
        var section;
        var keyIndex;
        var rawItems;

        if (!rawMeal) {
            return { available: false, sections: [] };
        }

        for (i = 0; i < sectionOrder.length; i++) {
            section = sectionOrder[i];
            rawItems = [];

            for (keyIndex = 0; keyIndex < section.keys.length; keyIndex++) {
                if (rawMeal[section.keys[keyIndex]]) {
                    rawItems = rawItems.concat(rawMeal[section.keys[keyIndex]]);
                }
            }

            if (!rawItems || !rawItems.length) {
                continue;
            }

            items = [];
            rawItems.forEach(function (dish) {
                var name = normalizeDish(dish);
                if (name) {
                    items.push(name);
                }
            });

            if (items.length) {
                sections.push({
                    label: section.label,
                    items: items
                });
            }
        }

        return {
            available: sections.length > 0,
            sections: sections
        };
    }

    function normalize(response) {
        return {
            pranzo: normalizeMeal(response && response.Pranzo),
            cena: normalizeMeal(response && response.Cena)
        };
    }

    function buildMenuUrl(date) {
        var path = (config.api && config.api.menu) || "/api/menu";
        return path + "?data=" + encodeURIComponent(dateUtils.formatIsoDate(date || new Date()));
    }

    function logMenu(message, detail) {
        if (window.console && window.console.log) {
            window.console.log("[Bacheca menu] " + message, detail || "");
        }
    }

    function load(callback) {
        var date = new Date();
        var dateText = dateUtils.formatIsoDate(date);
        var url = buildMenuUrl(date);

        logMenu("loading menu for " + dateText);
        logMenu("menu API URL: " + url);

        http.getJson(url, function (error, response) {
            var normalized;
            if (error) {
                logMenu("menu API request failed", error);
                callback(error);
                return;
            }

            logMenu("raw response has Pranzo=" + !!(response && response.Pranzo) + ", Cena=" + !!(response && response.Cena));
            normalized = normalize(response);
            logMenu("normalized availability Pranzo=" + normalized.pranzo.available + ", Cena=" + normalized.cena.available);
            callback(null, normalized);
        });
    }

    Bacheca.services.menu = {
        buildMenuUrl: buildMenuUrl,
        load: load,
        normalize: normalize
    };
})(window);
