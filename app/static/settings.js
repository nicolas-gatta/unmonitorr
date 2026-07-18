document.querySelectorAll(".test-btn").forEach((btn) => {
  btn.addEventListener("click", async () => {
    const service = btn.dataset.service; // "radarr" or "sonarr"
    const url = document.getElementById(`${service}_url`).value.trim();
    const apiKey = document.getElementById(`${service}_api_key`).value.trim();
    const resultEl = document.getElementById(`${service}-result`);

    resultEl.textContent = "Testing...";
    resultEl.className = "test-result";
    btn.disabled = true;

    try {
      const resp = await fetch(`/settings/test-${service}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url, api_key: apiKey }),
      });
      const data = await resp.json();

      if (data.ok) {
        resultEl.textContent = `Connected (Radarr/Sonarr v${data.version})`;
        resultEl.className = "test-result ok";
      } else {
        resultEl.textContent = `Failed: ${data.error}`;
        resultEl.className = "test-result fail";
      }
    } catch (err) {
      resultEl.textContent = `Failed: ${err}`;
      resultEl.className = "test-result fail";
    } finally {
      btn.disabled = false;
    }
  });
});