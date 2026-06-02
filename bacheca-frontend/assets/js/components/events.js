(function (window) {
    var Bacheca = window.Bacheca = window.Bacheca || {};
    Bacheca.components = Bacheca.components || {};

    var dom = Bacheca.utils.dom;

    function setLoading() {
        var mount = dom.byId("events-list");
        dom.clear(mount);
        mount.appendChild(dom.emptyState("Caricamento eventi"));
    }

    function render(events, error, maxItems) {
        var mount = dom.byId("events-list");
        var visibleEvents;
        var i;
        var child;
        dom.clear(mount);

        if (error) {
            mount.appendChild(dom.emptyState("Eventi non disponibili"));
            return;
        }

        if (!events || !events.length) {
            mount.appendChild(dom.emptyState("Non ci sono eventi nella prossima settimana"));
            return;
        }

        visibleEvents = maxItems ? events.slice(0, maxItems) : events;
        for (i = 0; i < visibleEvents.length; i++) {
            child = createEventItem(visibleEvents[i]);
            mount.appendChild(child);
            if (doesOverflow(mount)) {
                mount.removeChild(child);
                break;
            }
        }

        if (!mount.childNodes.length) {
            mount.appendChild(dom.emptyState("Nessun evento visibile nello spazio disponibile"));
        }
    }

    function doesOverflow(element) {
        return element && element.scrollHeight > element.clientHeight + 1;
    }

    function createEventItem(event) {
        var root = dom.create("article", "event-item");
        var date = dom.create("div", "event-date");
        var dayName = dom.create("span", "", event.dayName);
        var dayNumber = dom.create("strong", "", event.dayNumber);
        var body = dom.create("div", "event-body");
        var title = dom.create("div", "event-title", event.title);
        var meta = dom.create("div", "event-meta");
        var metaText = event.timeLabel;

        if (event.location) {
            metaText += " - Luogo: " + event.location;
        }

        dom.setText(meta, metaText);
        date.appendChild(dayName);
        date.appendChild(dayNumber);
        body.appendChild(title);
        body.appendChild(meta);
        root.appendChild(date);
        root.appendChild(body);

        return root;
    }

    Bacheca.components.events = {
        setLoading: setLoading,
        render: render
    };
})(window);
