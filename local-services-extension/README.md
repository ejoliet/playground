# Local Services for Chrome

Discover the web servers running on your computer and open them from one tab. Discovery runs when you select **Discover**. Your results are saved in the current Chrome profile, and you can export them to the [static Local Services directory](https://ejoliet.github.io/local-services/).

## Install

1. Download **local-services-extension.zip** from the [0.1.0 preview release](https://github.com/ejoliet/playground/releases/tag/local-services-v0.1.0) and extract it to a folder you can keep.
2. Open `chrome://extensions`, turn on **Developer mode**, select **Load unpacked**, and choose the extracted folder that contains `manifest.json`.
3. The Local Services tab opens. In **Helper setup**, check the operating system and processor, download the installer, and open it. The extension shows the installation steps for your selection.
4. Return to the extension and select **Check connection**, then **Discover**. You can reopen the directory from Chrome’s **Extensions** menu or pin it to the toolbar.

| Platform | Installation |
| --- | --- |
| Windows x64 or ARM64 | Open the matching `.exe` and follow the wizard. The installer registers the helper for the current Windows user. Remove it from **Settings → Installed apps**. |
| macOS Apple silicon or Intel | Open the ZIP and double-click **Install Local Services Helper**. Choose **Install** in the dialog. To uninstall, open the same app and choose **Remove**. |
| Debian/Ubuntu x64 or ARM64 | Open the matching `.deb` in a graphical package installer. It registers the helper for regular Google Chrome and Chromium installations. Remove the package with your package manager. |

The Windows and macOS preview installers have no publisher signature or Apple notarization. If your device permits installing trusted unsigned apps, the extension explains how to use the system’s normal approval prompts. The extension ZIP loads through Developer mode. Snap and Flatpak browser packages can have different native messaging requirements and are outside this preview.

## What gets discovered

The native helper reads the host’s listening TCP sockets and sends concurrent, short `HEAD /` probes to those local addresses. It recognizes HTTP and HTTPS responses, including redirects and authentication responses. Links to TLS endpoints with self-signed certificates still use Chrome’s normal certificate checks. Discovery may miss services that require a custom hostname, a client certificate, or a different request path or method. Process names depend on OS permissions and listener information.

## Privacy and permissions

- `nativeMessaging` connects Chrome to the registered helper. The installer restricts the host to this extension’s ID. The helper accepts a connection check and a discovery command. It accepts no user-provided target address.
- `storage` remembers the latest results in `chrome.storage.local`. **Clear results** removes them. Export creates a JSON file on your device.
- The extension requests no site or browsing-history permissions. The helper uses standard input and output, runs only when Chrome invokes it, and opens no listening port. Discovery contacts local listeners directly, without proxies, redirects, accounts, or telemetry. The download links open GitHub only when selected.

## Build from source

The extension is plain HTML, CSS, and JavaScript. The helper is a standalone Go executable with no runtime dependencies beyond the platform’s usual listener tools. Linux falls back to `/proc/net/tcp` when `ss` is unavailable. On macOS it uses `lsof`, and on Windows it uses `netstat` and, when available, `tasklist`.

To build on Linux with Go 1.23+, Node, NSIS, and `dpkg-deb`, run `packaging/build.sh /absolute/path/to/output`. The script creates one extension ZIP with the manifest at its root, six installer packages, and SHA-256 checksums. The extension’s embedded public key gives the unpacked extension a stable ID. The packaging script derives the same ID for all helper registrations.

For a local test, load the `extension/` folder in Chrome, install the package for your OS, check the connection, and discover a running local web server. Check search, protocol filters, cancellation, export, and clearing results.
