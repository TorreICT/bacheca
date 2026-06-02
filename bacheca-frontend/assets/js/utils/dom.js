(function (window, document) {
    var Bacheca = window.Bacheca = window.Bacheca || {};
    Bacheca.utils = Bacheca.utils || {};

    function byId(id) {
        return document.getElementById(id);
    }

    function create(tagName, className, text) {
        var element = document.createElement(tagName);
        if (className) {
            element.className = className;
        }
        if (text !== undefined && text !== null) {
            setText(element, text);
        }
        return element;
    }

    function setText(element, value) {
        if (!element) {
            return;
        }
        if (element.textContent !== undefined) {
            element.textContent = value;
        } else {
            element.innerText = value;
        }
    }

    function clear(element) {
        if (!element) {
            return;
        }
        while (element.firstChild) {
            element.removeChild(element.firstChild);
        }
    }

    function addClass(element, className) {
        if (!element || hasClass(element, className)) {
            return;
        }
        element.className = element.className ? element.className + " " + className : className;
    }

    function removeClass(element, className) {
        if (!element || !element.className) {
            return;
        }
        element.className = (" " + element.className + " ").replace(" " + className + " ", " ").replace(/^\s+|\s+$/g, "");
    }

    function hasClass(element, className) {
        return element && (" " + element.className + " ").indexOf(" " + className + " ") !== -1;
    }

    function emptyState(message) {
        return create("div", "empty-state", message);
    }

    Bacheca.utils.dom = {
        byId: byId,
        create: create,
        setText: setText,
        clear: clear,
        addClass: addClass,
        removeClass: removeClass,
        hasClass: hasClass,
        emptyState: emptyState
    };
})(window, document);
