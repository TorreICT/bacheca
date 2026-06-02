(function (window) {
    var Bacheca = window.Bacheca = window.Bacheca || {};
    Bacheca.components = Bacheca.components || {};

    var dom = Bacheca.utils.dom;
    var config = window.BachecaConfig;

    function render(names) {
        var panel = dom.byId("birthdays-panel");
        var mount = dom.byId("birthdays-content");
        var image;
        var text;

        dom.clear(mount);

        if (!names || !names.length) {
            dom.addClass(panel, "is-hidden");
            dom.removeClass(panel, "is-featured");
            return;
        }

        dom.removeClass(panel, "is-hidden");
        dom.addClass(panel, "is-featured");

        image = dom.create("img");
        image.src = config.birthdayIconPath;
        image.alt = "";

        text = dom.create("div", "birthday-text", messageFor(names));
        mount.appendChild(image);
        mount.appendChild(text);
    }

    function messageFor(names) {
        if (names.length === 1) {
            return "Compleanno di " + names[0];
        }
        if (names.length === 2) {
            return "Compleanno di " + names[0] + " e " + names[1];
        }
        if (names.length === 3) {
            return "Compleanno di " + names[0] + ", " + names[1] + " e " + names[2];
        }
        return "Compleanno di " + names.length + " persone";
    }

    Bacheca.components.birthdays = {
        render: render,
        messageFor: messageFor
    };
})(window);
