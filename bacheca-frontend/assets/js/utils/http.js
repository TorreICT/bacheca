(function (window) {
    var Bacheca = window.Bacheca = window.Bacheca || {};
    Bacheca.utils = Bacheca.utils || {};

    function joinUrl(baseUrl, path) {
        if (!baseUrl) {
            return path;
        }
        if (!path) {
            return baseUrl;
        }
        return String(baseUrl).replace(/\/+$/, "") + "/" + String(path).replace(/^\/+/, "");
    }

    function logRequest(message, detail) {
        if (window.console && window.console.log) {
            window.console.log("[Bacheca] " + message, detail || "");
        }
    }

    function getJson(url, callback) {
        var xhr = new XMLHttpRequest();
        var timeout = window.BachecaConfig && window.BachecaConfig.requestTimeoutMs ? window.BachecaConfig.requestTimeoutMs : 8000;
        var completed = false;

        logRequest("GET " + url);

        function finish(error, data) {
            if (completed) {
                return;
            }
            completed = true;
            callback(error, data);
        }

        xhr.onreadystatechange = function () {
            var data;
            if (completed || xhr.readyState !== 4) {
                return;
            }

            if ((xhr.status >= 200 && xhr.status < 300) || (xhr.status === 0 && xhr.responseText)) {
                if (!xhr.responseText || /^\s*$/.test(xhr.responseText)) {
                    logRequest("GET empty " + url + " status=" + xhr.status);
                    finish(null, null);
                    return;
                }
                try {
                    data = JSON.parse(xhr.responseText);
                } catch (parseError) {
                    logRequest("GET parse error " + url, parseError);
                    finish(parseError);
                    return;
                }
                logRequest("GET success " + url + " status=" + xhr.status);
                finish(null, data);
                return;
            }

            logRequest("GET failed " + url + " status=" + xhr.status);
            finish(new Error("HTTP " + xhr.status + " for " + url));
        };

        xhr.onerror = function () {
            if (completed) {
                return;
            }
            logRequest("GET network/CORS error " + url);
            finish(new Error("Network error for " + url));
        };

        xhr.ontimeout = function () {
            if (completed) {
                return;
            }
            logRequest("GET timeout " + url);
            finish(new Error("Timeout for " + url));
        };

        xhr.open("GET", url, true);
        xhr.timeout = timeout;
        xhr.send(null);
    }

    Bacheca.utils.http = {
        joinUrl: joinUrl,
        getJson: getJson
    };
})(window);
