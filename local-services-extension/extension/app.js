"use strict";

const host = "io.github.ejoliet.local_services";
const protocolVersion = 1;
const extensionVersion = chrome.runtime.getManifest().version;
const release = `https://github.com/ejoliet/playground/releases/download/local-services-v${extensionVersion}/`;
const installers = {
  "windows-amd64": "local-services-helper-windows-amd64.exe",
  "windows-arm64": "local-services-helper-windows-arm64.exe",
  "macos-arm64": "local-services-helper-macos-arm64.zip",
  "macos-amd64": "local-services-helper-macos-amd64.zip",
  "linux-amd64": "local-services-helper-linux-amd64.deb",
  "linux-arm64": "local-services-helper-linux-arm64.deb",
};
const $ = (id) => document.getElementById(id);
const setup = $("setup");
const scanButton = $("scan");
const cancelButton = $("cancel");
const verifyButton = $("verify");
const search = $("search");
const filters = document.querySelectorAll("[data-filter]");
const platform = $("platform");
let snapshot = null;
let filter = "all";
let connected = false;
let active = null;
let saving = false;

function status(text, error = false, element = $("status")) {
  element.textContent = text;
  element.dataset.error = error;
}

function updateButtons() {
  scanButton.disabled = !connected || !!active || saving;
  verifyButton.disabled = !!active || saving;
  cancelButton.hidden = active?.command !== "discover";
  $("clear").disabled = !snapshot || !!active || saving;
  $("results").setAttribute("aria-busy", active?.command === "discover" ? "true" : "false");
}

function connection(state, text) {
  connected = state === "connected";
  $("connection").dataset.state = state;
  $("connection-text").textContent = text;
  updateButtons();
}

function request(command) {
  return new Promise((resolve, reject) => {
    let port;
    try {
      port = chrome.runtime.connectNative(host);
    } catch (error) {
      reject(error);
      return;
    }
    const timeout = window.setTimeout(
      () => finish(new Error("The helper took too long to respond. Try checking the connection again.")),
      command === "ping" ? 6000 : 28000,
    );
    let settled = false;

    function finish(error, message) {
      if (settled) return;
      settled = true;
      window.clearTimeout(timeout);
      active = null;
      port.disconnect();
      updateButtons();
      if (error) reject(error);
      else resolve(message);
    }

    active = {command, cancel: () => finish(new DOMException("Discovery cancelled.", "AbortError"))};
    updateButtons();
    port.onMessage.addListener((message) => {
      if (message?.version !== protocolVersion || message.helperVersion !== extensionVersion) {
        finish(new Error("The helper version differs from this extension. Download and install the matching helper from Setup."));
      } else if (message.error) {
        const error = new Error(String(message.error));
        error.helperResponded = true;
        finish(error);
      } else {
        finish(null, message);
      }
    });
    port.onDisconnect.addListener(() => {
      const detail = chrome.runtime.lastError?.message || "The helper disconnected.";
      finish(new Error(detail));
    });
    try {
      port.postMessage({command, version: protocolVersion});
    } catch (error) {
      finish(error);
    }
  });
}

function helperAdvice(error) {
  if (/not found|not registered|access.*forbidden/i.test(error.message)) {
    return "Chrome couldn’t find the helper. Install it below, then check the connection again.";
  }
  return error.message;
}

async function verify() {
  if (active || saving) return;
  connection("checking", "Checking helper");
  status("Checking the helper connection…", false, $("setup-status"));
  try {
    const message = await request("ping");
    const wasOpen = setup.open;
    connection("connected", "Helper connected");
    status(snapshot ? scanSummary() : "Ready to discover. Select Discover to check this machine’s listeners.");
    status(`Helper ${message.helperVersion} is connected.`, false, $("setup-status"));
    if (document.activeElement === verifyButton) scanButton.focus();
    if (wasOpen) setup.open = false;
  } catch (error) {
    connection("missing", "Helper disconnected");
    setup.open = true;
    status("Install or reconnect the helper to discover services.");
    status(helperAdvice(error), true, $("setup-status"));
  }
}

function validatedServices(values) {
  if (!Array.isArray(values)) return [];
  return values.flatMap((item) => {
    if (!item || !["http", "https"].includes(item.protocol)
      || !Number.isInteger(item.port) || item.port < 1 || item.port > 65535
      || typeof item.url !== "string" || typeof item.address !== "string"
      || typeof item.process !== "string" || !Number.isInteger(item.status)) return [];
    try {
      const url = new URL(item.url);
      if (url.protocol !== item.protocol + ":" || url.username || url.password) return [];
      return [{...item, url: url.href}];
    } catch {
      // Scoped IPv6 addresses cannot be opened as URLs in Chrome, but may be listed.
      return [{...item, url: ""}];
    }
  });
}

function label(service) {
  return service.process || "Web service";
}

function makeRow(service) {
  const row = document.createElement("tr");
  const name = document.createElement("span");
  name.className = "name";
  name.textContent = label(service);
  const address = document.createElement("span");
  address.className = "address";
  address.textContent = service.address;
  row.insertCell().append(name, address);

  const port = row.insertCell();
  port.className = "port";
  port.textContent = service.port;
  const badge = document.createElement("span");
  badge.className = `badge ${service.protocol}`;
  badge.textContent = service.protocol.toUpperCase();
  badge.title = `Responded with status ${service.status}`;
  row.insertCell().append(badge);

  const action = row.insertCell();
  if (service.url) {
    const open = document.createElement("a");
    open.className = "button";
    open.href = service.url;
    open.target = "_blank";
    open.rel = "noopener noreferrer";
    open.textContent = "Open";
    open.setAttribute("aria-label", `Open ${label(service)} on port ${service.port} in a new tab`);
    action.append(open);
  }
  return row;
}

function render() {
  const services = snapshot?.services || [];
  const query = search.value.trim().toLowerCase();
  const matches = services.filter((service) => (filter === "all" || filter === service.protocol)
    && `${label(service)} ${service.address} ${service.port} ${service.protocol}`.toLowerCase().includes(query));
  $("rows").replaceChildren(...matches.map(makeRow));
  $("directory").hidden = !matches.length;
  $("empty").hidden = !!matches.length;
  $("empty").textContent = !snapshot ? "Discovered services will appear here."
    : !services.length ? "No listeners responded over HTTP or HTTPS." : "No services match your search or filter.";
  $("total").textContent = snapshot ? services.length : "–";
  $("http").textContent = snapshot ? services.filter((service) => service.protocol === "http").length : "–";
  $("https").textContent = snapshot ? services.filter((service) => service.protocol === "https").length : "–";
  $("export").disabled = !services.some((service) => service.url);
  updateButtons();
}

function scanSummary() {
  const when = new Date(snapshot.scannedAt).toLocaleTimeString([], {hour: "numeric", minute: "2-digit"});
  return `${snapshot.checked} ${snapshot.checked === 1 ? "listener" : "listeners"} checked · ${when}`;
}

async function discover() {
  if (!connected || active || saving) return;
  status("Checking listening ports on this machine…");
  try {
    const message = await request("discover");
    if (!Array.isArray(message.services) || !Number.isInteger(message.checked)) {
      throw new Error("The helper returned an invalid discovery result.");
    }
    saving = true;
    snapshot = {services: validatedServices(message.services), checked: message.checked, scannedAt: Date.now()};
    render();
    try {
      await chrome.storage.local.set({snapshot});
      status(scanSummary());
    } catch {
      status("Discovery finished. Chrome couldn’t save the results for next time.", true);
    } finally {
      saving = false;
      updateButtons();
    }
  } catch (error) {
    if (error.name === "AbortError") {
      status("Discovery cancelled.");
    } else if (error.helperResponded) {
      status(error.message, true);
    } else {
      connection("missing", "Helper disconnected");
      setup.open = true;
      status("Discovery couldn’t finish. Check the helper connection and try again.", true);
      status(helperAdvice(error), true, $("setup-status"));
    }
  }
}

function updateInstaller() {
  const selection = platform.value;
  $("download").href = release + installers[selection];
  if (selection.startsWith("windows")) {
    $("install-instructions").textContent = "Open the downloaded installer and choose Install. You can remove the helper later from Windows Settings → Installed apps.";
    $("security-instructions").textContent = "This preview installer is unsigned. Windows may show a SmartScreen prompt. If you trust this GitHub release, choose More info → Run anyway.";
  } else if (selection.startsWith("macos")) {
    $("install-instructions").textContent = "Open the ZIP, then double-click Install Local Services Helper and choose Install. Keep the installer if you want to remove the helper later.";
    $("security-instructions").textContent = "This preview app is unsigned. If macOS blocks it and you trust this GitHub release, use System Settings → Privacy & Security → Open Anyway.";
  } else {
    $("install-instructions").textContent = "Open the .deb in your graphical package installer and choose Install. Your system may ask for your password.";
    $("security-instructions").textContent = "This package is for Debian and Ubuntu with Google Chrome or Chromium. A graphical installer that supports local .deb files is required.";
  }
}

async function pickPlatform() {
  const agent = navigator.userAgent;
  const os = /Windows/i.test(agent) ? "windows" : /Macintosh|Mac OS/i.test(agent) ? "macos" : "linux";
  platform.value = `${os}-${os === "macos" || /aarch64|arm64/i.test(agent) ? "arm64" : "amd64"}`;
  updateInstaller();
  try {
    const info = await navigator.userAgentData?.getHighEntropyValues(["architecture"]);
    const arch = info?.architecture === "arm" ? "arm64" : info?.architecture === "x86" ? "amd64" : "";
    if (arch && !platform.matches(":focus") && !platform.dataset.changed) platform.value = `${os}-${arch}`;
  } catch {
    // The selector remains available when architecture hints are disabled.
  }
  updateInstaller();
}

function exportResults() {
  const services = snapshot.services.filter((service) => service.url)
    .map((service) => ({name: label(service).slice(0, 120), url: service.url}));
  const object = URL.createObjectURL(new Blob([JSON.stringify({version: 1, services}, null, 2)], {type: "application/json"}));
  const link = document.createElement("a");
  link.href = object;
  link.download = "local-services.json";
  link.click();
  window.setTimeout(() => URL.revokeObjectURL(object), 1000);
}

async function clearResults() {
  if (active || saving) return;
  if (!window.confirm("Clear the saved discovery results?")) return;
  saving = true;
  updateButtons();
  try {
    await chrome.storage.local.remove("snapshot");
    snapshot = null;
    render();
    status("Saved results cleared.");
  } catch {
    status("Chrome couldn’t clear the saved results. Try again.", true);
  } finally {
    saving = false;
    updateButtons();
  }
}

platform.addEventListener("change", () => {
  platform.dataset.changed = "true";
  updateInstaller();
});
verifyButton.addEventListener("click", verify);
scanButton.addEventListener("click", discover);
cancelButton.addEventListener("click", () => {
  active?.cancel();
  scanButton.focus();
});
search.addEventListener("input", render);
filters.forEach((button) => button.addEventListener("click", () => {
  filter = button.dataset.filter;
  filters.forEach((item) => item.setAttribute("aria-pressed", item === button));
  render();
}));
$("export").addEventListener("click", exportResults);
$("clear").addEventListener("click", clearResults);

async function initialize() {
  void pickPlatform();
  try {
    const saved = (await chrome.storage.local.get("snapshot")).snapshot;
    if (saved && Number.isFinite(saved.scannedAt) && Number.isInteger(saved.checked)) {
      snapshot = {...saved, services: validatedServices(saved.services)};
      status(scanSummary());
    }
  } catch {
    // Discovery can still run without persisted results.
  }
  render();
  await verify();
}
void initialize();
