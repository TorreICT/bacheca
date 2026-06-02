(function (window) {
    var Bacheca = window.Bacheca = window.Bacheca || {};
    Bacheca.services = Bacheca.services || {};

    var config = window.BachecaConfig;
    var http = Bacheca.utils.http;
    var dateUtils = Bacheca.utils.date;

    function buildCalendarUrl() {
        return (config.api && config.api.calendar) || "/api/calendar";
    }

    function trim(value) {
        return String(value || "").replace(/^\s+|\s+$/g, "");
    }

    function birthdayName(event) {
        var summary = event && event.summary ? String(event.summary) : "";
        var match = /^\s*Compleanno\s+di\s+(.+?)\s*$/i.exec(summary);
        if (!match) {
            return "";
        }
        return trim(match[1]);
    }

    function sameLocalDay(left, right) {
        return left.getFullYear() === right.getFullYear() &&
            left.getMonth() === right.getMonth() &&
            left.getDate() === right.getDate();
    }

    function normalizeEvent(event) {
        var start = dateUtils.parseCalendarStart(event);
        var day;

        if (!start || isNaN(start.date.getTime())) {
            return null;
        }

        day = dateUtils.formatEventDay(start.date);

        return {
            title: event.summary || "Evento",
            location: event.location || "",
            description: event.description || "",
            date: start.date,
            allDay: start.allDay,
            dayName: day.dayName,
            dayNumber: day.dayNumber,
            timeLabel: dateUtils.formatEventTime(start.date, start.allDay)
        };
    }

    function normalize(response) {
        var rawEvents = response && response.events ? response.events : [];
        var events = [];
        var birthdayNames = [];
        var today = new Date();

        if (!rawEvents.length) {
            return {
                events: [],
                birthdayNames: []
            };
        }

        rawEvents.forEach(function (event) {
            var normalized;
            var start = dateUtils.parseCalendarStart(event);
            var name = birthdayName(event);

            if (name) {
                if (start && !isNaN(start.date.getTime()) && sameLocalDay(start.date, today)) {
                    birthdayNames.push(name);
                }
                return;
            }

            normalized = normalizeEvent(event);
            if (normalized) {
                events.push(normalized);
            }
        });

        events.sort(function (left, right) {
            return left.date.getTime() - right.date.getTime();
        });

        return {
            events: events,
            birthdayNames: birthdayNames
        };
    }

    function load(callback) {
        http.getJson(buildCalendarUrl(), function (error, response) {
            if (error) {
                callback(error);
                return;
            }
            callback(null, normalize(response));
        });
    }

    Bacheca.services.events = {
        buildCalendarUrl: buildCalendarUrl,
        load: load,
        normalize: normalize,
        birthdayName: birthdayName
    };
})(window);
