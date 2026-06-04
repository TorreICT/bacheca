(function (window) {
    var Bacheca = window.Bacheca = window.Bacheca || {};
    Bacheca.components = Bacheca.components || {};

    var dom = Bacheca.utils.dom;
    var countdownTimer = null;
    var slideTimer = null;
    var resizeTimer = null;
    var resizeAttached = false;
    var slides = [];
    var activeSlideIndex = 0;
    var activeFitItems = [];
    var currentContent = null;
    var slideIntervalMs = 10000;

    function setLoading() {
        render(null, null);
    }

    function render(data, error) {
        var panel = dom.byId("bar-widget-panel");
        var content = dom.byId("bar-widget-content");
        var dashboard = dom.byId("dashboard");
        var previousIndex = activeSlideIndex;
        var previousKey = currentSlideKey();
        var nextSlides;

        clearCountdownTimer();
        activeFitItems = [];
        currentContent = content;

        if (!panel || !content) {
            return;
        }

        dom.clear(content);

        if (error || !data || !data.visible) {
            hide(panel, dashboard);
            return;
        }

        panel.style.backgroundColor = safeColor(data.color);
        nextSlides = buildSlides(data);

        if (!nextSlides.length) {
            nextSlides.push({ type: "empty", text: "Bacheca aggiornata" });
        }
        slides = nextSlides;
        activeSlideIndex = preservedSlideIndex(previousKey, previousIndex);

        dom.removeClass(panel, "is-hidden");
        if (dashboard) {
            dom.addClass(dashboard, "has-bar-widget");
        }

        attachResizeHandler();
        renderActiveSlide();
        ensureSlideRotation();
    }

    function hide(panel, dashboard) {
        slides = [];
        clearTimers();
        dom.addClass(panel, "is-hidden");
        if (dashboard) {
            dom.removeClass(dashboard, "has-bar-widget");
        }
    }

    function buildSlides(data) {
        var list = [];
        var announcements = arrayOrEmpty(data.announcements);
        var i;

        if (announcements.length) {
            for (i = 0; i < announcements.length; i++) {
                if (announcements[i] && announcements[i].text) {
                    list.push({ type: "announcement", announcement: announcements[i] });
                }
            }
        } else if (data.announcement && data.announcement.text) {
            list.push({ type: "announcement", announcement: data.announcement });
        }

        if (data.countdown && data.countdown.to) {
            list.push({ type: "countdown", countdown: data.countdown });
        }

        if (data.soccer && data.soccer.enabled) {
            list.push(buildSoccerSlide(data.soccer));
        }

        if (data.basketball && data.basketball.enabled) {
            list.push(buildBasketballSlide(data.basketball));
        }

        if (data.markets && data.markets.enabled) {
            list.push(buildMarketSlide(data.markets));
        }

        return list;
    }

    function buildSoccerSlide(soccer) {
        return buildSportSlide("soccer", "Calcio", soccer, "Calcio non disponibile");
    }

    function buildBasketballSlide(basketball) {
        return buildSportSlide("basketball", "Basket", basketball, "Basket non disponibile");
    }

    function buildSportSlide(type, title, sport, unavailableText) {
        var matches = [];
        var fixtures = arrayOrEmpty(sport.fixtures);
        var results = arrayOrEmpty(sport.results);
        var liveMatches = [];
        var futureMatches = [];
        var i;

        if (sport.available) {
            for (i = 0; i < fixtures.length; i++) {
                if (fixtures[i] && fixtures[i].live) {
                    liveMatches.push(fixtures[i]);
                } else if (fixtures[i]) {
                    futureMatches.push(fixtures[i]);
                }
            }

            for (i = 0; i < liveMatches.length; i++) {
                matches.push({ match: liveMatches[i], label: "Live" });
            }
            for (i = 0; i < results.length; i++) {
                matches.push({ match: results[i], label: "Ultime" });
            }
            for (i = 0; i < futureMatches.length; i++) {
                matches.push({ match: futureMatches[i], label: "Prossime" });
            }
        }

        return {
            type: type,
            title: title,
            sport: sport,
            matches: matches,
            text: sport.available ? "Nessuna partita in evidenza" : sport.message || unavailableText
        };
    }

    function buildMarketSlide(markets) {
        return {
            type: "markets",
            title: "Mercati",
            markets: markets || {},
            items: arrayOrEmpty(markets && markets.items),
            text: markets && markets.available ? "Nessun indice disponibile" : markets && markets.message ? markets.message : "Mercati non disponibili"
        };
    }

    function renderActiveSlide() {
        var slide;

        clearCountdownTimer();
        activeFitItems = [];
        if (!currentContent) {
            return;
        }

        dom.clear(currentContent);
        if (!slides.length) {
            return;
        }

        if (activeSlideIndex >= slides.length) {
            activeSlideIndex = 0;
        }

        slide = slides[activeSlideIndex];
        if (slide.type === "announcement") {
            currentContent.appendChild(createAnnouncementSlide(slide.announcement));
        } else if (slide.type === "countdown") {
            currentContent.appendChild(createCountdownSlide(slide.countdown));
        } else if (slide.type === "soccer") {
            currentContent.appendChild(createSportSlide(slide));
        } else if (slide.type === "basketball") {
            currentContent.appendChild(createSportSlide(slide));
        } else if (slide.type === "markets") {
            currentContent.appendChild(createMarketSlide(slide));
        } else {
            currentContent.appendChild(createMessageSlide("", slide.text || "Bacheca aggiornata"));
        }

        window.setTimeout(fitActiveText, 0);
    }

    function ensureSlideRotation() {
        if (slides.length <= 1) {
            clearSlideTimer();
            return;
        }
        if (slideTimer) {
            return;
        }
        slideTimer = window.setInterval(function () {
            activeSlideIndex = (activeSlideIndex + 1) % slides.length;
            renderActiveSlide();
        }, slideIntervalMs);
    }

    function preservedSlideIndex(previousKey, previousIndex) {
        var i;
        if (previousKey) {
            for (i = 0; i < slides.length; i++) {
                if (slideKey(slides[i]) === previousKey) {
                    return i;
                }
            }
        }
        if (previousIndex >= 0 && previousIndex < slides.length) {
            return previousIndex;
        }
        return 0;
    }

    function currentSlideKey() {
        if (!slides.length || activeSlideIndex < 0 || activeSlideIndex >= slides.length) {
            return "";
        }
        return slideKey(slides[activeSlideIndex]);
    }

    function slideKey(slide) {
        if (!slide) {
            return "";
        }
        if (slide.type === "announcement") {
            return "announcement:" + (slide.announcement && slide.announcement.id ? slide.announcement.id : "");
        }
        if (slide.type === "countdown") {
            return "countdown";
        }
        if (slide.type === "soccer") {
            return "soccer";
        }
        if (slide.type === "basketball") {
            return "basketball";
        }
        if (slide.type === "markets") {
            return "markets";
        }
        return slide.type || "";
    }

    function createAnnouncementSlide(announcement) {
        var item = dom.create("div", "bar-widget-slide bar-widget-announcement");
        var text = dom.create("strong", "bar-widget-fit-text bar-widget-announcement-text", announcement.text);

        item.appendChild(dom.create("span", "bar-widget-label", "Avviso"));
        item.appendChild(text);
        activeFitItems.push({
            element: text,
            max: 40,
            min: 20
        });
        return item;
    }

    function createCountdownSlide(countdown) {
        var item = dom.create("div", "bar-widget-slide bar-widget-countdown");
        var value = dom.create("strong", "bar-widget-countdown-value", "--");

        item.appendChild(dom.create("span", "bar-widget-label", countdown.label || "Manca"));
        item.appendChild(value);
        startCountdown(value, countdown.to);
        return item;
    }

    function createMessageSlide(label, text) {
        var item = dom.create("div", "bar-widget-slide bar-widget-message");
        var message = dom.create("strong", "bar-widget-fit-text", text || "");
        if (label) {
            item.appendChild(dom.create("span", "bar-widget-label", label));
        }
        item.appendChild(message);
        activeFitItems.push({
            element: message,
            max: 38,
            min: 18
        });
        return item;
    }

    function createSportSlide(slide) {
        var item = dom.create("div", "bar-widget-slide bar-widget-soccer-slide bar-widget-" + slide.type + "-slide");
        var header = dom.create("div", "bar-widget-soccer-header");
        var list = dom.create("div", "bar-widget-soccer-match-list");
        var matches = arrayOrEmpty(slide.matches);
        var sport = slide.sport || {};
        var i;

        header.appendChild(dom.create("span", "bar-widget-label", slide.title || "Sport"));
        if (sport.label || sport.competition) {
            header.appendChild(dom.create("strong", "bar-widget-soccer-title", sport.label || sport.competition));
        }
        item.appendChild(header);

        if (!matches.length) {
            item.appendChild(dom.create("div", "bar-widget-soccer-message", slide.text || "Nessuna partita in evidenza"));
            return item;
        }

        for (i = 0; i < matches.length; i++) {
            list.appendChild(createSportMatchCard(matches[i]));
        }
        item.appendChild(list);
        return item;
    }

    function createSportMatchCard(slide) {
        var item = dom.create("div", "bar-widget-soccer-card");
        var match = slide.match || {};
        var top = dom.create("div", "bar-widget-soccer-card-top");
        var middle = dom.create("div", "bar-widget-soccer-card-middle");
        var scoreBlock = dom.create("div", "bar-widget-soccer-score-block");

        top.appendChild(dom.create("strong", "bar-widget-soccer-card-date", sportDateTime(match)));
        if (match.stageLabel) {
            top.appendChild(dom.create("span", "bar-widget-soccer-stage", match.stageLabel));
        }

        scoreBlock.appendChild(createSportScore(match));
        scoreBlock.appendChild(dom.create("span", match.live ? "bar-widget-soccer-live" : "bar-widget-soccer-status", sportStatus(match)));

        middle.appendChild(createSportTeamCard(match.home, "home"));
        middle.appendChild(scoreBlock);
        middle.appendChild(createSportTeamCard(match.away, "away"));

        item.appendChild(top);
        item.appendChild(middle);
        return item;
    }

    function createSportTeamCard(team, side) {
        var data = team || {};
        var root = dom.create("div", "bar-widget-soccer-team-card bar-widget-soccer-team-" + side);
        var visual = dom.create("div", "bar-widget-soccer-team-visual");
        var abbr = dom.create("div", "bar-widget-soccer-team-abbr", data.abbr || shortName(data.shortName || data.name));
        var image;

        if (data.badgeUrl) {
            image = dom.create("img", "bar-widget-soccer-team-badge");
            image.src = data.badgeUrl;
            image.alt = data.abbr || "";
            image.onerror = function () {
                this.style.display = "none";
                dom.addClass(visual, "is-missing-badge");
            };
            visual.appendChild(image);
        } else {
            dom.addClass(visual, "is-missing-badge");
        }

        visual.appendChild(dom.create("span", "bar-widget-soccer-team-chip", data.abbr || shortName(data.shortName || data.name)));
        root.appendChild(visual);
        root.appendChild(abbr);
        root.title = data.name || data.shortName || data.abbr || "";
        return root;
    }

    function createMarketSlide(slide) {
        var item = dom.create("div", "bar-widget-slide bar-widget-market-slide");
        var header = dom.create("div", "bar-widget-market-header");
        var list = dom.create("div", "bar-widget-market-list");
        var items = arrayOrEmpty(slide.items);
        var markets = slide.markets || {};
        var i;

        header.appendChild(dom.create("span", "bar-widget-label", slide.title || "Mercati"));
        if (markets.stale) {
            header.appendChild(dom.create("strong", "bar-widget-market-title", "cache"));
        } else if (markets.partial) {
            header.appendChild(dom.create("strong", "bar-widget-market-title", "parziale"));
        }
        item.appendChild(header);

        if (!items.length) {
            item.appendChild(dom.create("div", "bar-widget-market-message", slide.text || "Mercati non disponibili"));
            return item;
        }

        for (i = 0; i < items.length; i++) {
            list.appendChild(createMarketCard(items[i]));
        }
        item.appendChild(list);
        return item;
    }

    function createMarketCard(market) {
        var data = market || {};
        var item = dom.create("div", "bar-widget-market-card bar-widget-market-" + marketDirection(data));
        var top = dom.create("div", "bar-widget-market-card-top");
        var label = dom.create("strong", "bar-widget-market-name", data.label || data.symbol || "Indice");
        var symbol = dom.create("span", "bar-widget-market-symbol", data.symbol || "");
        var value = dom.create("strong", "bar-widget-market-value", formatMarketValue(data.value));
        var change = dom.create("span", "bar-widget-market-change", formatMarketChange(data));

        top.appendChild(label);
        if (data.symbol) {
            top.appendChild(symbol);
        }
        item.appendChild(top);
        item.appendChild(value);
        item.appendChild(change);
        return item;
    }

    function sportDateTime(match) {
        var date = match && match.displayDate ? match.displayDate : "";
        var time = match && match.displayTime ? match.displayTime : "";
        if (!date && match && match.dateLabel) {
            return match.dateLabel;
        }
        if (date && time) {
            return date + " " + time;
        }
        return date || time || "--";
    }

    function sportScore(match) {
        if (match && match.score) {
            return String(match.score.home) + "-" + String(match.score.away);
        }
        return "vs";
    }

    function sportPenaltyScore(match) {
        if (match && match.score && match.score.home === match.score.away && match.penalties && match.penalties.home !== null && match.penalties.home !== undefined && match.penalties.away !== null && match.penalties.away !== undefined) {
            return "Rigori " + String(match.penalties.home) + "-" + String(match.penalties.away);
        }
        return "";
    }

    function createSportScore(match) {
        var score = dom.create("strong", "bar-widget-soccer-card-score", sportScore(match));
        var penalties = sportPenaltyScore(match);

        if (penalties) {
            score = dom.create("div", "bar-widget-soccer-card-score-stack");
            score.appendChild(dom.create("strong", "bar-widget-soccer-card-score", sportScore(match)));
            score.appendChild(dom.create("span", "bar-widget-soccer-card-penalty-score", penalties));
        }

        return score;
    }

    function sportStatus(match) {
        if (!match) {
            return "";
        }
        if (match.live) {
            var minute = liveMinute(match);
            if (minute) {
                return "LIVE " + minute;
            }
            if (match.period) {
                return "LIVE " + match.period;
            }
            if (match.statusLabel && match.statusLabel !== "LIVE") {
                return "LIVE " + match.statusLabel;
            }
            return "LIVE";
        }
        if (match.kind === "result") {
            return "Risultato";
        }
        return "In programma";
    }

    function liveMinute(match) {
        if (match.minute === null || match.minute === undefined) {
            return "";
        }
        if (match.injuryTime !== null && match.injuryTime !== undefined && match.injuryTime > 0) {
            return String(match.minute) + "+" + String(match.injuryTime) + "'";
        }
        return String(match.minute) + "'";
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
            resizeTimer = window.setTimeout(fitActiveText, 180);
        };
    }

    function fitActiveText() {
        var i;
        for (i = 0; i < activeFitItems.length; i++) {
            fitText(activeFitItems[i]);
        }
    }

    function fitText(item) {
        var element = item && item.element;
        var size = item ? item.max : 34;
        var min = item ? item.min : 18;
        var parent;

        if (!element) {
            return;
        }

        parent = element.parentNode;
        element.style.fontSize = size + "px";
        while (size > min && parent && element.clientWidth > 0 && element.scrollWidth > element.clientWidth) {
            size = size - 1;
            element.style.fontSize = size + "px";
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

    function clearTimers() {
        clearCountdownTimer();
        clearSlideTimer();
    }

    function clearSlideTimer() {
        if (slideTimer) {
            window.clearInterval(slideTimer);
            slideTimer = null;
        }
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

    function marketDirection(data) {
        var direction = data && data.direction ? String(data.direction) : "";
        if (direction === "up" || direction === "down") {
            return direction;
        }
        return "flat";
    }

    function formatMarketValue(value) {
        var number = parseFloat(value);
        var decimals;
        if (isNaN(number)) {
            return "--";
        }
        decimals = Math.abs(number) >= 1000 ? 0 : 2;
        return formatDecimal(number, decimals);
    }

    function formatMarketChange(data) {
        var change = data ? parseFloat(data.change) : NaN;
        var percent = data ? parseFloat(data.changePercent) : NaN;
        var sign;
        if (isNaN(change) || isNaN(percent)) {
            return "--";
        }
        sign = change > 0 ? "+" : "";
        return sign + formatDecimal(change, 2) + " (" + sign + formatDecimal(percent, 2) + "%)";
    }

    function formatDecimal(value, decimals) {
        var parts = Number(value).toFixed(decimals).split(".");
        var integer = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ".");
        if (parts.length > 1) {
            return integer + "," + parts[1];
        }
        return integer;
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
