(function (window) {
    var Bacheca = window.Bacheca = window.Bacheca || {};
    Bacheca.services = Bacheca.services || {};

    var config = window.BachecaConfig;
    var http = Bacheca.utils.http;
    var dateUtils = Bacheca.utils.date;

    function buildUrl(dateText, birthdayNames) {
        var path = (config.api && config.api.randomPhoto) || "/api/random-photo";
        var dateValue = dateText || dateUtils.formatIsoDate(new Date());
        var refreshValue = String(new Date().getTime()) + String(Math.floor(Math.random() * 1000000));
        var params = [
            "data=" + encodeURIComponent(dateValue),
            "refresh=" + encodeURIComponent(refreshValue)
        ];
        var i;

        birthdayNames = birthdayNames || [];
        for (i = 0; i < birthdayNames.length; i += 1) {
            if (birthdayNames[i]) {
                params.push("birthdayName=" + encodeURIComponent(birthdayNames[i]));
            }
        }

        return path + "?" + params.join("&");
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

    function load(birthdayNames, callback) {
        var dateText = dateUtils.formatIsoDate(new Date());
        var url;

        if (typeof birthdayNames === "function") {
            callback = birthdayNames;
            birthdayNames = [];
        }

        url = buildUrl(dateText, birthdayNames);

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
