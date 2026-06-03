# Bacheca Frontend

Static plain-JS dashboard served by the FastAPI backend in this repo.

This folder has no package manager, no Node runtime, no build step, and no
startup scripts. Production serving is handled by `../start-service.sh`.

## API Configuration

`assets/js/config.js` uses same-origin API paths:

```js
api: {
    meals: "/api/pasti",
    menu: "/api/menu",
    calendar: "/api/calendar",
    pizzaIndex: "/api/pizza-index",
    randomPhoto: "/api/random-photo",
    barWidget: "/api/bar-widget"
}
```

The browser calls same-origin dashboard APIs for backend-owned data, including
the Telegram-controlled bar widget. It never calls Telegram or soccer providers
directly. The only direct browser-side external data call is weather, via
Open-Meteo.

## Compatibility

Frontend JavaScript should remain old-browser friendly:

- no ES modules;
- no `fetch`;
- no `async` / `await`;
- no arrow functions;
- no `let` / `const`;
- no optional chaining.

Check syntax from the repo root:

```bash
find bacheca-frontend/assets/js -name "*.js" -print -exec node --check {} \;
```
