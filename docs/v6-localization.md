# Dashboard languages

Open **MeshcoreStation Settings** and choose **Language / Sprache**. The page reloads in the selected language. English is the default. The choice is saved in a first-party cookie on the current browser profile and station address. Users can choose different languages while using the same station. Date and clock formats are still configured separately.

Translations apply to dashboard labels, notices, charts and controls. Names, saved messages, configured bot replies, repeater console output and device identifiers retain their original values.

## Adding a language

Add a JSON catalog named for its language code in `meshcorestation/web/locales/`. Use the message identifiers from `en.json` and retain positional placeholders such as `{0}` and `{1}`. Add the language's display name to `language_names` in the dashboard layout. Both Dash and the browser use the same catalogs and fall back to English for missing entries.

Use `t(identifier, ...values)` for Python UI output and `ui(identifier, ...values)` in dashboard assets. For static dialog markup, `uiHTML` translates text and accessibility labels while preserving control values and attributes used by the application. Translate known errors at the point where they are shown. Keep raw device responses and unknown diagnostic details available as received.
