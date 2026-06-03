(function (window) {
    var Bacheca = window.Bacheca = window.Bacheca || {};
    Bacheca.components = Bacheca.components || {};

    var dom = Bacheca.utils.dom;
    var countdownTimer = null;
    var marqueeItems = [];
    var resizeAttached = false;
    var resizeTimer = null;

    function setLoading() {
        render(null, null);
    }

    function render(data, error) {
        var panel = dom.byId("bar-widget-panel");
        var content = dom.byId("bar-widget-content");
        var dashboard = dom.byId("dashboard");
        var hasContent;

        clearCountdownTimer();
        marqueeItems = [];
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
        attachResizeHandler();
        window.setTimeout(recalculateMarquees, 0);
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
        var viewport = dom.create("div", "bar-widget-marquee");
        var track = dom.create("div", "bar-widget-marquee-track");
        var primary = dom.create("span", "bar-widget-marquee-text", announcement.text);
        var spacer = dom.create("span", "bar-widget-marquee-spacer", "\u00a0\u00a0\u2022\u00a0\u00a0");
        var clone = dom.create("span", "bar-widget-marquee-text bar-widget-marquee-clone", announcement.text);

        track.appendChild(primary);
        track.appendChild(spacer);
        track.appendChild(clone);
        viewport.appendChild(track);
        item.appendChild(dom.create("span", "bar-widget-label", "Avviso"));
        item.appendChild(viewport);

        marqueeItems.push({
            viewport: viewport,
            track: track,
            primary: primary
        });

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
        var header = dom.create("div", "bar-widget-soccer-header");
        var body = dom.create("div", "bar-widget-soccer-body");
        var results = arrayOrEmpty(soccer.results);
        var fixtures = arrayOrEmpty(soccer.fixtures);

        header.appendChild(dom.create("span", "bar-widget-label", "Calcio"));
        header.appendChild(dom.create("strong", "bar-widget-soccer-title", soccer.label || soccer.competition || ""));
        item.appendChild(header);

        if (!soccer.available) {
            body.appendChild(dom.create("div", "bar-widget-soccer-message", soccer.message || "Calcio non disponibile"));
            item.appendChild(body);
            return item;
        }

        if (!results.length && !fixtures.length) {
            body.appendChild(createSoccerFallback(soccer));
            item.appendChild(body);
            return item;
        }

        body.appendChild(createSoccerGroup("Ultime", results, "Nessun risultato"));
        body.appendChild(createSoccerGroup("Prossime", fixtures, "Nessuna partita"));
        item.appendChild(body);
        return item;
    }

    function createSoccerGroup(title, matches, emptyText) {
        var group = dom.create("div", "bar-widget-soccer-group");
        var label = dom.create("span", "bar-widget-soccer-group-label", title);
        var rows = dom.create("div", "bar-widget-soccer-rows");
        var i;

        group.appendChild(label);

        if (!matches.length) {
            rows.appendChild(dom.create("div", "bar-widget-soccer-empty", emptyText));
        } else {
            for (i = 0; i < matches.length; i++) {
                rows.appendChild(createSoccerMatch(matches[i]));
            }
        }

        group.appendChild(rows);
        return group;
    }

    function createSoccerMatch(match) {
        var row = dom.create("div", "bar-widget-soccer-match");
        row.appendChild(dom.create("span", "bar-widget-soccer-date", match.dateLabel || "--"));
        row.appendChild(createSoccerTeam(match.home));
        row.appendChild(dom.create("strong", "bar-widget-soccer-score", soccerScore(match)));
        row.appendChild(createSoccerTeam(match.away));
        return row;
    }

    function createSoccerTeam(team) {
        var data = team || {};
        var root = dom.create("span", "bar-widget-soccer-team");
        var abbr = dom.create("span", "bar-widget-soccer-abbr", data.abbr || shortName(data.shortName || data.name));
        var image;

        if (data.badgeUrl) {
            image = dom.create("img", "bar-widget-soccer-badge");
            image.src = data.badgeUrl;
            image.alt = data.abbr || "";
            image.onerror = function () {
                this.style.display = "none";
            };
            root.appendChild(image);
        }

        root.appendChild(abbr);
        root.title = data.name || data.shortName || data.abbr || "";
        return root;
    }

    function soccerScore(match) {
        if (match && match.score) {
            return String(match.score.home) + "-" + String(match.score.away);
        }
        return "vs";
    }

    function createSoccerFallback(soccer) {
        return dom.create("div", "bar-widget-soccer-message", soccerText(soccer));
    }

    function soccerText(soccer) {
        var items = soccer.items || [];
        var parts = [];
        var i;

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

    function attachResizeHandler() {
        if (resizeAttached) {
            return;
        }
        resizeAttached = true;
        window.onresize = wrapResize(window.onresize);
    }

    function wrapResize(previous) {
        return function () {
            if (typeof previous === "function") {
                previous();
            }
            if (resizeTimer) {
                window.clearTimeout(resizeTimer);
            }
            resizeTimer = window.setTimeout(recalculateMarquees, 180);
        };
    }

    function recalculateMarquees() {
        var i;
        for (i = 0; i < marqueeItems.length; i++) {
            adjustMarquee(marqueeItems[i]);
        }
    }

    function adjustMarquee(item) {
        var maxFont = 28;
        var minFont = 18;
        var size = maxFont;
        var viewportWidth;
        var textWidth;
        var duration;

        if (!item || !item.viewport || !item.track || !item.primary) {
            return;
        }

        dom.removeClass(item.viewport, "is-scrolling");
        item.track.style.animationDuration = "";
        item.track.style.fontSize = maxFont + "px";
        viewportWidth = item.viewport.clientWidth;

        while (size > minFont && item.primary.scrollWidth > viewportWidth) {
            size = size - 1;
            item.track.style.fontSize = size + "px";
        }

        textWidth = item.primary.scrollWidth;
        if (textWidth > viewportWidth) {
            duration = Math.max(22, Math.min(90, Math.ceil(textWidth / 18)));
            item.track.style.animationDuration = duration + "s";
            dom.addClass(item.viewport, "is-scrolling");
        }
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

    function shortName(value) {
        var text = String(value || "").replace(/\s+/g, "");
        if (!text) {
            return "---";
        }
        return text.substring(0, 3).toUpperCase();
    }

    function arrayOrEmpty(value) {
        if (Object.prototype.toString.call(value) === "[object Array]") {
            return value;
        }
        return [];
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
