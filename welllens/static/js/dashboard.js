// Dashboard charts. Reads pre-computed data from the server (no math here).
(function () {
  var el = document.getElementById("chart-data");
  if (!el || typeof Chart === "undefined") return;
  var data = JSON.parse(el.textContent);

  var ink = "#2A2D25", green = "#41613A", line = "#DCD5C6", label = "#837F6E";
  Chart.defaults.font.family = "Inter, system-ui, sans-serif";
  Chart.defaults.color = label;

  var weekly = document.getElementById("weeklyChart");
  if (weekly && data.weekly_km && data.weekly_km.length) {
    new Chart(weekly, {
      type: "bar",
      data: {
        labels: data.weekly_labels,
        datasets: [{
          label: "Distance (km)",
          data: data.weekly_km,
          backgroundColor: green,
          borderRadius: 8,
          maxBarThickness: 38
        }]
      },
      options: {
        plugins: { legend: { display: false } },
        scales: {
          y: { beginAtZero: true, grid: { color: line }, ticks: { color: label } },
          x: { grid: { display: false }, ticks: { color: label } }
        }
      }
    });
  }

  var pace = document.getElementById("paceChart");
  if (pace && data.pace_values && data.pace_values.length) {
    new Chart(pace, {
      type: "line",
      data: {
        labels: data.pace_labels,
        datasets: [{
          label: "Pace (min/km)",
          data: data.pace_values,
          borderColor: green,
          backgroundColor: "rgba(65,97,58,.12)",
          fill: true,
          tension: 0.3,
          pointRadius: 3,
          pointBackgroundColor: green
        }]
      },
      options: {
        plugins: { legend: { display: false } },
        scales: {
          // Lower min/km is faster — invert so "up" reads as "faster".
          y: { reverse: true, grid: { color: line }, ticks: { color: label } },
          x: { grid: { display: false }, ticks: { color: label } }
        }
      }
    });
  }
})();
