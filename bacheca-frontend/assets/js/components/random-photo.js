(function (window) {
    var Bacheca = window.Bacheca = window.Bacheca || {};
    Bacheca.components = Bacheca.components || {};

    var dom = Bacheca.utils.dom;

    function hide() {
        var panel = dom.byId("random-photo-panel");
        var content = dom.byId("random-photo-content");

        dom.clear(content);
        dom.addClass(panel, "is-hidden");
    }

    function setLoading() {
        hide();
    }

    function render(data, error) {
        var panel = dom.byId("random-photo-panel");
        var content = dom.byId("random-photo-content");
        var grid;
        var image;
        var photos;
        var i;
        var item;

        dom.clear(content);

        if (error || !data || !data.photos || !data.photos.length) {
            dom.addClass(panel, "is-hidden");
            return;
        }

        grid = dom.create("div", data.photos.length > 1 ? "random-photo-grid" : "random-photo-grid random-photo-grid-single");
        photos = data.photos.length > 2 ? data.photos.slice(0, 2) : data.photos;

        for (i = 0; i < photos.length; i += 1) {
            item = photos[i];
            image = dom.create("img", "random-photo-image");
            image.src = item.imageUrl;
            image.alt = "Foto casuale Torrescalla";
            grid.appendChild(image);
        }

        content.appendChild(grid);

        panel.setAttribute("title", "Foto casuale Torrescalla");
        dom.removeClass(panel, "is-hidden");
    }

    Bacheca.components.randomPhoto = {
        setLoading: setLoading,
        render: render
    };
})(window);
