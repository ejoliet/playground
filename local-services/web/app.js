"use strict";

const total = document.querySelector("#total");
const httpCount = document.querySelector("#http-count");
const httpsCount = document.querySelector("#https-count");
const scanStatus = document.querySelector("#scan-status");
const search = document.querySelector("#search");
const filterButtons = document.querySelectorAll("[data-filter]");
const rescan = document.querySelector("#rescan");
const results = document.querySelector("#results");
const table = document.querySelector("#services");
const rows = document.querySelector("#rows");
const empty = document.querySelector("#empty");

let snapshot;
let selectedProtocol = "all";
let scanError = "";

function serviceName(service) {
  if (service.server === "Local Services") return service.server;
  return service.process || service.server || "Web service";
}

function render() {
  const query = search.value.trim().toLowerCase();
  const matching = (snapshot?.services || []).filter((service) => {
    const searchable = [serviceName(service), service.port, service.protocol,
      service.url, service.server, ...service.binds].join(" ").toLowerCase();
    return (selectedProtocol === "all" || selectedProtocol === service.protocol)
      && searchable.includes(query);
  });

  const newRows = matching.map((service) => {
    const row = document.createElement("tr");
    const name = row.insertCell();
    const title = document.createElement("span");
    title.className = "service-name";
    title.textContent = serviceName(service);
    const meta = document.createElement("span");
    meta.className = "service-meta";
    meta.textContent = `Status ${service.status}`;
    name.append(title, meta);

    const port = row.insertCell();
    port.className = "port";
    port.textContent = service.port;

    const badge = document.createElement("span");
    badge.className = `protocol ${service.protocol}`;
    badge.textContent = service.protocol.toUpperCase();
    row.insertCell().append(badge);

    const address = row.insertCell();
    address.className = "address";
    address.textContent = service.address;
    address.title = `Listening on ${service.binds.join(", ")}`;

    const link = document.createElement("a");
    link.className = "open";
    // A wildcard-bound service is reachable at whatever name reached this dashboard.
    const url = new URL(service.url);
    if (service.binds.some((bind) => bind === "0.0.0.0" || bind === "::")) url.hostname = location.hostname;
    link.href = url.href;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.textContent = "Open";
    link.setAttribute("aria-label", `Open ${serviceName(service)} on port ${service.port} in a new tab`);
    row.insertCell().append(link);
    return row;
  });

  rows.replaceChildren(...newRows);
  table.hidden = newRows.length === 0;
  empty.hidden = newRows.length > 0;
  if (!snapshot) {
    empty.textContent = scanError || "Scanning for HTTP and HTTPS services…";
  } else if (!snapshot.services.length) {
    empty.textContent = "No HTTP or HTTPS services responded.";
  } else if (!newRows.length) {
    empty.textContent = "No services match your search or filter.";
  }
}

async function scan() {
  rescan.disabled = true;
  results.setAttribute("aria-busy", "true");
  scanStatus.textContent = "Checking local listeners…";
  scanError = "";
  render();
  try {
    const response = await fetch("/api/services", {cache: "no-store"});
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || "Scan unavailable.");
    snapshot = payload;
    total.textContent = snapshot.services.length;
    httpCount.textContent = snapshot.services.filter((service) => service.protocol === "http").length;
    httpsCount.textContent = snapshot.services.filter((service) => service.protocol === "https").length;
    const time = new Date(snapshot.scannedAt).toLocaleTimeString([], {hour: "numeric", minute: "2-digit", second: "2-digit"});
    const listenerWord = snapshot.checked === 1 ? "listener" : "listeners";
    scanStatus.textContent = `${snapshot.checked} ${listenerWord} checked · ${time}`;
  } catch (error) {
    scanError = error.message || "Scan unavailable.";
    scanStatus.textContent = snapshot ? "Scan failed. Showing the previous results." : "Scan failed.";
  } finally {
    rescan.disabled = false;
    results.setAttribute("aria-busy", "false");
    render();
  }
}

search.addEventListener("input", render);
rescan.addEventListener("click", scan);
filterButtons.forEach((button) => button.addEventListener("click", () => {
  selectedProtocol = button.dataset.filter;
  filterButtons.forEach((item) => item.setAttribute("aria-pressed", item === button));
  render();
}));

scan();
