(function (window) {
    var Bacheca = window.Bacheca = window.Bacheca || {};
    var config = window.BachecaConfig;
    var refreshTimer = null;
    var dateCheckTimer = null;
    var activeDataDate = null;

    function init() {
        Bacheca.components.clock.init();
        refreshAll();
        startDateWatcher();

        if (refreshTimer) {
            window.clearInterval(refreshTimer);
        }
        refreshTimer = window.setInterval(refreshAll, config.refreshMs);
    }

    function refreshAll() {
        activeDataDate = Bacheca.utils.date.formatIsoDate(new Date());
        refreshMeals();
        refreshCalendar();
        refreshWeather();
        refreshPizzaIndex();
        refreshRandomPhoto();
        Bacheca.components.clock.setLastUpdated();
    }

    function startDateWatcher() {
        if (dateCheckTimer) {
            window.clearInterval(dateCheckTimer);
        }

        dateCheckTimer = window.setInterval(function () {
            var currentDate = Bacheca.utils.date.formatIsoDate(new Date());
            if (activeDataDate && currentDate !== activeDataDate) {
                refreshAll();
            }
        }, 5000);
    }

    function refreshMeals() {
        var pending = 2;
        var statsData = null;
        var menuData = null;
        var errors = [];

        Bacheca.components.meals.setLoading();

        Bacheca.services.meals.load(function (error, response) {
            if (error) {
                errors.push(error);
            } else {
                statsData = response;
            }
            complete();
        });

        Bacheca.services.menu.load(function (error, response) {
            if (error) {
                errors.push(error);
            } else {
                menuData = response;
            }
            complete();
        });

        function complete() {
            pending = pending - 1;
            if (pending > 0) {
                return;
            }
            Bacheca.components.meals.render({
                stats: statsData,
                menu: menuData,
                errors: errors
            });
        }
    }

    function refreshCalendar() {
        var maxItems;
        Bacheca.components.birthdays.render([]);
        Bacheca.components.events.setLoading();
        Bacheca.services.events.load(function (error, calendarData) {
            var birthdayNames = calendarData && calendarData.birthdayNames ? calendarData.birthdayNames : [];
            var events = calendarData && calendarData.events ? calendarData.events : [];

            Bacheca.components.birthdays.render(birthdayNames);
            maxItems = birthdayNames.length ? config.maxEventsWithBirthday : config.maxEvents;
            Bacheca.components.events.render(events, error, maxItems);
        });
    }

    function refreshWeather() {
        Bacheca.components.weather.setLoading();
        Bacheca.services.weather.load(function (error, weather) {
            Bacheca.components.weather.render(weather, error);
        });
    }

    function refreshPizzaIndex() {
        Bacheca.components.pizzaIndex.setLoading();
        Bacheca.services.pizzaIndex.load(function (error, pizzaIndex) {
            Bacheca.components.pizzaIndex.render(pizzaIndex, error);
        });
    }

    function refreshRandomPhoto() {
        Bacheca.components.randomPhoto.setLoading();
        Bacheca.services.randomPhoto.load(function (error, photo) {
            Bacheca.components.randomPhoto.render(photo, error);
        });
    }

    Bacheca.app = {
        init: init,
        refreshAll: refreshAll
    };
})(window);
