(() => {
  const root = document.querySelector("[data-trace-viewer-root]");
  const viewer = window.MinAgentTraceViewer.create({ root });

  if (!("EventSource" in window)) {
    viewer.setConnectionStatus("unsupported");
    return;
  }

  const stream = new EventSource("/events");
  stream.onmessage = (message) => viewer.applyEvent(JSON.parse(message.data));
  stream.onerror = () => {
    const status = root.querySelector("#run-status").textContent;
    if (!["completed", "failed", "interrupted"].includes(status)) {
      viewer.setConnectionStatus("reconnecting");
    }
  };
  window.addEventListener("beforeunload", () => stream.close(), { once: true });
})();
