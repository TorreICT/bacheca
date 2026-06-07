(function (window) {
    var Bacheca = window.Bacheca = window.Bacheca || {};
    Bacheca.components = Bacheca.components || {};

    var dom = Bacheca.utils.dom;
    var config = window.BachecaConfig;

    function setLoading() {
        var currentMount = dom.byId("weather-current");
        var forecastMount = dom.byId("weather-forecast");
        dom.clear(currentMount);
        dom.clear(forecastMount);
        currentMount.appendChild(dom.emptyState("Caricamento meteo"));
        forecastMount.appendChild(dom.emptyState("Caricamento previsioni"));
    }

    function render(data, error) {
        var currentMount = dom.byId("weather-current");
        var forecastMount = dom.byId("weather-forecast");
        var current;
        var forecast;

        dom.clear(currentMount);
        dom.clear(forecastMount);

        if (error || !data || !data.current) {
            currentMount.appendChild(dom.emptyState("Meteo non disponibile"));
            forecastMount.appendChild(dom.emptyState("Previsioni non disponibili"));
            return;
        }

        current = createCurrent(data.current);
        forecast = createForecast(data.days || []);
        currentMount.appendChild(current);
        forecastMount.appendChild(forecast);
    }

    function createCurrent(current) {
        var root = dom.create("div", "weather-current");
        var main = dom.create("div", "weather-main");
        var hero = dom.create("div", "weather-hero");
        var icon = weatherIcon(current.icon, "weather-icon-current", current.label);
        var text = dom.create("div", "weather-hero-text");
        var temp = dom.create("div", "weather-temp", formatTemperature(current.temperature));
        var condition = dom.create("div", "weather-condition", current.label);
        var location = createLocation(current.location);
        var details = dom.create("div", "weather-details");
        var uv = createUvIndicator(current);

        text.appendChild(temp);
        text.appendChild(condition);
        hero.appendChild(icon);
        hero.appendChild(text);
        main.appendChild(hero);
        if (location) {
            main.appendChild(location);
        }

        details.appendChild(detail("Percepita", formatTemperature(current.apparentTemperature)));
        details.appendChild(detail("Umidit\u00e0", formatPercent(current.humidity)));
        details.appendChild(detail("Vento", formatWind(current.windSpeed)));
        details.appendChild(detail("Pioggia", formatMillimeters(current.precipitation)));

        root.appendChild(main);
        root.appendChild(details);
        root.appendChild(uv);
        return root;
    }

    function createForecast(days) {
        var root = dom.create("div", "forecast-grid");

        if (!days.length) {
            root.appendChild(dom.emptyState("Previsioni non disponibili"));
            return root;
        }

        days.forEach(function (day) {
            root.appendChild(createForecastDay(day));
        });

        return root;
    }

    function createForecastDay(day) {
        var item = dom.create("div", "forecast-day");
        var visual = dom.create("div", "forecast-visual");
        var info = dom.create("div", "forecast-info");
        var icon = weatherIcon(day.icon, "forecast-icon", day.label);
        var date = dom.create("div", "forecast-date", formatShortDate(day.date));
        var label = dom.create("div", "forecast-label", day.label);
        var temps = dom.create("div", "forecast-temps", formatTemperature(day.minTemperature) + " / " + formatTemperature(day.maxTemperature));
        var rain = dom.create("div", "forecast-rain");
        var rainIcon = weatherIcon("rain", "forecast-rain-icon", "Pioggia");

        rain.appendChild(rainIcon);
        rain.appendChild(dom.create("strong", "", formatPercent(day.rainChance)));
        visual.appendChild(date);
        visual.appendChild(icon);
        info.appendChild(label);
        info.appendChild(temps);
        info.appendChild(rain);
        item.appendChild(visual);
        item.appendChild(info);
        return item;
    }

    function weatherIcon(iconKey, className, label) {
        var image = dom.create("img", className);
        var key = iconKey || "cloud";
        image.className = className + " weather-icon-" + key;
        image.src = config.weatherIconBasePath + key + ".svg";
        image.alt = label || "";
        return image;
    }

    function createLocation(value) {
        var text = String(value || "").replace(/\s+/g, " ").replace(/^\s+|\s+$/g, "");
        var root;
        var icon;

        if (!text) {
            return null;
        }

        root = dom.create("div", "weather-location");
        icon = dom.create("span", "weather-location-icon");
        icon.setAttribute("aria-hidden", "true");
        root.appendChild(icon);
        root.appendChild(dom.create("span", "weather-location-text", text));
        return root;
    }

    function detail(label, value) {
        var item = dom.create("div", "weather-detail");
        item.appendChild(dom.create("span", "", label));
        item.appendChild(dom.create("strong", "", value));
        return item;
    }

    function createUvIndicator(current) {
        var value = current ? current.uvIndex : null;
        var maxValue = current ? current.uvIndexMax : null;
        var colorValue = value === null || value === undefined ? maxValue : value;
        var category = uvCategory(colorValue);
        var root = dom.create("div", "weather-uv weather-uv-" + category.key);

        root.setAttribute("aria-label", "Indice UV");
        root.appendChild(dom.create("span", "weather-uv-label", "UV"));
        root.appendChild(dom.create("strong", "weather-uv-value", formatUv(value)));
        root.appendChild(dom.create("span", "weather-uv-level", category.label));
        root.appendChild(dom.create("span", "weather-uv-max", "Max oggi " + formatUv(maxValue)));
        return root;
    }

    function uvCategory(value) {
        var number = parseFloat(value);
        if (isNaN(number)) {
            return { key: "unknown", label: "N/D" };
        }
        if (number < 3) {
            return { key: "low", label: "Basso" };
        }
        if (number < 6) {
            return { key: "moderate", label: "Moderato" };
        }
        if (number < 8) {
            return { key: "high", label: "Alto" };
        }
        if (number < 11) {
            return { key: "very-high", label: "Molto alto" };
        }
        return { key: "extreme", label: "Estremo" };
    }

    function formatTemperature(value) {
        return value === null || value === undefined ? "--" : value + "\u00b0";
    }

    function formatPercent(value) {
        return value === null || value === undefined ? "--" : value + "%";
    }

    function formatWind(value) {
        return value === null || value === undefined ? "--" : value + " km/h";
    }

    function formatMillimeters(value) {
        return value === null || value === undefined ? "--" : value + " mm";
    }

    function formatUv(value) {
        var number = parseFloat(value);
        return isNaN(number) ? "--" : number.toFixed(1);
    }

    function formatShortDate(value) {
        var date = new Date(value);
        var dayNames = ["Dom", "Lun", "Mar", "Mer", "Gio", "Ven", "Sab"];

        if (isNaN(date.getTime())) {
            return "--";
        }

        return dayNames[date.getDay()] + " " + Bacheca.utils.date.pad(date.getDate());
    }

    Bacheca.components.weather = {
        setLoading: setLoading,
        render: render
    };
})(window);
