(function (window) {
    var Bacheca = window.Bacheca = window.Bacheca || {};
    Bacheca.services = Bacheca.services || {};

    var config = window.BachecaConfig;
    var http = Bacheca.utils.http;
    var labels = {
        1: { name: "Maximum Readiness", meaning: "Highest alert" },
        2: { name: "Next Step to Maximum Readiness", meaning: "One step below maximum" },
        3: { name: "Increase in Force Readiness", meaning: "Forces on alert" },
        4: { name: "Increased Intelligence Watch", meaning: "Enhanced monitoring" },
        5: { name: "Lowest State of Readiness", meaning: "Normal situation" }
    };

    function buildUrl() {
        return (config.api && config.api.pizzaIndex) || "/api/pizza-index";
    }

    function labelFor(level) {
        return labels[level] || null;
    }

    function normalize(response) {
        var level;
        var label;

        if (!response || response.success !== true) {
            return null;
        }

        level = parseInt(response.defcon_level, 10);
        label = labelFor(level);

        if (!label) {
            return null;
        }

        return {
            level: level,
            title: "DOUGHCON " + level,
            name: label.name,
            meaning: label.meaning,
            overallIndex: response.overall_index,
            activeSpikes: response.active_spikes,
            hasActiveSpikes: !!response.has_active_spikes,
            timestamp: response.timestamp || "",
            freshness: response.data_freshness || ""
        };
    }

    function load(callback) {
        http.getJson(buildUrl(), function (error, response) {
            var normalized;
            if (error) {
                callback(error);
                return;
            }

            normalized = normalize(response);
            if (!normalized) {
                callback(new Error("Malformed pizza index response"));
                return;
            }

            callback(null, normalized);
        });
    }

    Bacheca.services.pizzaIndex = {
        buildUrl: buildUrl,
        labelFor: labelFor,
        load: load,
        normalize: normalize
    };
})(window);
