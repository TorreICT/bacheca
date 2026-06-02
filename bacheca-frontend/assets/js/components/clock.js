(function (window) {
    var Bacheca = window.Bacheca = window.Bacheca || {};
    Bacheca.components = Bacheca.components || {};

    var dom = Bacheca.utils.dom;
    var dateUtils = Bacheca.utils.date;
    var timer = null;

    function renderClock() {
        var now = new Date();
        dom.setText(dom.byId("clock-time"), dateUtils.formatTime(now));
        dom.setText(dom.byId("clock-seconds"), dateUtils.formatSeconds(now));
        dom.setText(dom.byId("clock-date"), dateUtils.formatDate(now));
    }

    function setLastUpdated(date) {
        var updatedAt = date || new Date();
        dom.setText(dom.byId("last-updated"), "Aggiornato alle " + dateUtils.formatTime(updatedAt));
    }

    function init() {
        renderClock();
        setLastUpdated();
        if (timer) {
            window.clearInterval(timer);
        }
        timer = window.setInterval(renderClock, 1000);
    }

    Bacheca.components.clock = {
        init: init,
        setLastUpdated: setLastUpdated
    };
})(window);
