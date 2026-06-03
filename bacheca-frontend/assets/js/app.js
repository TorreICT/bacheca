(function (window) {
    var Bacheca = window.Bacheca = window.Bacheca || {};
    var config = window.BachecaConfig;
    var refreshTimer = null;
    var menuTimer = null;
    var barWidgetTimer = null;
    var pizzaIndexTimer = null;
    var dateCheckTimer = null;
    var activeDataDate = null;
    var latestStatsData = null;
    var latestMenuData = null;
    var latestMealErrors = [];
    var latestRandomPhotoAvailable = false;
    var photoFocusMode = false;

    function init() {
        Bacheca.components.clock.init();
        refreshAll();
        startMenuPoller();
        startBarWidgetPoller();
        startPizzaIndexPoller();
        startDateWatcher();

        if (refreshTimer) {
            window.clearInterval(refreshTimer);
        }
        refreshTimer = window.setInterval(refreshAll, config.refreshMs);
    }

    function refreshAll() {
        var currentDate = Bacheca.utils.date.formatIsoDate(new Date());
        if (activeDataDate && currentDate !== activeDataDate) {
            latestMenuData = null;
            latestMealErrors = [];
        }
        activeDataDate = currentDate;
        refreshMeals();
        refreshCalendar();
        refreshWeather();
        refreshBarWidget();
        refreshPizzaIndex();
        refreshRandomPhoto();
        Bacheca.components.clock.setLastUpdated();
    }

    function startMenuPoller() {
        if (menuTimer) {
            window.clearInterval(menuTimer);
        }
        menuTimer = window.setInterval(refreshMenuOnly, config.menuRefreshMs || 60000);
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

    function startBarWidgetPoller() {
        if (barWidgetTimer) {
            window.clearInterval(barWidgetTimer);
        }
        barWidgetTimer = window.setInterval(refreshBarWidget, config.barWidgetRefreshMs || 12000);
    }

    function startPizzaIndexPoller() {
        if (pizzaIndexTimer) {
            window.clearInterval(pizzaIndexTimer);
        }
        pizzaIndexTimer = window.setInterval(function () {
            refreshPizzaIndex(false);
        }, config.pizzaIndexRefreshMs || 30000);
    }

    function refreshMeals() {
        var pending = 2;
        var errors = [];

        if (!photoFocusMode) {
            Bacheca.components.meals.setLoading();
        }

        Bacheca.services.meals.load(function (error, response) {
            if (error) {
                errors.push(error);
            } else {
                latestStatsData = response;
            }
            complete();
        });

        Bacheca.services.menu.load(function (error, response) {
            if (error) {
                errors.push(error);
                latestMenuData = menuFallbackForError();
            } else {
                latestMenuData = response;
            }
            complete();
        });

        function complete() {
            pending = pending - 1;
            if (pending > 0) {
                return;
            }
            latestMealErrors = errors;
            renderMeals(errors);
        }
    }

    function refreshMenuOnly() {
        Bacheca.services.menu.load(function (error, response) {
            var errors = [];
            if (error) {
                errors.push(error);
                latestMenuData = menuFallbackForError();
            } else {
                latestMenuData = response;
            }
            latestMealErrors = errors;
            renderMeals(errors);
        });
    }

    function renderMeals(errors) {
        var mealErrors = errors || latestMealErrors || [];
        Bacheca.components.meals.render({
            stats: latestStatsData,
            menu: latestMenuData,
            errors: mealErrors,
            compactNoMenu: shouldUsePhotoFocusMode()
        });
        applyAdaptiveLayout();
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

    function refreshBarWidget() {
        if (!Bacheca.services.barWidget || !Bacheca.components.barWidget) {
            return;
        }
        Bacheca.services.barWidget.load(function (error, data) {
            Bacheca.components.barWidget.render(data, error);
        });
    }

    function refreshPizzaIndex(showLoading) {
        if (showLoading !== false) {
            Bacheca.components.pizzaIndex.setLoading();
        }
        Bacheca.services.pizzaIndex.load(function (error, pizzaIndex) {
            Bacheca.components.pizzaIndex.render(pizzaIndex, error);
        });
    }

    function refreshRandomPhoto() {
        if (!photoFocusMode) {
            Bacheca.components.randomPhoto.setLoading();
        }
        Bacheca.services.randomPhoto.load(function (error, photo) {
            latestRandomPhotoAvailable = !error && !!(photo && photo.photos && photo.photos.length);
            Bacheca.components.randomPhoto.render(photo, error);
            if (latestMenuData) {
                renderMeals(latestMealErrors);
            } else {
                applyAdaptiveLayout();
            }
        });
    }

    function shouldUsePhotoFocusMode() {
        return latestRandomPhotoAvailable && bothMenusUnavailable(latestMenuData);
    }

    function bothMenusUnavailable(menu) {
        if (!menu) {
            return false;
        }
        return !anyMenuAvailable(menu);
    }

    function anyMenuAvailable(menu) {
        return !!(menu && (mealMenuAvailable(menu.pranzo) || mealMenuAvailable(menu.cena)));
    }

    function mealMenuAvailable(meal) {
        return !!(meal && meal.available);
    }

    function menuFallbackForError() {
        if (anyMenuAvailable(latestMenuData)) {
            return latestMenuData;
        }
        return emptyMenuData();
    }

    function emptyMenuData() {
        return {
            pranzo: {
                available: false,
                sections: []
            },
            cena: {
                available: false,
                sections: []
            }
        };
    }

    function applyAdaptiveLayout() {
        var dashboard = document.getElementById("dashboard");
        var sideStack = document.querySelector ? document.querySelector(".side-stack") : null;
        var mealsPanel = document.getElementById("meals-panel");
        var photoPanel = document.getElementById("random-photo-panel");
        var eventsPanel = document.querySelector ? document.querySelector(".events-panel") : null;
        var desired = shouldUsePhotoFocusMode();

        if (!dashboard || !sideStack || !mealsPanel || !photoPanel || !eventsPanel) {
            return;
        }

        if (desired) {
            if (photoPanel.parentNode !== dashboard) {
                dashboard.appendChild(photoPanel);
            }
            if (mealsPanel.parentNode !== sideStack) {
                sideStack.insertBefore(mealsPanel, eventsPanel);
            }
            addClass(dashboard, "menu-photo-mode");
            photoFocusMode = true;
            return;
        }

        removeClass(dashboard, "menu-photo-mode");
        if (photoPanel.parentNode !== sideStack) {
            sideStack.insertBefore(photoPanel, eventsPanel);
        }
        if (mealsPanel.parentNode !== dashboard) {
            dashboard.appendChild(mealsPanel);
        }
        photoFocusMode = false;
    }

    function addClass(element, className) {
        if (Bacheca.utils.dom && Bacheca.utils.dom.addClass) {
            Bacheca.utils.dom.addClass(element, className);
        }
    }

    function removeClass(element, className) {
        if (Bacheca.utils.dom && Bacheca.utils.dom.removeClass) {
            Bacheca.utils.dom.removeClass(element, className);
        }
    }

    Bacheca.app = {
        init: init,
        refreshAll: refreshAll
    };
})(window);
