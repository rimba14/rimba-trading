## 2024-05-21 - Caching error states causes permanent failure
**Learning:** When using `functools.lru_cache` to cache network requests, if the function handles exceptions internally and returns a default or fallback value (e.g. `(0, 0)`), caching will persist that failure permanently.
**Action:** Use a manual dictionary cache instead of `lru_cache` when you need to conditionally cache only successful results.
