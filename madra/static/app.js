// Progressive enhancement: all core flows work through ordinary HTML forms.
const kindSelect = document.getElementById("activity-kind");
if (kindSelect) {
  const hints = {
    flashcard:
      "Najpierw przypomnij sobie odpowiedź, potem odkryj drugą stronę. Ćwiczy zapamiętanie.",
    open: "Wyjaśnij temat własnymi słowami i porównaj odpowiedź ze wzorcem. Ćwiczy zrozumienie.",
    quiz: "Wybierz jedną z 2–6 opcji. Poprawność sprawdzi aplikacja. Ćwiczy zrozumienie.",
    exercise:
      "Zastosuj wiedzę w praktyce. Wzorzec może zawierać kod lub rozwiązanie krok po kroku.",
    cloze:
      "Wstaw [...] w miejscu jednej luki. W odpowiedzi zapisz brakujące słowo lub wyrażenie.",
  };
  function updateKind() {
    document.getElementById("quiz-options").hidden =
      kindSelect.value !== "quiz";
    document.getElementById("kind-hint").textContent = hints[kindSelect.value];
  }
  kindSelect.addEventListener("change", updateKind);
  updateKind();
}
document.querySelectorAll("form[data-confirm]").forEach((form) => {
  form.addEventListener("submit", (event) => {
    if (!window.confirm(form.dataset.confirm)) event.preventDefault();
  });
});
// Retire the old worker: its shared HTML cache could mix accounts on one device.
if ("serviceWorker" in navigator) {
  navigator.serviceWorker
    .getRegistrations()
    .then((registrations) => {
      for (const registration of registrations) {
        const worker =
          registration.active ||
          registration.waiting ||
          registration.installing;
        if (
          worker &&
          new URL(worker.scriptURL).pathname === "/service-worker.js"
        )
          registration.unregister();
      }
    })
    .catch(() => {});
}
if ("caches" in window) {
  caches
    .keys()
    .then((keys) =>
      Promise.all(
        keys
          .filter((key) => key.startsWith("fiszki-"))
          .map((key) => caches.delete(key)),
      ),
    )
    .catch(() => {});
}

const fileDrop = document.querySelector("[data-file-drop]");
if (fileDrop) {
  const input = fileDrop.querySelector('input[type="file"]');
  const name = fileDrop.querySelector("[data-file-name]");
  const description = fileDrop.querySelector("[data-file-description]");
  function showFile() {
    const file = input.files[0];
    name.textContent = file ? file.name : "Wybierz plik lub przeciągnij go tutaj";
    description.textContent = file
      ? `${file.size < 1024 * 1024 ? (file.size / 1024).toFixed(1) + " KB" : (file.size / 1024 / 1024).toFixed(1) + " MB"} · Gotowy do wgrania`
      : "Notatki, dokument lub podręcznik";
  }
  description.setAttribute("aria-live", "polite");
  input.addEventListener("change", showFile);
  fileDrop.addEventListener("dragover", (event) => {
    event.preventDefault();
    fileDrop.classList.add("dragging");
  });
  fileDrop.addEventListener("dragleave", () => fileDrop.classList.remove("dragging"));
  fileDrop.addEventListener("drop", (event) => {
    event.preventDefault();
    fileDrop.classList.remove("dragging");
    if (event.dataTransfer.files.length) {
      const transfer = new DataTransfer();
      transfer.items.add(event.dataTransfer.files[0]);
      input.files = transfer.files;
      showFile();
    }
  });
}

// Category selection changes only the save checkboxes; original field indexes stay intact.
document.querySelectorAll("[data-select-group]").forEach((button) => {
  button.addEventListener("click", () => {
    button.closest(".result-group").querySelectorAll('input[name="selected"]').forEach((input) => {
      input.checked = button.dataset.selectGroup === "all";
    });
  });
});

// A table-of-contents link opens its chapter, including on direct hash navigation.
function revealNoteChapter() {
  const target = document.getElementById(location.hash.slice(1));
  if (target && target.classList.contains("note-chapter")) target.open = true;
}
window.addEventListener("hashchange", revealNoteChapter);
revealNoteChapter();

document.querySelectorAll('.chapter-toc a').forEach((link) => {
  link.addEventListener('click', () => {
    const chapter = document.getElementById(link.hash.slice(1));
    if (chapter) chapter.open = true;
  });
});

const cloudCallback = document.getElementById("cloud-oauth-callback");
if (cloudCallback) {
  const params = new URLSearchParams(location.hash.slice(1));
  history.replaceState(null, "", location.pathname);
  if (params.get("state") && (params.get("code") || params.get("error"))) {
    for (const key of ["code", "state", "client_id", "error"]) cloudCallback.elements[key].value = params.get(key) || "";
    cloudCallback.requestSubmit();
  } else {
    document.getElementById("callback-status").textContent = "Brak odpowiedzi logowania. Wróć do Połączenia AI i spróbuj ponownie.";
  }
}
