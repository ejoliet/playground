const launches = [
  {
    mission: "Starlink Group 10-4",
    window: "NET Oct 18 • 7:14 PM ET",
    vehicle: "Falcon 9 • Booster B1083",
    site: "SLC-40, Cape Canaveral",
    status: "Weather monitoring",
    details: "Next-gen Starlink satellites with optimized V2 mini stack.",
  },
  {
    mission: "USSF-52",
    window: "NET Oct 23 • 3:32 AM ET",
    vehicle: "Falcon Heavy • Boosters B1064/B1065",
    site: "LC-39A, Kennedy Space Center",
    status: "Payload encapsulated",
    details: "National security payload to geosynchronous transfer orbit.",
  },
  {
    mission: "Polaris Dawn",
    window: "NET Nov 2 • 6:05 AM ET",
    vehicle: "Falcon 9 • Crew Dragon Resilience",
    site: "LC-39A, Kennedy Space Center",
    status: "Crew training",
    details: "Commercial astronaut mission with EVA and laser comms demo.",
  },
  {
    mission: "Intuitive Machines IM-3",
    window: "NET Nov 17 • 9:42 PM ET",
    vehicle: "Falcon 9 • Booster B1077",
    site: "SLC-4E, Vandenberg",
    status: "Payload processing",
    details: "Lunar lander delivery with NASA CLPS payload suite.",
  },
  {
    mission: "Transporter-13",
    window: "NET Dec 1 • 1:20 PM ET",
    vehicle: "Falcon 9 • Booster B1080",
    site: "SLC-4E, Vandenberg",
    status: "Rideshare manifest",
    details: "Dedicated rideshare with 80+ smallsat customers.",
  },
  {
    mission: "Starship Flight Test 5",
    window: "Window opens Dec 12",
    vehicle: "Starship + Super Heavy",
    site: "Starbase, Texas",
    status: "FAA review",
    details: "Integrated test flight with targeted booster catch attempt.",
  },
];

const feedGrid = document.getElementById("feed-grid");

launches.forEach((launch) => {
  const card = document.createElement("article");
  card.className = "launch-card";
  card.innerHTML = `
    <span>${launch.window}</span>
    <h3>${launch.mission}</h3>
    <p>${launch.vehicle}</p>
    <p>${launch.site}</p>
    <p>${launch.details}</p>
    <div class="status-pill">${launch.status}</div>
  `;
  feedGrid.appendChild(card);
});

const form = document.getElementById("subscribe-form");
const statusMessage = document.getElementById("status-message");

form.addEventListener("submit", (event) => {
  event.preventDefault();
  const email = new FormData(form).get("email");
  statusMessage.textContent = `Thanks, ${email}! Your 1-month trial is active. We'll remind you before billing starts.`;
  form.reset();
});
