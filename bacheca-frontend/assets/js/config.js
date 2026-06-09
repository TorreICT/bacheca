(function (window) {
    window.BachecaConfig = {
        api: {
            meals: "/api/pasti",
            menu: "/api/menu",
            calendar: "/api/calendar",
            pizzaIndex: "/api/pizza-index",
            randomPhoto: "/api/random-photo",
            barWidget: "/api/bar-widget",
            weather: "/api/weather"
        },
        refreshMs: 15 * 60 * 1000,
        menuRefreshMs: 60 * 1000,
        barWidgetRefreshMs: 12 * 1000,
        pizzaIndexRefreshMs: 30 * 1000,
        requestTimeoutMs: 8000,
        maxEvents: 5,
        maxEventsWithBirthday: 3,
        mealIconBasePath: "assets/img/pasti/",
        birthdayIconPath: "assets/img/birthday.svg",
        logoPath: "assets/img/torrescalla-mark.svg",
        weatherIconBasePath: "assets/img/weather/",
        weather: {
            providerUrl: "/api/weather",
            latitude: 45.478,
            longitude: 9.229,
            timezone: "Europe/Rome",
            forecastDays: 5,
            current: [
                "temperature_2m",
                "relative_humidity_2m",
                "apparent_temperature",
                "precipitation",
                "weather_code",
                "uv_index",
                "wind_speed_10m"
            ],
            daily: [
                "weather_code",
                "temperature_2m_max",
                "temperature_2m_min",
                "uv_index_max",
                "precipitation_probability_max"
            ]
        }
    };
})(window);
