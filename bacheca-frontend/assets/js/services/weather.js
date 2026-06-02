(function (window) {
    var Bacheca = window.Bacheca = window.Bacheca || {};
    Bacheca.services = Bacheca.services || {};

    var config = window.BachecaConfig;
    var http = Bacheca.utils.http;
    var dateUtils = Bacheca.utils.date;
    var weatherConfig = config.weather;
    var weatherTypes = {
        0: { label: "Sereno", icon: "sun" },
        1: { label: "Preval. sereno", icon: "partly-cloudy" },
        2: { label: "Parzialmente nuvoloso", icon: "partly-cloudy" },
        3: { label: "Nuvoloso", icon: "cloud" },
        45: { label: "Nebbia", icon: "fog" },
        48: { label: "Nebbia", icon: "fog" },
        51: { label: "Pioviggine", icon: "rain" },
        53: { label: "Pioviggine", icon: "rain" },
        55: { label: "Pioviggine intensa", icon: "rain" },
        56: { label: "Pioviggine gelata", icon: "rain" },
        57: { label: "Pioviggine gelata", icon: "rain" },
        61: { label: "Pioggia leggera", icon: "rain" },
        63: { label: "Pioggia", icon: "rain" },
        65: { label: "Pioggia intensa", icon: "rain" },
        66: { label: "Pioggia gelata", icon: "rain" },
        67: { label: "Pioggia gelata", icon: "rain" },
        71: { label: "Neve leggera", icon: "snow" },
        73: { label: "Neve", icon: "snow" },
        75: { label: "Neve intensa", icon: "snow" },
        77: { label: "Neve", icon: "snow" },
        80: { label: "Rovesci leggeri", icon: "showers" },
        81: { label: "Rovesci", icon: "showers" },
        82: { label: "Rovesci intensi", icon: "showers" },
        85: { label: "Neve", icon: "snow" },
        86: { label: "Neve intensa", icon: "snow" },
        95: { label: "Temporale", icon: "storm" },
        96: { label: "Temporale con grandine", icon: "storm" },
        99: { label: "Temporale con grandine", icon: "storm" }
    };

    function addDays(date, amount) {
        var copy = new Date(date.getTime());
        copy.setDate(copy.getDate() + amount);
        return copy;
    }

    function buildUrl(date) {
        var startDate = date || new Date();
        var endDate = addDays(startDate, Math.max(parseInt(weatherConfig.forecastDays, 10) || 5, 1) - 1);
        var params = [
            ["latitude", weatherConfig.latitude],
            ["longitude", weatherConfig.longitude],
            ["timezone", weatherConfig.timezone],
            ["start_date", dateUtils.formatIsoDate(startDate)],
            ["end_date", dateUtils.formatIsoDate(endDate)],
            ["current", weatherConfig.current.join(",")],
            ["daily", weatherConfig.daily.join(",")]
        ];
        var query = [];
        var i;

        for (i = 0; i < params.length; i++) {
            query.push(encodeURIComponent(params[i][0]) + "=" + encodeURIComponent(params[i][1]));
        }

        return weatherConfig.providerUrl + "?" + query.join("&");
    }

    function round(value) {
        var number = parseFloat(value);
        if (isNaN(number)) {
            return null;
        }
        return Math.round(number);
    }

    function labelFor(code) {
        var parsed = parseInt(code, 10);
        return weatherTypes[parsed] ? weatherTypes[parsed].label : "Meteo variabile";
    }

    function iconFor(code) {
        var parsed = parseInt(code, 10);
        return weatherTypes[parsed] ? weatherTypes[parsed].icon : "cloud";
    }

    function normalize(response) {
        var current = response && response.current ? response.current : null;
        var daily = response && response.daily ? response.daily : null;
        var days = [];
        var i;
        var dayCount;

        if (!current || !daily || !daily.time || !daily.time.length) {
            return null;
        }

        dayCount = Math.min(daily.time.length, weatherConfig.forecastDays);
        for (i = 0; i < dayCount; i++) {
            days.push({
                date: daily.time[i],
                label: labelFor(daily.weather_code && daily.weather_code[i]),
                icon: iconFor(daily.weather_code && daily.weather_code[i]),
                maxTemperature: round(daily.temperature_2m_max && daily.temperature_2m_max[i]),
                minTemperature: round(daily.temperature_2m_min && daily.temperature_2m_min[i]),
                rainChance: round(daily.precipitation_probability_max && daily.precipitation_probability_max[i])
            });
        }

        return {
            current: {
                temperature: round(current.temperature_2m),
                apparentTemperature: round(current.apparent_temperature),
                humidity: round(current.relative_humidity_2m),
                precipitation: current.precipitation === undefined || current.precipitation === null ? null : current.precipitation,
                windSpeed: round(current.wind_speed_10m),
                code: current.weather_code,
                label: labelFor(current.weather_code),
                icon: iconFor(current.weather_code)
            },
            days: days
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
                callback(new Error("Malformed weather response"));
                return;
            }

            callback(null, normalized);
        });
    }

    Bacheca.services.weather = {
        buildUrl: buildUrl,
        iconFor: iconFor,
        labelFor: labelFor,
        load: load,
        normalize: normalize
    };
})(window);
