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
    var latestBirthdayNames = [];
    var latestRandomPhotoAvailable = false;
    var photoFocusMode = false;
    var randomPhotoLoading = false;
    var calendarLoading = false;
    var menuSlotMarker = null;
    var photoSlotMarker = null;
    var adaptiveDebugEnabled = false;

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
            latestBirthdayNames = [];
        }
        activeDataDate = currentDate;
        refreshMeals();
        refreshCalendar();
        refreshWeather();
        refreshBarWidget();
        refreshPizzaIndex();
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

        debugAdaptive("refreshMeals start", {});
        if (!photoFocusMode) {
            Bacheca.components.meals.setLoading();
        }

        Bacheca.services.meals.load(function (error, response) {
            if (error) {
                errors.push(error);
                debugAdaptive("stats error", { error: errorMessage(error) });
            } else {
                latestStatsData = response;
                debugAdaptive("stats loaded", {});
            }
            complete();
        });

        Bacheca.services.menu.load(function (error, response) {
            if (error) {
                errors.push(error);
                latestMenuData = menuFallbackForError();
                debugAdaptive("menu error, using fallback", { error: errorMessage(error) });
            } else {
                latestMenuData = response;
                debugAdaptive("menu loaded", menuDebugState(response));
            }
            complete();
        });

        function complete() {
            pending = pending - 1;
            if (pending > 0) {
                return;
            }
            renderMealsOrLoadPhoto(errors);
        }
    }

    function refreshMenuOnly() {
        debugAdaptive("refreshMenuOnly start", {});
        Bacheca.services.menu.load(function (error, response) {
            var errors = [];
            if (error) {
                errors.push(error);
                latestMenuData = menuFallbackForError();
                debugAdaptive("menu-only error, using fallback", { error: errorMessage(error) });
            } else {
                latestMenuData = response;
                debugAdaptive("menu-only loaded", menuDebugState(response));
            }
            renderMealsOrLoadPhoto(errors);
        });
    }

    function renderMealsOrLoadPhoto(errors) {
        latestMealErrors = errors || [];
        debugAdaptive("renderMealsOrLoadPhoto decision", {
            menusUnavailable: bothMenusUnavailable(latestMenuData),
            photoAvailable: isRandomPhotoAvailable(),
            photoLoading: randomPhotoLoading,
            calendarLoading: calendarLoading,
            errors: latestMealErrors.length
        });
        if (bothMenusUnavailable(latestMenuData) && !isRandomPhotoAvailable() && !randomPhotoLoading) {
            if (calendarLoading) {
                debugAdaptive("photo refresh waiting for calendar", {});
                return;
            }
            debugAdaptive("triggering photo refresh before swap", {});
            refreshRandomPhoto();
            return;
        }
        renderMeals(errors);
    }

    function renderMeals(errors) {
        var mealErrors = errors || latestMealErrors || [];
        debugAdaptive("renderMeals", {
            compactNoMenu: shouldUsePhotoFocusMode(),
            photoAvailable: isRandomPhotoAvailable(),
            menusUnavailable: bothMenusUnavailable(latestMenuData),
            errors: mealErrors.length
        });
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
        calendarLoading = true;
        latestBirthdayNames = [];
        Bacheca.components.birthdays.render([]);
        Bacheca.components.events.setLoading();
        Bacheca.services.events.load(function (error, calendarData) {
            var birthdayNames = calendarData && calendarData.birthdayNames ? calendarData.birthdayNames : [];
            var events = calendarData && calendarData.events ? calendarData.events : [];

            calendarLoading = false;
            latestBirthdayNames = birthdayNames;
            Bacheca.components.birthdays.render(birthdayNames);
            maxItems = birthdayNames.length ? config.maxEventsWithBirthday : config.maxEvents;
            Bacheca.components.events.render(events, error, maxItems);
            refreshRandomPhoto(birthdayNames);
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

    function refreshRandomPhoto(birthdayNames) {
        var names = birthdayNames || latestBirthdayNames || [];
        if (randomPhotoLoading) {
            debugAdaptive("photo refresh skipped, already loading", {});
            return;
        }
        randomPhotoLoading = true;
        debugAdaptive("photo refresh start", { birthdayNames: names.length });
        if (!photoFocusMode) {
            Bacheca.components.randomPhoto.setLoading();
        }
        Bacheca.services.randomPhoto.load(names, function (error, photo) {
            randomPhotoLoading = false;
            latestRandomPhotoAvailable = !error && !!(photo && photo.photos && photo.photos.length);
            debugAdaptive("photo loaded", {
                error: error ? errorMessage(error) : "",
                photos: photo && photo.photos ? photo.photos.length : 0,
                latestRandomPhotoAvailable: latestRandomPhotoAvailable
            });
            Bacheca.components.randomPhoto.render(photo, error);
            if (latestMenuData) {
                renderMeals(latestMealErrors);
            } else {
                applyAdaptiveLayout();
            }
        });
    }

    function shouldUsePhotoFocusMode() {
        return isRandomPhotoAvailable() && bothMenusUnavailable(latestMenuData);
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

    function isRandomPhotoAvailable() {
        var photoPanel;
        if (latestRandomPhotoAvailable) {
            return true;
        }
        photoPanel = document.getElementById("random-photo-panel");
        return !!(photoPanel && !hasClass(photoPanel, "is-hidden"));
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
            debugAdaptive("layout skipped, missing node", {
                dashboard: !!dashboard,
                sideStack: !!sideStack,
                mealsPanel: !!mealsPanel,
                photoPanel: !!photoPanel,
                eventsPanel: !!eventsPanel
            });
            return;
        }

        ensureLayoutMarkers(dashboard, sideStack, mealsPanel, photoPanel);
        debugAdaptive("applyAdaptiveLayout", {
            desired: desired,
            photoFocusMode: photoFocusMode,
            dashboardClass: dashboard.className,
            photoParent: parentDebugName(photoPanel),
            mealsParent: parentDebugName(mealsPanel),
            photoHidden: hasClass(photoPanel, "is-hidden"),
            menuSlotParent: parentDebugName(menuSlotMarker),
            photoSlotParent: parentDebugName(photoSlotMarker)
        });

        if (desired) {
            moveAfterMarker(photoPanel, menuSlotMarker);
            moveAfterMarker(mealsPanel, photoSlotMarker);
            addClass(dashboard, "menu-photo-mode");
            photoFocusMode = true;
            debugAdaptive("swap enabled", {
                photoParent: parentDebugName(photoPanel),
                mealsParent: parentDebugName(mealsPanel),
                dashboardClass: dashboard.className
            });
            return;
        }

        removeClass(dashboard, "menu-photo-mode");
        moveAfterMarker(photoPanel, photoSlotMarker);
        moveAfterMarker(mealsPanel, menuSlotMarker);
        photoFocusMode = false;
        debugAdaptive("swap disabled", {
            photoParent: parentDebugName(photoPanel),
            mealsParent: parentDebugName(mealsPanel),
            dashboardClass: dashboard.className
        });
    }

    function ensureLayoutMarkers(dashboard, sideStack, mealsPanel, photoPanel) {
        if (!menuSlotMarker && mealsPanel && mealsPanel.parentNode) {
            menuSlotMarker = document.createComment("bacheca-menu-slot");
            mealsPanel.parentNode.insertBefore(menuSlotMarker, mealsPanel);
        }
        if (!photoSlotMarker && photoPanel && photoPanel.parentNode) {
            photoSlotMarker = document.createComment("bacheca-photo-slot");
            photoPanel.parentNode.insertBefore(photoSlotMarker, photoPanel);
        }
        if (menuSlotMarker && !menuSlotMarker.parentNode && dashboard) {
            dashboard.appendChild(menuSlotMarker);
        }
        if (photoSlotMarker && !photoSlotMarker.parentNode && sideStack) {
            sideStack.insertBefore(photoSlotMarker, sideStack.firstChild);
        }
    }

    function moveAfterMarker(element, marker) {
        var parent = marker && marker.parentNode;
        var next = marker ? marker.nextSibling : null;
        if (!element || !parent || next === element) {
            debugAdaptive("move skipped", {
                element: element ? element.id || element.className || element.nodeName : "",
                parent: parentDebugName(parent),
                nextIsElement: next === element
            });
            return;
        }
        parent.insertBefore(element, next);
        debugAdaptive("move executed", {
            element: element.id || element.className || element.nodeName,
            parent: parentDebugName(parent)
        });
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

    function hasClass(element, className) {
        if (Bacheca.utils.dom && Bacheca.utils.dom.hasClass) {
            return Bacheca.utils.dom.hasClass(element, className);
        }
        return element && (" " + element.className + " ").indexOf(" " + className + " ") !== -1;
    }

    function debugAdaptive(message, detail) {
        if (!adaptiveDebugEnabled || !window.console || !window.console.log) {
            return;
        }
        window.console.log("[Bacheca adaptive] " + message, detail || {});
    }

    function menuDebugState(menu) {
        return {
            hasMenu: !!menu,
            pranzoAvailable: !!(menu && menu.pranzo && menu.pranzo.available),
            cenaAvailable: !!(menu && menu.cena && menu.cena.available),
            pranzoSections: menu && menu.pranzo && menu.pranzo.sections ? menu.pranzo.sections.length : 0,
            cenaSections: menu && menu.cena && menu.cena.sections ? menu.cena.sections.length : 0
        };
    }

    function parentDebugName(node) {
        var parent = node && node.parentNode ? node.parentNode : node;
        if (!parent) {
            return "";
        }
        if (parent.id) {
            return "#" + parent.id;
        }
        if (parent.className) {
            return "." + parent.className;
        }
        return parent.nodeName || "";
    }

    function errorMessage(error) {
        return error && error.message ? error.message : String(error || "");
    }

    Bacheca.app = {
        init: init,
        refreshAll: refreshAll
    };
})(window);
