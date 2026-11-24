# Research prompt

Can a normal web page make a MacBook Force Touch trackpad or external Magic Trackpad emit an audible 440 Hz tone, like https://github.com/os6/nospeaker, without installing anything?

Investigate by running code. Read the upstream implementation and identify exactly where it crosses the native OS boundary. Test whether Pyodide or WebAssembly changes that boundary; prioritize WebHID discovery and report descriptors before porting speech synthesis. Compare built-in and external trackpads using stock Chrome on macOS. Do not disable browser protections, guess actuator reports, or drive unknown hardware commands. Only attempt a brief low-strength 440 Hz tone if a documented or independently verified safe actuator protocol is available. Mute speakers and record microphone evidence against a silent baseline; distinguish physical sound from ordinary speaker playback.

Build a minimal static diagnostic page with downloadable JSON evidence. Test what can actually be tested in the available environment. Clearly separate source inspection, executed tests, hardware observations and hypotheses. Do not claim impossibility from an unavailable device. Write README.md and notes.md in nospeaker-web/ only, along with the prompt and prototype. No _summary.md. Stop at the first unresolved hardware gate; do not build a native bridge or port speech processing until it passes.
