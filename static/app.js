const form = document.getElementById("download-form");
const input = document.getElementById("url");
const button = document.getElementById("download-btn");
const statusBox = document.getElementById("status");

function showStatus(message, kind = "info") {
  statusBox.textContent = message;
  statusBox.className = `status show ${kind}`;
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const url = input.value.trim();
  if (!url) {
    showStatus("Paste a YouTube video URL first.", "error");
    return;
  }

  button.disabled = true;
  button.querySelector("span:first-child").textContent = "Preparing…";
  showStatus("Preparing your file. This can take a while, especially on free hosting.");

  try {
    const response = await fetch("/api/download", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url })
    });

    const contentType = response.headers.get("content-type") || "";
    if (!response.ok || contentType.includes("application/json")) {
      const result = await response.json().catch(() => ({}));
      throw new Error(result.error || "The download could not be prepared.");
    }

    const blob = await response.blob();
    const disposition = response.headers.get("content-disposition") || "";
    const match = disposition.match(/filename="?([^";]+)"?/i);
    const filename = match ? match[1] : "youtube-video.mp4";
    const objectUrl = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = objectUrl;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(objectUrl);
    showStatus("The file was sent to your browser. Check your Downloads folder or browser download prompt.");
  } catch (error) {
    showStatus(error.message || "Something went wrong. Please try again.", "error");
  } finally {
    button.disabled = false;
    button.querySelector("span:first-child").textContent = "Download";
  }
});
