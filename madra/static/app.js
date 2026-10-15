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
    name.textContent = input.files.length > 1 ? input.files.length + " plików: " + [...input.files].map(f => f.name).join(", ") : file ? file.name : "Wybierz pliki lub przeciągnij je tutaj";
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
      for (const file of [...event.dataTransfer.files].slice(0, 6)) transfer.items.add(file);
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
function renderMath(root) {
  root.querySelectorAll('.math.inline, .math.block').forEach((node) => {
    if (window.katex && !node.dataset.mathRendered && node.textContent.length <= 4000) {
      katex.render(node.textContent, node, {displayMode: node.classList.contains('block'), throwOnError: false, trust: false, maxExpand: 1000, maxSize: 10});
      node.dataset.mathRendered = '1';
    }
  });
}
renderMath(document);

// Serialize autosaves and final submits; a stale tab cannot overwrite a newer draft.
document.querySelectorAll('form[data-autosave]').forEach((form) => {
  let dirty = false, pending = null, timer, blocked = false, submitting = false;
  const status = form.querySelector('[data-save-status]');
  const revision = form.elements.namedItem('revision') || form.elements.namedItem('draft_revision');
  const say = (message) => { if (status) status.textContent = message; };
  async function flush() {
    clearTimeout(timer);
    if (blocked) return false;
    if (pending) { await pending; if (blocked) return false; }
    if (!dirty) return true;
    const data = new FormData(form);
    dirty = false;
    pending = (async () => {
      try {
        const response = await fetch(form.dataset.autosave, { method: 'POST', body: data, credentials: 'same-origin', headers: { 'Accept': 'application/json' } });
        if (!response.ok || !response.headers.get('Content-Type')?.includes('application/json')) {
          if (response.status === 409) {
            blocked = true;
            throw new Error('Istnieje nowszy zapis. Skopiuj swój tekst i odśwież stronę przed dalszą pracą.');
          }
          throw new Error('Szkic nie został zapisany. Zachowaj tę stronę, sprawdź połączenie i wybierz „Ponów zapis”.');
        }
        const result = await response.json();
        if (revision) revision.value = result.revision;
        retry.hidden = true;
        say(dirty ? 'Zapisywanie kolejnych zmian…' : 'Szkic zapisany.');
        return true;
      } catch (error) {
        dirty = true; retry.hidden = false; say(error.message);
        return false;
      }
    })();
    const ok = await pending;
    pending = null;
    if (ok && dirty) return flush();
    return ok;
  }
  const changed = () => {
    if (submitting) return;
    dirty = true; say('Niezapisane zmiany…'); clearTimeout(timer);
    timer = setTimeout(flush, 650);
  };
  form.addEventListener('input', changed);
  form.addEventListener('change', changed);
  form.addEventListener('submit', async (event) => {
    if (submitting) return;
    event.preventDefault();
    const button = event.submitter;
    if (!await flush()) return;
    submitting = true;
    setTimeout(() => form.requestSubmit(button || undefined), 0);
  });
  const retry = document.createElement('button');
  retry.hidden = true; retry.type = 'button'; retry.className = 'text-button small'; retry.textContent = 'Ponów zapis';
  retry.addEventListener('click', flush);
  status?.after(retry);
  document.querySelectorAll('[data-study-hint]').forEach((hint) => {
    hint.addEventListener('toggle', () => {
      if (hint.open && form.elements.namedItem('used_help')) {
        form.elements.namedItem('used_help').value = '1'; changed();
      }
    });
  });
  window.addEventListener('beforeunload', (event) => {
    if ((dirty || pending) && !submitting) { event.preventDefault(); event.returnValue = ''; }
  });
  document.addEventListener('click', async (event) => {
    const link = event.target.closest('a[href]');
    if (!link || link.target === '_blank' || link.download || event.ctrlKey || event.metaKey || event.shiftKey) return;
    const url = new URL(link.href, location.href);
    if (url.pathname === location.pathname && url.search === location.search) return;
    if (dirty || pending) {
      event.preventDefault();
      if (await flush()) location.assign(url.href);
    }
  });
});

const studyMode = document.querySelector('[data-study-mode]');
if (studyMode) {
  const fieldset = document.querySelector('[data-exam-settings]');
  const update = () => {
    fieldset.hidden = studyMode.value !== 'exam';
    fieldset.disabled = studyMode.value !== 'exam';
    const budget = studyMode.form.querySelector('[data-regular-budget]');
    if (budget) { budget.hidden = studyMode.value === 'exam'; budget.querySelector('input').disabled = studyMode.value === 'exam'; }
    const repeat = studyMode.form.querySelector('[data-repeat-setting]');
    if (repeat) { repeat.hidden = studyMode.value !== 'regular'; repeat.querySelector('input').disabled = studyMode.value !== 'regular'; }
  };
  studyMode.addEventListener('change', update); update();
}
const sourceSelect = document.querySelector('select[name="material_id"]');
const chapterSelect = document.querySelector('[data-source-chapters]');
if (sourceSelect && chapterSelect) {
  const update = () => {
    for (const option of chapterSelect.options) {
      if (!option.dataset.material) continue;
      option.hidden = option.disabled = option.dataset.material !== sourceSelect.value;
    }
    if (chapterSelect.selectedOptions[0]?.disabled) chapterSelect.value = '0';
  };
  sourceSelect.addEventListener('change', update); update();
}
const correctOptions = document.querySelector('[data-correct-options]');
if (correctOptions) {
  const optionsInput = document.querySelector('textarea[name="options"]');
  const answerInput = document.querySelector('textarea[name="answer"]');
  const answerLabel = answerInput.closest('label');
  const update = () => {
    const previous = correctOptions.querySelector('input:checked')?.dataset.answer || answerInput.value.trim();
    correctOptions.replaceChildren();
    const quiz = kindSelect.value === 'quiz';
    answerLabel.hidden = quiz;
    answerInput.required = !quiz;
    if (!quiz) return;
    optionsInput.value.split('\n').forEach((text, index) => {
      if (!text.trim()) return;
      const label = document.createElement('label'); label.className = 'check-row';
      const input = document.createElement('input'); input.type = 'radio'; input.name = 'correct_option';
      input.value = index; input.dataset.answer = text.trim(); input.required = true; input.checked = text.trim() === previous;
      input.addEventListener('change', () => { answerInput.value = text.trim(); });
      label.append(input, document.createTextNode(text.trim())); correctOptions.append(label);
    });
  };
  optionsInput.addEventListener('input', update); kindSelect.addEventListener('change', update); update();
}
const reading = document.querySelector('[data-reading-url]');
if (reading) {
  const links = reading.querySelectorAll('.chapter-toc a');
  if (!location.hash && Number(reading.dataset.lastChapter) > 0) links[Number(reading.dataset.lastChapter) - 1]?.click();
  links.forEach((link, index) => link.addEventListener('click', () => {
    const data = new FormData();
    data.set('chapter', index + 1); data.set('csrf_token', reading.querySelector('[name="csrf_token"]').value);
    fetch(reading.dataset.readingUrl, { method: 'POST', body: data, credentials: 'same-origin' }).catch(() => {});
  }));
}
const clock = document.querySelector('[data-exam-clock]');
if (clock) {
  const deadline = Date.parse(clock.dataset.start) + Number(clock.dataset.minutes) * 60000;
  const update = () => {
    const seconds = Math.max(0, Math.ceil((deadline - Date.now()) / 1000));
    clock.textContent = seconds ? 'Pozostało ' + Math.floor(seconds / 60) + ':' + String(seconds % 60).padStart(2, '0') + ' · przerwa nie zatrzymuje zegara' : 'Planowany czas minął. Zakończ sprawdzian, gdy będziesz gotowy.';
  };
  update(); setInterval(update, 1000);
}

const goalWorkspace = document.querySelector('.goal-form select[name="workspace_id"]');
if (goalWorkspace) {
  const update = () => document.querySelectorAll('[data-goal-workspace]').forEach((row) => {
    const enabled = row.dataset.goalWorkspace === goalWorkspace.value;
    row.hidden = !enabled;
    row.querySelectorAll('input, select').forEach((field) => { field.disabled = !enabled; });
  });
  goalWorkspace.addEventListener('change', update); update();
}

// Exercise lists remain complete and usable if JavaScript is unavailable.
document.querySelectorAll('[data-exercise-browser]').forEach((browser) => {
  const rows = [...browser.querySelectorAll('[data-exercise-row]')];
  const search = browser.querySelector('[data-exercise-search]');
  const kind = browser.querySelector('[data-exercise-kind-filter]');
  const state = browser.querySelector('[data-exercise-state-filter]');
  const normalize = (value) => value.toLocaleLowerCase('pl').normalize('NFD').replace(/[\u0300-\u036f]/g, '');
  const filter = () => {
    const query = normalize(search.value.trim());
    for (const row of rows) {
      const text = row.querySelector('[data-exercise-search-text]').textContent;
      row.hidden = Boolean((kind.value && row.dataset.exerciseKind !== kind.value) || (state?.value && row.dataset.exerciseState !== state.value) || (query && !normalize(text).includes(query)));
    }
    const count = rows.filter((row) => !row.hidden).length;
    browser.querySelector('[data-exercise-count]').textContent = 'Widoczne pytania: ' + count + ' z ' + rows.length;
    browser.querySelector('[data-exercise-empty]').hidden = count !== 0;
  };
  browser.querySelector('[data-exercise-controls]').hidden = false;
  search.addEventListener('input', filter);
  kind.addEventListener('change', filter);
  state?.addEventListener('change', filter);
  browser.querySelectorAll('[data-select-visible]').forEach((button) => {
    button.hidden = false;
    button.addEventListener('click', () => {
      rows.filter((row) => !row.hidden).forEach((row) => {
        const input = row.querySelector('input[name="selected"]');
        if (input) input.checked = button.dataset.selectVisible === 'all';
      });
      browser.dispatchEvent(new Event('change', {bubbles:true}));
    });
  });
  filter();
});

document.querySelectorAll('[data-exercise-selection-form]').forEach((form) => {
  const inputs = [...form.querySelectorAll('input[name="selected"]')];
  const note = form.querySelector('input[name="save_note"]');
  const count = form.querySelector('[data-selected-count]');
  const button = form.querySelector('[data-save-selected]');
  const update = () => {
    const selected = inputs.filter((input) => input.checked).length;
    count.textContent = 'Wybrane: ' + selected + ' z ' + inputs.length;
    button.textContent = 'Zapisz ćwiczenia (' + selected + ')' + (note?.checked ? ' i notatkę' : '');
    button.disabled = selected === 0 && !note?.checked;
  };
  let dirty = false, submitting = false;
  form.addEventListener('input', () => { dirty = true; });
  form.addEventListener('change', () => { dirty = true; update(); });
  form.addEventListener('submit', () => { submitting = true; });
  window.addEventListener('beforeunload', (event) => {
    if (dirty && !submitting) { event.preventDefault(); event.returnValue = ''; }
  });
  update();
});

document.querySelectorAll('[data-preview-url]').forEach((row) => {
  const index = row.dataset.exerciseIndex;
  const editor = row.querySelector('.exercise-edit');
  const button = row.querySelector('[data-refresh-preview]');
  const status = row.querySelector('[data-preview-status]');
  let revision = 0, dirty = false, pending = false;
  const refresh = async () => {
    if (!dirty || pending) return;
    const version = revision;
    const data = new FormData();
    data.set('csrf_token', row.closest('form').elements.csrf_token.value);
    data.set('index', index);
    for (const key of ['prompt', 'options', 'answer', 'explanation', 'rubric']) {
      const field = row.querySelector('[name="' + key + '_' + index + '"]');
      if (field) data.set(key, field.value);
    }
    pending = true; status.textContent = 'Odświeżanie podglądu…';
    try {
      const response = await fetch(row.dataset.previewUrl, {method:'POST', body:data, credentials:'same-origin'});
      if (!response.ok || !response.headers.get('Content-Type')?.includes('text/html')) throw new Error();
      const html = await response.text();
      if (version !== revision) { status.textContent = 'Wprowadzono kolejne zmiany. Odśwież podgląd.'; return; }
      // Only owner-checked, safely rendered HTML from this application's preview endpoint.
      const target = row.querySelector('[data-exercise-preview]');
      target.innerHTML = html;
      row.querySelector('[data-exercise-search-text]').innerHTML = target.querySelector('.exercise-prompt').innerHTML;
      renderMath(row);
      dirty = false; status.textContent = 'Podgląd aktualny. Zmiany zapiszesz razem z zestawem.';
    } catch {
      status.textContent = 'Nie udało się odświeżyć podglądu. Zmiany w formularzu pozostają. Spróbuj ponownie.';
    } finally { pending = false; }
  };
  editor.addEventListener('input', () => { revision += 1; dirty = true; status.textContent = 'Zmieniono treść. Odśwież podgląd lub zamknij edycję.'; });
  editor.addEventListener('toggle', () => { if (!editor.open) refresh(); });
  button.hidden = false; button.addEventListener('click', refresh);
});

document.querySelectorAll('[data-response-mode]').forEach((select) => {
  const form = select.closest('form');
  const text = form.querySelector('[data-text-response]');
  const instruction = form.querySelector('[data-response-instruction]');
  const update = () => {
    if (text) text.hidden = select.value !== 'text';
    if (instruction) instruction.hidden = select.value === 'text';
  };
  select.addEventListener('change', update); update();
});
