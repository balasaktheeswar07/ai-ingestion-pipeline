# Responsible acquisition strategy

Frontier Atlas uses official APIs first, then RSS/Atom feeds, permitted static HTML, and Playwright Async only where rendering is allowed by a site's terms. It does not solve CAPTCHAs, evade authentication, disguise automation, or bypass paywalls.

Each source adapter declares its allowed acquisition method. The shared client bounds concurrency, applies backoff, and can cache conditional `ETag`/`Last-Modified` responses. A 403, 429, or challenge page is logged as blocked; workers stop or reduce traffic for that source. The source is then escalated to an approved API, licensed provider, or data partnership.

`adapter → allowed API/RSS/HTML/Playwright → rate limiter → parser → idempotency store`
