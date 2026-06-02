(function (window) {
    var Bacheca = window.Bacheca = window.Bacheca || {};
    Bacheca.services = Bacheca.services || {};

    var config = window.BachecaConfig;
    var http = Bacheca.utils.http;

    function buildMealsUrl() {
        return (config.api && config.api.meals) || "/api/pasti";
    }

    function toNumber(value) {
        var parsed;
        if (value === undefined || value === null || value === "-" || value === "") {
            return 0;
        }
        parsed = parseInt(value, 10);
        return isNaN(parsed) ? 0 : parsed;
    }

    function readStats(rawStats) {
        var presente = toNumber(rawStats && rawStats.Presente);
        var turno1 = toNumber(rawStats && rawStats["Turno 1"]);
        var turno2 = toNumber(rawStats && rawStats["Turno 2"]);
        var sacchetto = toNumber(rawStats && rawStats.Sacchetto);
        var vassoio = toNumber(rawStats && rawStats.Vassoio);
        var assente = toNumber(rawStats && rawStats.Assente);
        var items;

        if (presente > 0) {
            items = [
                stat("presente", "Presenze", presente, "presente.svg", "#8cc04d", 60),
                stat("sacchetto", "Sacchetti", sacchetto, "sacchetto.svg", "#428dcc", 32),
                stat("vassoio", "Vassoi", vassoio, "vassoio.svg", "#23a69a", 32),
                stat("assente", "Assenze", assente, "assente.svg", "#ee6f49", 60)
            ];
        } else {
            items = [
                stat("turno1", "Turno 1", turno1, "turno1.svg", "#8cc04d", 32),
                stat("turno2", "Turno 2", turno2, "turno2.svg", "#8cc04d", 32),
                stat("sacchetto", "Sacchetti", sacchetto, "sacchetto.svg", "#428dcc", 32),
                stat("vassoio", "Vassoi", vassoio, "vassoio.svg", "#23a69a", 32),
                stat("assente", "Assenze", assente, "assente.svg", "#ee6f49", 60)
            ];
        }

        return {
            items: items
        };
    }

    function stat(key, label, value, icon, color, max) {
        return {
            key: key,
            label: label,
            value: value,
            icon: config.mealIconBasePath + icon,
            color: color,
            max: max
        };
    }

    function normalize(response) {
        var totals = response && response.totali ? response.totali : {};
        return {
            pranzo: readStats(totals.Pranzo || {}),
            cena: readStats(totals.Cena || {})
        };
    }

    function load(callback) {
        http.getJson(buildMealsUrl(), function (error, response) {
            if (error) {
                callback(error);
                return;
            }
            callback(null, normalize(response));
        });
    }

    Bacheca.services.meals = {
        buildMealsUrl: buildMealsUrl,
        load: load,
        normalize: normalize
    };
})(window);
