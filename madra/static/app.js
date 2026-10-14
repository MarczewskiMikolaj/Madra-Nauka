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
document.querySelectorAll("[data-file-picker]").forEach((picker) => {
  const input = picker.querySelector('input[type="file"]');
  const name = picker.querySelector("[data-picker-name]");
  const emptyName = name.textContent;
  const update = () => {
    name.textContent = input.files[0]?.name || emptyName;
  };
  input.addEventListener("change", update);
  input.form?.addEventListener("reset", () => {
    name.textContent = emptyName;
  });
  update();
});
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

// Tabs and chapter navigation share URL hashes, so links and browser Back work.
function selectMaterialPane(group, pane) {
  group.querySelectorAll('[data-tab-pane]').forEach((item) => {
    if (item.closest('[data-tab-group]') === group) item.hidden = item !== pane;
  });
  group.querySelectorAll('[data-pane-link]').forEach((link) => {
    const selected = link.hash === '#' + pane.id;
    link.setAttribute('aria-selected', String(selected));
    link.tabIndex = selected ? 0 : -1;
  });
}
function selectNoteChapter(reader, chapter) {
  reader.querySelectorAll('.note-chapter').forEach((item) => { item.hidden = item !== chapter; });
  reader.querySelectorAll('.chapter-toc a').forEach((link) => {
    if (link.hash === '#' + chapter.id) link.setAttribute('aria-current', 'step');
    else link.removeAttribute('aria-current');
  });
}
function revealStudyTarget() {
  if (!location.hash) {
    document.querySelectorAll('[data-tab-group]').forEach((group) => {
      selectMaterialPane(group, group.querySelector('[data-tab-pane]'));
    });
    document.querySelectorAll('.chapter-reader').forEach((reader) => {
      const first = reader.querySelector('.note-chapter');
      if (first) selectNoteChapter(reader, first);
    });
    return;
  }
  const target = document.getElementById(location.hash.slice(1));
  if (!target) return;
  const pane = target.closest('[data-tab-pane]');
  if (pane) selectMaterialPane(pane.closest('[data-tab-group]'), pane);
  const reader = target.closest('.chapter-reader');
  if (reader && target.classList.contains('note-chapter')) selectNoteChapter(reader, target);
}
document.querySelectorAll('[data-tab-group]').forEach((group) => {
  const nav = group.querySelector('[data-tab-nav]');
  nav.setAttribute('role', 'tablist');
  const links = [...nav.querySelectorAll('[data-pane-link]')];
  links.forEach((link, index) => {
    const pane = document.getElementById(link.hash.slice(1));
    link.id = pane.id + '-tab';
    link.setAttribute('role', 'tab');
    link.setAttribute('aria-controls', pane.id);
    pane.setAttribute('role', 'tabpanel');
    pane.setAttribute('aria-labelledby', link.id);
    link.addEventListener('click', () => selectMaterialPane(group, pane));
    link.addEventListener('keydown', (event) => {
      let next;
      if (event.key === 'ArrowRight') next = (index + 1) % links.length;
      if (event.key === 'ArrowLeft') next = (index + links.length - 1) % links.length;
      if (event.key === 'Home') next = 0;
      if (event.key === 'End') next = links.length - 1;
      if (next !== undefined) {
        event.preventDefault();
        links[next].focus();
        links[next].click();
      }
    });
  });
  selectMaterialPane(group, group.querySelector('[data-tab-pane]'));
  group.addEventListener('invalid', (event) => {
    const pane = event.target.closest('[data-tab-pane]');
    if (pane) selectMaterialPane(group, pane);
    const details = event.target.closest('details');
    if (details) details.open = true;
  }, true);
});
document.querySelectorAll('.chapter-reader').forEach((reader) => {
  const first = reader.querySelector('.note-chapter');
  if (first) selectNoteChapter(reader, first);
  reader.querySelectorAll('.chapter-toc a').forEach((link) => {
    link.addEventListener('click', () => {
      const chapter = document.getElementById(link.hash.slice(1));
      if (chapter) selectNoteChapter(reader, chapter);
    });
  });
});
window.addEventListener('hashchange', revealStudyTarget);
revealStudyTarget();

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

// Formula nodes contain escaped TeX produced by the server-side Markdown parser.
document.querySelectorAll('.math.inline, .math.block').forEach((node) => {
  if (window.katex && node.textContent.length <= 4000) {
    katex.render(node.textContent, node, {displayMode: node.classList.contains('block'), throwOnError: false, trust: false, maxExpand: 1000, maxSize: 10});
  }
});
