# Typography

Tally uses the OS system font stack — no webfont files to bundle or license:

```
--font-sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", sans-serif;
```

Renders as San Francisco on macOS/iOS, Segoe UI on Windows, Roboto on Android/ChromeOS.
Amounts and other numeric columns always use `font-variant-numeric: tabular-nums` for
column alignment. Weights used: 400 (body), 500–600 (labels, buttons), 700 (headings,
totals). See `DESIGN-SYSTEM.md` §1.4 for full type scale.
