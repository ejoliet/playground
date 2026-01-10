const API_BASE = "https://api.spacexdata.com/v4/launches";
const feedGrid = document.getElementById("feed-grid");
const feedTitle = document.getElementById("feed-title");
const feedSummary = document.getElementById("feed-summary");
const loginButton = document.getElementById("login-button");
const loginStatus = document.getElementById("login-status");

const formatDate = (dateString) => {
  const date = new Date(dateString);
  return date.toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
  });
};

const getStatusLabel = (launch) => {
  if (launch.upcoming) {
    return "Upcoming";
  }

  if (launch.success === true) {
    return "Success";
  }

  if (launch.success === false) {
    return "Failed";
  }

  return "Completed";
};

const renderLaunches = (launches) => {
  feedGrid.innerHTML = "";

  launches.forEach((launch) => {
    const card = document.createElement("article");
    card.className = "launch-card";
    const details = launch.details || "Mission details will post after recovery analysis.";
    const statusLabel = getStatusLabel(launch);

    card.innerHTML = `
      <span>${formatDate(launch.date_utc)}</span>
      <h3>${launch.name}</h3>
      <p>${details}</p>
      <div class="status-pill">${statusLabel}</div>
    `;

    feedGrid.appendChild(card);
  });
};

const sortByDateDesc = (launches) =>
  launches
    .slice()
    .sort((a, b) => new Date(b.date_utc) - new Date(a.date_utc));

const sortByDateAsc = (launches) =>
  launches
    .slice()
    .sort((a, b) => new Date(a.date_utc) - new Date(b.date_utc));

const fetchLaunches = async (type) => {
  const response = await fetch(`${API_BASE}/${type}`);
  if (!response.ok) {
    throw new Error("Unable to load launch data.");
  }
  return response.json();
};

const loadPastLaunches = async () => {
  feedTitle.textContent = "Recent SpaceX launches";
  feedSummary.textContent = "A quick look at the latest completed missions.";
  loginStatus.textContent = "Loading past launches...";

  try {
    const pastLaunches = await fetchLaunches("past");
    const recentPast = sortByDateDesc(pastLaunches).slice(0, 6);
    renderLaunches(recentPast);
    loginStatus.textContent = "Viewing recent past launches.";
  } catch (error) {
    loginStatus.textContent = "Unable to load launches right now.";
  }
};

const loadCombinedLaunches = async () => {
  feedTitle.textContent = "Past and upcoming SpaceX launches";
  feedSummary.textContent = "Upcoming windows are now added alongside recent mission history.";
  loginStatus.textContent = "Loading full launch feed...";

  try {
    const [pastLaunches, upcomingLaunches] = await Promise.all([
      fetchLaunches("past"),
      fetchLaunches("upcoming"),
    ]);

    const recentPast = sortByDateDesc(pastLaunches).slice(0, 4);
    const soonUpcoming = sortByDateAsc(upcomingLaunches).slice(0, 4);
    renderLaunches([...soonUpcoming, ...recentPast]);
    loginStatus.textContent = "Logged in. Feed updated with past and future launches.";
  } catch (error) {
    loginStatus.textContent = "Unable to update the feed right now.";
  }
};

loginButton.addEventListener("click", () => {
  loginButton.disabled = true;
  loginButton.textContent = "Logged in";
  loadCombinedLaunches();
});

loadPastLaunches();
