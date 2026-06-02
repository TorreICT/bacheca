(function (window) {
    var Bacheca = window.Bacheca = window.Bacheca || {};
    Bacheca.utils = Bacheca.utils || {};

    var dayNames = ["Dom", "Lun", "Mar", "Mer", "Gio", "Ven", "Sab"];
    var monthNames = ["Gen", "Feb", "Mar", "Apr", "Mag", "Giu", "Lug", "Ago", "Set", "Ott", "Nov", "Dic"];

    function pad(value) {
        value = parseInt(value, 10);
        return value < 10 ? "0" + value : "" + value;
    }

    function formatTime(date) {
        return pad(date.getHours()) + ":" + pad(date.getMinutes());
    }

    function formatSeconds(date) {
        return pad(date.getSeconds());
    }

    function formatDate(date) {
        return dayNames[date.getDay()] + " " + pad(date.getDate()) + " " + monthNames[date.getMonth()] + " " + date.getFullYear();
    }

    function formatIsoDate(date) {
        return date.getFullYear() + "-" + pad(date.getMonth() + 1) + "-" + pad(date.getDate());
    }

    function parseLocalDate(value) {
        var parts = String(value).split("-");
        if (parts.length !== 3) {
            return new Date(value);
        }
        return new Date(parseInt(parts[0], 10), parseInt(parts[1], 10) - 1, parseInt(parts[2], 10));
    }

    function parseCalendarStart(event) {
        if (!event || !event.start) {
            return null;
        }

        if (event.start.dateTime) {
            return {
                date: new Date(String(event.start.dateTime).replace(" ", "+")),
                allDay: false
            };
        }

        if (event.start.date) {
            return {
                date: parseLocalDate(event.start.date),
                allDay: true
            };
        }

        return null;
    }

    function formatEventTime(date, allDay) {
        if (allDay) {
            return "Tutto il giorno";
        }
        return "Orario: " + formatTime(date);
    }

    function formatEventDay(date) {
        return {
            dayName: dayNames[date.getDay()],
            dayNumber: pad(date.getDate())
        };
    }

    Bacheca.utils.date = {
        pad: pad,
        formatTime: formatTime,
        formatSeconds: formatSeconds,
        formatDate: formatDate,
        formatIsoDate: formatIsoDate,
        parseCalendarStart: parseCalendarStart,
        formatEventTime: formatEventTime,
        formatEventDay: formatEventDay
    };
})(window);
