# Research log — 2026-11-23

1. Retrieved upstream README (blob 8b0bd5d220bc94546cefece635cb379c41f7eedb) and Swift source (blob da809bad1fbe099f33790ac77c6517678009c675, 1610 lines). Swift imports IOKit at line 23, loads private MultitouchSupport via dlopen at line 71, resolves symbols via dlsym at line 73, and binds MTActuationCreateFromDictionary and MTActuationActuate at lines 96–97. Upstream README reports Intel MacBookPro15,1 and Apple Silicon testing; external Magic Trackpad was not tested by upstream.
2. Consulted Pyodide official compatibility and ABI documentation, plus Chrome WebHID documentation. Pyodide shared libraries must be built for the Emscripten target; the original native framework is not such a library. Chrome denies reports in protected collections, including mouse/keyboard. This does not establish whether a separate vendor-defined collection is usable.
3. Created branch from master and committed PROMPT.md and index.html. Diagnostic requests Apple vendor ID 0x05ac with user consent, enumerates collections and report IDs, and exports timestamped JSON. It deliberately sends no reports and does not open devices.
4. Retrieved committed HTML (blob bafa15a7cf4a0616ad1613a2748220e023ff8057) and executed static JavaScript string checks: script present=true; no sendReport/sendFeatureReport/open calls=true; Apple vendor filter=true; evidence filename=true. These are source checks only, not browser integration tests.
5. No target macOS browser or attached trackpad available. No acoustic recordings, HID traffic captures, Pyodide runtime execution or physical playback performed. Stop at hardware gate. Next experiment: run diagnostic on actual Mac with internal/external trackpad, then inspect independently verified actuator protocol if a relevant accessible collection exists. Do not infer that an empty chooser proves universal impossibility.

## Runtime follow-up

Executed on Linux: node -e 'WebAssembly.instantiate(Uint8Array.from([0,97,115,109,1,0,0,0])).then(x=>console.log(JSON.stringify({instantiated:!!x.instance,imports:WebAssembly.Module.imports(x.module),exports:WebAssembly.Module.exports(x.module)})))'

Output: {"instantiated":true,"imports":[],"exports":[]}. This only verifies empty-module instantiation in Node, not browser hardware access.

Attempted headless Chromium with localhost HTTP and a minimal browser WASM/WebHID probe: command timed out after 20 seconds. Attempted Playwright Chromium file navigation: net::ERR_BLOCKED_BY_ADMINISTRATOR. Neither yielded device data. No attempt to bypass restrictions. No Pyodide runtime execution. No target Mac available. Stop at hardware gate.
