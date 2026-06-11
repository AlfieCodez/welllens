// Register the WellLens service worker (served at root scope via /sw.js).
if ("serviceWorker" in navigator) {
  window.addEventListener("load", function () {
    navigator.serviceWorker.register("/sw.js", { scope: "/" }).catch(function (err) {
      console.warn("WellLens SW registration failed:", err);
    });
  });
}
