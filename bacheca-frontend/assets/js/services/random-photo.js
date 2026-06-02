(function (window) {
    var Bacheca = window.Bacheca = window.Bacheca || {};
    Bacheca.services = Bacheca.services || {};

    var config = window.BachecaConfig;
    var http = Bacheca.utils.http;
    var dateUtils = Bacheca.utils.date;

    function buildUrl(dateText) {
        var path = (config.api && config.api.randomPhoto) || "/api/random-photo";
        var dateValue = dateText || dateUtils.formatIsoDate(new Date());
        var refreshValue = String(new Date().getTime()) + String(Math.floor(Math.random() * 1000000));

        return path + "?data=" + encodeURIComponent(dateValue) + "&refresh=" + encodeURIComponent(refreshValue);
    }

    function normalize(response) {
        var photos = [];
        var sourcePhotos;
        var i;
        var item;

        if (!response || response.available !== true || !response.id || !response.imagePath) {
            return null;
        }

        sourcePhotos = response.photos && response.photos.length ? response.photos : [{
            id: response.id,
            imagePath: response.imagePath,
            fileName: response.fileName
        }];

        for (i = 0; i < sourcePhotos.length; i += 1) {
            item = sourcePhotos[i];
            if (item && item.id && item.imagePath) {
                photos.push({
                    id: item.id,
                    imageUrl: item.imagePath,
                    fileName: item.fileName || ""
                });
            }
        }

        if (!photos.length) {
            return null;
        }

        return {
            id: response.id,
            imageUrl: photos[0].imageUrl,
            fileName: response.fileName || "",
            photos: photos,
            requestedYear: response.requestedYear || "",
            sourceYear: response.sourceYear || response.requestedYear || "",
            count: response.count || 0,
            timedOut: !!response.timedOut
        };
    }

    function load(callback) {
        var dateText = dateUtils.formatIsoDate(new Date());
        var url = buildUrl(dateText);

        http.getJson(url, function (error, response) {
            if (error) {
                callback(error);
                return;
            }

            callback(null, normalize(response));
        });
    }

    Bacheca.services.randomPhoto = {
        buildUrl: buildUrl,
        load: load,
        normalize: normalize
    };
})(window);
