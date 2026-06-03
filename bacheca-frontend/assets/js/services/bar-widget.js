(function (window) {
    var Bacheca = window.Bacheca = window.Bacheca || {};
    Bacheca.services = Bacheca.services || {};

    var config = window.BachecaConfig;
    var http = Bacheca.utils.http;

    function load(callback) {
        var path = (config.api && config.api.barWidget) || "/api/bar-widget";
        http.getJson(path, function (error, response) {
            if (error) {
                callback(error);
                return;
            }
            callback(null, response || null);
        });
    }

    Bacheca.services.barWidget = {
        load: load
    };
})(window);
