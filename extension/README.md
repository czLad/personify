# Personify Extension

The Chrome extension is the **eyes and hands** of the Personify agent. It runs on supported job application portals, scans the DOM for form fields, sends them to the backend for classification + generation, and pastes the results back into the page.

## Files

| File | Purpose |
|---|---|
| `manifest.json` | Manifest V3 declaration |
| `src/content_script.js` | Runs on job pages — scans DOM, calls backend, pastes responses |
| `src/background.js` | Service worker — message relay, future scheduling |
| `src/popup.html/.css/.js` | Toolbar popup UI with autofill trigger |

## Loading in Chrome

1. Open `chrome://extensions`
2. Toggle **Developer mode** on
3. **Load unpacked** → select this `extension/` directory
4. Pin Personify to your toolbar

## Hot reload

After editing files, click the **refresh** icon on the extension card in `chrome://extensions`. The popup will reload automatically; content scripts only re-inject on page reload.

## Icons

Placeholder icons are referenced in the manifest. Add `icons/icon16.png`, `icons/icon48.png`, `icons/icon128.png` before publishing — for local development the extension loads fine without them.

## Adding a portal

To support a new ATS:
1. Add the URL pattern under `host_permissions` in `manifest.json`
2. Add the same pattern under `content_scripts.matches`
3. Test the existing selector strategy on the new portal — most likely you'll need to extend `buildSelector()` and `scrapeJobDescription()` for portal-specific quirks
