// static/js/app.js

document.addEventListener("DOMContentLoaded", () => {
  const startBtn     = document.getElementById("start-btn");
  const stopBtn      = document.getElementById("stop-btn");
  const runOnceBtn   = document.getElementById("run-once-btn");
  const prerollBtn   = document.getElementById("run-preroll-btn");
  const statusBadge  = document.getElementById("status-badge");
  const statusSpinner= document.getElementById("status-spinner");
  const lastRunEl    = document.getElementById("last-run");
  const nextRunEl    = document.getElementById("next-run");

  function refreshStatus() {
    if (!statusSpinner.classList.contains("d-none")) return;

    fetch("/run_state")
      .then(res => res.json())
      .then(data => {
        statusSpinner.classList.add("d-none");

        switch (data.state) {
          case "one-off":
            statusBadge.textContent = "One-Off…";
            statusBadge.className   = "badge bg-info";
            break;
          case "running":
            statusBadge.textContent = "Running";
            statusBadge.className   = "badge bg-success";
            break;
          case "waiting":
            statusBadge.textContent = "Waiting";
            statusBadge.className   = "badge bg-info";
            break;
          default:
            statusBadge.textContent = "Stopped";
            statusBadge.className   = "badge bg-secondary";
        }

        // Disable Run-Once button during one-off
        runOnceBtn.disabled = (data.state === "one-off");

        lastRunEl.textContent = data.last_run;
        nextRunEl.textContent = data.next_run;
      })
      .catch(console.error);
  }

  function refreshDashboard() {
    fetch("/dashboard_data")
      .then(r => r.json())
      .then(data => {
        document.getElementById("total-collections").textContent  = data.total_collections;
        document.getElementById("pinned-today").textContent       = data.pinned_today;
        document.getElementById("exclusions-active").textContent  = data.exclusions_active;
        document.getElementById("exemptions-count").textContent   = data.exemptions_count;

        document.getElementById("active-time-block").textContent   = data.active_time_block.join(", ") || "None";
        document.getElementById("library-limits").textContent     = data.library_limits.join(", ");
        document.getElementById("seasonal-blocks").textContent    = data.seasonal_blocks.join(", ") || "None";
        document.getElementById("pinned-collections").textContent = data.pinned_collections.join(", ") || "None";
        document.getElementById("current-roll").textContent       = data.current_roll || "None";
      })
      .catch(console.error);
  }

  // Button handlers
  startBtn.addEventListener("click", () => {
    fetch("/start", { method: "POST" }).then(refreshStatus).catch(console.error);
  });

  stopBtn.addEventListener("click", () => {
    fetch("/stop", { method: "POST" }).then(refreshStatus).catch(console.error);
  });

  runOnceBtn.addEventListener("click", () => {
    statusSpinner.classList.remove("d-none");
    statusBadge.textContent = "One-Off…";
    statusBadge.className   = "badge bg-info";
    runOnceBtn.disabled     = true;

    fetch("/run-once", { method: "POST" })
      .then(res => {
        if (!res.ok) throw new Error(`Status ${res.status}`);
        return res.json();
      })
      .then(() => {
        statusSpinner.classList.add("d-none");
        refreshStatus();
      })
      .catch(err => {
        console.error(err);
        statusSpinner.classList.add("d-none");
        statusBadge.textContent = "Error";
        statusBadge.className   = "badge bg-danger";
        runOnceBtn.disabled     = false;
      });
  });

  if (prerollBtn) {
    prerollBtn.addEventListener("click", () => {
      prerollBtn.disabled = true;
      const nextUrl = prerollBtn.dataset.next;
      fetch("/preroll/run", {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: new URLSearchParams({ next: nextUrl })
      })
        .then(() => { prerollBtn.disabled = false; location.reload(); })
        .catch(err => { console.error(err); prerollBtn.disabled = false; });
    });
  }

  // Initial + polling
  refreshStatus();
  refreshDashboard();
  setInterval(refreshStatus, 5000);
  setInterval(refreshDashboard, 10000);

  // Check for update banner
  checkForUpdate();
});

function checkForUpdate() {
  fetch("/update/check")
    .then(res => res.json())
    .then(data => {
      if (data.update_available) {
        const banner = document.getElementById("update-banner");
        banner.innerHTML = `
          New version ${data.latest_version} available!
          <a href="${data.release_url}" target="_blank" class="btn btn-sm btn-primary ms-2">
            View on GitHub
          </a>
        `;
        banner.classList.remove("d-none");
      }
    })
    .catch(err => console.error("Update check failed:", err));
}
