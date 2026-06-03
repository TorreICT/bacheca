(function (window) {
    var Bacheca = window.Bacheca = window.Bacheca || {};
    Bacheca.components = Bacheca.components || {};

    var dom = Bacheca.utils.dom;
    var countdownTimer = null;

    function setLoading() {
        render(null, null);
    }

    function render(data, error) {
        var panel = dom.byId("bar-widget-panel");
        var content = dom.byId("bar-widget-content");
        var dashboard = dom.byId("dashboard");
        var hasContent;

        clearCountdownTimer();
        if (!panel || !content) {
            return;
        }

        dom.clear(content);

        if (error || !data || !data.visible) {
            hide(panel, dashboard);
            return;
        }

        panel.style.backgroundColor = safeColor(data.color);
        hasContent = appendContent(content, data);

        if (!hasContent) {
            content.appendChild(dom.create("div", "bar-widget-empty", "Bacheca aggiornata"));
        }

        dom.removeClass(panel, "is-hidden");
        if (dashboard) {
            dom.addClass(dashboard, "has-bar-widget");
        }
    }

    function hide(panel, dashboard) {
        dom.addClass(panel, "is-hidden");
        if (dashboard) {
            dom.removeClass(dashboard, "has-bar-widget");
        }
    }

    function appendContent(content, data) {
        var hasContent = false;

        if (data.announcement && data.announcement.text) {
            content.appendChild(createAnnouncement(data.announcement));
            hasContent = true;
        }

        if (data.countdown && data.countdown.to) {
            content.appendChild(createCountdown(data.countdown));
            hasContent = true;
        }

        if (data.soccer && data.soccer.enabled) {
            content.appendChild(createSoccer(data.soccer));
            hasContent = true;
        }

        return hasContent;
    }

    function createAnnouncement(announcement) {
        var item = dom.create("div", "bar-widget-announcement");
        item.appendChild(dom.create("span", "bar-widget-label", "Avviso"));
        item.appendChild(dom.create("strong", "bar-widget-text", announcement.text));
        return item;
    }

    function createCountdown(countdown) {
        var item = dom.create("div", "bar-widget-countdown");
        var label = dom.create("span", "bar-widget-label", countdown.label || "Manca");
        var value = dom.create("strong", "bar-widget-countdown-value", "--");
        item.appendChild(label);
        item.appendChild(value);
        startCountdown(value, countdown.to);
        return item;
    }

    function createSoccer(soccer) {
        var item = dom.create("div", "bar-widget-soccer");
        var label = dom.create("span", "bar-widget-label", soccer.label || soccer.competition || "Calcio");
        var text = soccerText(soccer);
        item.appendChild(label);
        item.appendChild(dom.create("strong", "bar-widget-text", text));
        return item;
    }

    function soccerText(soccer) {
        var items = soccer.items || [];
        var parts = [];
        var i;

        if (!soccer.available) {
            return soccer.message || "Calcio non disponibile";
        }

        for (i = 0; i < items.length; i++) {
            if (items[i] && items[i].text) {
                parts.push(items[i].text);
            }
        }

        if (!parts.length) {
            return soccer.message || "Nessuna partita in evidenza";
        }

        return parts.join("  |  ");
    }

    function startCountdown(element, targetText) {
        var target = new Date(targetText);
        if (isNaN(target.getTime())) {
            dom.setText(element, "--");
            return;
        }

        function tick() {
            var remaining = target.getTime() - new Date().getTime();
            if (remaining <= 0) {
                dom.setText(element, "Concluso");
                clearCountdownTimer();
                return;
            }
            dom.setText(element, formatRemaining(remaining));
        }

        tick();
        countdownTimer = window.setInterval(tick, 1000);
    }

    function clearCountdownTimer() {
        if (countdownTimer) {
            window.clearInterval(countdownTimer);
            countdownTimer = null;
        }
    }

    function formatRemaining(ms) {
        var totalSeconds = Math.floor(ms / 1000);
        var days = Math.floor(totalSeconds / 86400);
        var hours = Math.floor((totalSeconds % 86400) / 3600);
        var minutes = Math.floor((totalSeconds % 3600) / 60);
        var seconds = totalSeconds % 60;

        if (days > 0) {
            return days + "g " + pad(hours) + ":" + pad(minutes) + ":" + pad(seconds);
        }
        return pad(hours) + ":" + pad(minutes) + ":" + pad(seconds);
    }

    function pad(value) {
        value = parseInt(value, 10);
        return value < 10 ? "0" + value : "" + value;
    }

    function safeColor(value) {
        var text = String(value || "").replace(/^\s+|\s+$/g, "");
        if (/^#[0-9A-Fa-f]{6}$/.test(text)) {
            return text;
        }
        return "#1565C0";
    }

    Bacheca.components.barWidget = {
        setLoading: setLoading,
        render: render
    };
})(window);
