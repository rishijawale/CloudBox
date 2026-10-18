document.addEventListener("DOMContentLoaded", () => {
  const search = document.getElementById("file-search");
  if (search) {
    search.addEventListener("input", () => {
      const query = search.value.trim().toLowerCase();
      document.querySelectorAll(".searchable").forEach(row => {
        row.style.display = (row.dataset.search || "").includes(query) ? "" : "none";
      });
    });
  }
  const input = document.getElementById("file-input");
  const form = document.getElementById("upload-form");
  if (input && form) {
    input.addEventListener("change", () => {
      const label = document.querySelector(".upload-drop strong");
      if (label && input.files.length) label.textContent = `${input.files.length} file(s) selected`;
    });
    const drop = document.querySelector(".upload-drop");
    ["dragenter", "dragover"].forEach(eventName => drop.addEventListener(eventName, event => {
      event.preventDefault(); drop.classList.add("drag-active");
    }));
    ["dragleave", "drop"].forEach(eventName => drop.addEventListener(eventName, event => {
      event.preventDefault(); drop.classList.remove("drag-active");
    }));
    drop.addEventListener("drop", event => {
      if (event.dataTransfer.files.length) {
        input.files = event.dataTransfer.files;
        input.dispatchEvent(new Event("change"));
      }
    });
  }
  document.querySelectorAll("[data-copy]").forEach(button => {
    button.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(button.dataset.copy);
        button.textContent = "Copied!";
        setTimeout(() => button.textContent = "Copy", 1400);
      } catch {
        window.prompt("Copy this share link:", button.dataset.copy);
      }
    });
  });
});
