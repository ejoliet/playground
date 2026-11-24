# Can a browser make a trackpad talk?

**Result: hardware gate unresolved.** The upstream native call cannot be invoked directly by ordinary browser WASM. WebHID is a separate possible route, not demonstrated here.

[Research prompt](PROMPT.md) · [Build log](notes.md) · [Diagnostic](index.html)

## Try it

On a Mac, clone the branch and serve the folder:

```sh
git clone -b research/nospeaker-web https://github.com/ejoliet/playground.git
cd playground/nospeaker-web
python3 -m http.server 8000 --bind 127.0.0.1
```

Open http://localhost:8000 in desktop Chrome. Alternatively serve these static files over HTTPS (no backend required). Click Choose Apple HID device; try built-in and external Magic Trackpad separately. Export the JSON evidence. The chooser may omit protected interfaces; a listed device or report ID does not establish permission to write it.

## Results

| Experiment | Outcome |
|---|---|
| Inspect original Swift | Native MultitouchSupport loaded via dlopen, symbols via dlsym |
| Inspect Pyodide architecture | WASM shared libraries are not native macOS frameworks |
| Inspect Chrome WebHID policy | Protected collections cannot send or receive reports |
| Static diagnostic checks | Apple vendor filter, JSON export and no write/open calls found |
| Actual Chrome device discovery | Not run: no target Mac or hardware access |
| 440 Hz trackpad playback | Not run: no verified actuator protocol |

No speech synthesis or Pyodide bundle was added because it would not resolve the hardware gate. This is a diagnostic, not a working trackpad synthesizer.

Sources: [upstream Swift](https://github.com/os6/nospeaker/blob/main/nospeaker.swift), [Pyodide constraints](https://pyodide.org/en/stable/usage/wasm-constraints.html), [Chrome HID security](https://developer.chrome.com/docs/capabilities/hid).
