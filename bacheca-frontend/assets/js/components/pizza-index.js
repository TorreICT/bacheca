(function (window) {
    var Bacheca = window.Bacheca = window.Bacheca || {};
    Bacheca.components = Bacheca.components || {};

    var dom = Bacheca.utils.dom;
    var levelClasses = [
        "pizza-index-threat-1",
        "pizza-index-threat-2",
        "pizza-index-threat-3",
        "pizza-index-threat-4",
        "pizza-index-threat-5"
    ];

    function clearLevelClasses(panel) {
        var i;
        for (i = 0; i < levelClasses.length; i += 1) {
            dom.removeClass(panel, levelClasses[i]);
        }
    }

    function hide() {
        var panel = dom.byId("pizza-index-panel");
        var content = dom.byId("pizza-index-content");

        dom.clear(content);
        clearLevelClasses(panel);
        dom.addClass(panel, "is-hidden");
    }

    function setLoading() {
        hide();
    }

    function render(data, error) {
        var panel = dom.byId("pizza-index-panel");
        var content = dom.byId("pizza-index-content");
        var icon;
        var level;
        var text;

        dom.clear(content);
        clearLevelClasses(panel);

        if (error || !data || !data.level) {
            dom.addClass(panel, "is-hidden");
            return;
        }

        icon = dom.create("img", "pizza-index-icon");
        icon.src = "assets/img/pizza.svg";
        icon.alt = "";
        level = dom.create("div", "pizza-index-level", data.title);
        text = dom.create("div", "pizza-index-text");
        text.appendChild(dom.create("strong", "", data.name));
        text.appendChild(dom.create("span", "", data.meaning));

        content.appendChild(icon);
        content.appendChild(level);
        content.appendChild(text);
        panel.setAttribute("title", "Pizza Index: " + data.title + " - " + data.name + ". " + data.meaning);
        dom.addClass(panel, "pizza-index-threat-" + data.level);
        dom.removeClass(panel, "is-hidden");
    }

    Bacheca.components.pizzaIndex = {
        setLoading: setLoading,
        render: render
    };
})(window);
