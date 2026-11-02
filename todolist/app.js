(() => {
  'use strict';

  const PREFIX = 'todo:v1:';
  const SETTINGS_KEY = PREFIX + 'settings';
  const DATE_KEY_RE = /^todo:v1:(\d{4}-\d{2}-\d{2})$/;
  const REMOVE_DELAY = 150;

  // ---------------------------------------------------------------------------
  // storage: localStorage 래퍼. 쓸 수 없으면 메모리에 보관하고 failed 표시
  // ---------------------------------------------------------------------------
  const storage = (() => {
    const memory = new Map();
    let failed = false;

    try {
      const probe = PREFIX + '__probe';
      localStorage.setItem(probe, '1');
      localStorage.removeItem(probe);
    } catch {
      failed = true;
    }

    function load(key, fallback) {
      try {
        const raw = memory.has(key) ? memory.get(key) : localStorage.getItem(key);
        return raw == null ? fallback : JSON.parse(raw);
      } catch {
        return fallback;
      }
    }

    function save(key, value) {
      const raw = JSON.stringify(value);
      if (!failed) {
        try {
          localStorage.setItem(key, raw);
          return;
        } catch {
          failed = true;
        }
      }
      memory.set(key, raw);
    }

    // 저장된 날짜 키 목록 (오름차순)
    function dateKeys() {
      const keys = new Set(memory.keys());
      try {
        for (let i = 0; i < localStorage.length; i++) keys.add(localStorage.key(i));
      } catch {
        // 읽기 불가: 메모리 키만 사용
      }
      return [...keys]
        .map((k) => DATE_KEY_RE.exec(k || ''))
        .filter(Boolean)
        .map((m) => m[1])
        .sort();
    }

    return {
      load,
      save,
      dateKeys,
      get failed() {
        return failed;
      },
    };
  })();

  // ---------------------------------------------------------------------------
  // date: 로컬 시간 기준 날짜 키와 표시 형식
  // ---------------------------------------------------------------------------
  const WEEKDAYS = '일월화수목금토';

  function toDateKey(date = new Date()) {
    const y = date.getFullYear();
    const m = String(date.getMonth() + 1).padStart(2, '0');
    const d = String(date.getDate()).padStart(2, '0');
    return `${y}-${m}-${d}`;
  }

  function parseDateKey(key) {
    const [y, m, d] = key.split('-').map(Number);
    return new Date(y, m - 1, d);
  }

  function formatDate(key) {
    const date = parseDateKey(key);
    return `${date.getFullYear()}년 ${date.getMonth() + 1}월 ${date.getDate()}일 (${WEEKDAYS[date.getDay()]})`;
  }

  function isYesterday(key, todayKey) {
    const d = parseDateKey(todayKey);
    d.setDate(d.getDate() - 1);
    return toDateKey(d) === key;
  }

  // ---------------------------------------------------------------------------
  // state
  // ---------------------------------------------------------------------------
  const settings = {
    theme: 'system',
    filter: 'all',
    carriedOn: null,
    ...storage.load(SETTINGS_KEY, {}),
  };

  const state = {
    dateKey: toDateKey(),
    todos: [],
    editingId: null,
    justAddedId: null,
  };
  state.todos = loadTodos(state.dateKey);

  function loadTodos(dateKey) {
    const todos = storage.load(PREFIX + dateKey, []);
    return Array.isArray(todos) ? todos : [];
  }

  function saveTodos() {
    storage.save(PREFIX + state.dateKey, state.todos);
  }

  function saveSettings() {
    storage.save(SETTINGS_KEY, settings);
  }

  function commit() {
    saveTodos();
    render();
  }

  function createId() {
    return `${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;
  }

  function createTodo(text) {
    return {
      id: createId(),
      text,
      done: false,
      important: false,
      createdAt: new Date().toISOString(),
      completedAt: null,
    };
  }

  function findTodo(id) {
    return state.todos.find((t) => t.id === id);
  }

  function addTodo(rawText) {
    const text = rawText.trim();
    if (!text) return false;
    const todo = createTodo(text);
    state.todos.push(todo);
    state.justAddedId = todo.id;
    commit();
    return true;
  }

  function toggleTodo(id) {
    const todo = findTodo(id);
    if (!todo) return;
    todo.done = !todo.done;
    todo.completedAt = todo.done ? new Date().toISOString() : null;
    commit();
  }

  function toggleImportant(id) {
    const todo = findTodo(id);
    if (!todo) return;
    todo.important = !todo.important;
    commit();
  }

  function removeTodo(id) {
    state.todos = state.todos.filter((t) => t.id !== id);
    commit();
  }

  function editTodo(id, rawText) {
    const todo = findTodo(id);
    const text = rawText.trim();
    if (todo && text) todo.text = text;
    commit();
  }

  function clearDone() {
    state.todos = state.todos.filter((t) => !t.done);
    commit();
  }

  // id 항목을 targetId 항목의 앞(after=false) 또는 뒤(after=true)로 이동
  function moveTodo(id, targetId, after) {
    if (id === targetId) return;
    const from = state.todos.findIndex((t) => t.id === id);
    if (from < 0) return;
    const [todo] = state.todos.splice(from, 1);
    let to = state.todos.findIndex((t) => t.id === targetId);
    if (to < 0) {
      state.todos.splice(from, 0, todo);
      return;
    }
    if (after) to += 1;
    state.todos.splice(to, 0, todo);
    commit();
  }

  // 화면에 보이는 순서 기준으로 한 칸 위/아래 이동 (키보드용)
  function moveBy(id, delta) {
    const visible = visibleTodos();
    const index = visible.findIndex((t) => t.id === id);
    const neighbor = visible[index + delta];
    if (index < 0 || !neighbor) return;
    moveTodo(id, neighbor.id, delta > 0);
  }

  // 오늘 이전 날짜 중 가장 최근이면서 미완료 항목이 있는 목록
  function findCarrySource() {
    if (settings.carriedOn === state.dateKey) return null;
    const keys = storage.dateKeys().filter((k) => k < state.dateKey).reverse();
    for (const key of keys) {
      const pending = loadTodos(key).filter((t) => !t.done);
      if (pending.length) return { key, pending };
    }
    return null;
  }

  function carryOver() {
    const source = findCarrySource();
    if (!source) return;
    const existing = new Set(state.todos.map((t) => t.text));
    for (const old of source.pending) {
      if (existing.has(old.text)) continue;
      const todo = createTodo(old.text);
      todo.important = Boolean(old.important);
      state.todos.push(todo);
    }
    settings.carriedOn = state.dateKey;
    saveSettings();
    commit();
  }

  function setFilter(filter) {
    settings.filter = filter;
    saveSettings();
    render();
  }

  // 중요 항목을 위로, 나머지는 저장된 순서 유지
  function visibleTodos() {
    const sorted = [
      ...state.todos.filter((t) => t.important),
      ...state.todos.filter((t) => !t.important),
    ];
    if (settings.filter === 'active') return sorted.filter((t) => !t.done);
    if (settings.filter === 'done') return sorted.filter((t) => t.done);
    return sorted;
  }

  // ---------------------------------------------------------------------------
  // theme
  // ---------------------------------------------------------------------------
  const darkQuery = window.matchMedia('(prefers-color-scheme: dark)');

  function effectiveTheme() {
    if (settings.theme === 'light' || settings.theme === 'dark') return settings.theme;
    return darkQuery.matches ? 'dark' : 'light';
  }

  function applyTheme() {
    const root = document.documentElement;
    if (settings.theme === 'system') delete root.dataset.theme;
    else root.dataset.theme = settings.theme;

    const dark = effectiveTheme() === 'dark';
    els.themeToggle.textContent = dark ? '☀️' : '🌙';
    els.themeToggle.setAttribute('aria-label', dark ? '라이트 모드로 전환' : '다크 모드로 전환');
  }

  function toggleTheme() {
    settings.theme = effectiveTheme() === 'dark' ? 'light' : 'dark';
    saveSettings();
    applyTheme();
  }

  // ---------------------------------------------------------------------------
  // render
  // ---------------------------------------------------------------------------
  const $ = (id) => document.getElementById(id);
  const els = {
    banner: $('storage-banner'),
    today: $('today'),
    themeToggle: $('theme-toggle'),
    progressBar: $('progress-bar'),
    progressFill: $('progress-fill'),
    progressText: $('progress-text'),
    addForm: $('add-form'),
    addInput: $('add-input'),
    carryBtn: $('carry-btn'),
    filters: document.querySelector('.filters'),
    allDone: $('all-done'),
    list: $('list'),
    empty: $('empty'),
    emptyText: $('empty-text'),
    remaining: $('remaining'),
    clearDone: $('clear-done'),
  };

  const EMPTY_TEXT = {
    all: '오늘 할 일을 추가해 보세요',
    active: '진행 중인 할일이 없어요',
    done: '아직 완료한 할일이 없어요',
  };

  function el(tag, props = {}, attrs = {}) {
    const node = Object.assign(document.createElement(tag), props);
    for (const [name, value] of Object.entries(attrs)) node.setAttribute(name, value);
    return node;
  }

  function renderItem(todo) {
    const editing = state.editingId === todo.id;
    const li = el('li', { className: 'item' }, { 'data-id': todo.id });
    li.classList.toggle('done', todo.done);
    li.classList.toggle('important', todo.important);
    li.classList.toggle('entering', state.justAddedId === todo.id);
    li.draggable = !editing;

    li.append(
      el('span', { className: 'handle', textContent: '⋮⋮', title: '끌어서 순서 변경 (Alt+↑/↓)' }, { 'aria-hidden': 'true' }),
      el('input', { type: 'checkbox', className: 'check', checked: todo.done }, { 'aria-label': `"${todo.text}" 완료` }),
    );

    if (editing) {
      li.append(el('input', { type: 'text', className: 'edit-input', value: todo.text, maxLength: 200 }, { 'aria-label': '할일 수정' }));
    } else {
      li.append(el('span', { className: 'text', textContent: todo.text, title: '더블클릭하여 수정' }));
    }

    li.append(
      el('button', { type: 'button', className: 'item-btn star', textContent: todo.important ? '★' : '☆' }, {
        'aria-label': `"${todo.text}" 중요 표시`,
        'aria-pressed': String(todo.important),
      }),
      el('button', { type: 'button', className: 'item-btn edit', textContent: '✎' }, { 'aria-label': `"${todo.text}" 수정` }),
      el('button', { type: 'button', className: 'item-btn delete', textContent: '✕' }, { 'aria-label': `"${todo.text}" 삭제` }),
    );
    return li;
  }

  function render() {
    const total = state.todos.length;
    const done = state.todos.filter((t) => t.done).length;
    const pct = total ? Math.round((done / total) * 100) : 0;

    els.banner.hidden = !storage.failed;
    els.today.textContent = formatDate(state.dateKey);

    els.progressFill.style.width = `${pct}%`;
    els.progressBar.setAttribute('aria-valuenow', String(pct));
    els.progressText.textContent = total ? `${done} / ${total} 완료 (${pct}%)` : '아직 할일이 없어요';
    els.allDone.hidden = !(total > 0 && done === total);

    const carry = findCarrySource();
    els.carryBtn.hidden = !carry;
    if (carry) {
      const label = isYesterday(carry.key, state.dateKey) ? '어제' : formatDate(carry.key);
      els.carryBtn.textContent = `↩ ${label} 못한 일 가져오기 (${carry.pending.length}개)`;
    }

    for (const btn of els.filters.querySelectorAll('button')) {
      btn.setAttribute('aria-pressed', String(btn.dataset.filter === settings.filter));
    }

    const visible = visibleTodos();
    els.list.replaceChildren(...visible.map(renderItem));
    els.empty.hidden = visible.length > 0;
    els.emptyText.textContent = total === 0 ? EMPTY_TEXT.all : EMPTY_TEXT[settings.filter];

    els.remaining.textContent = `남은 할일 ${total - done}개`;
    els.clearDone.disabled = done === 0;

    state.justAddedId = null;

    if (state.editingId) {
      const input = els.list.querySelector('.edit-input');
      if (input) {
        input.focus();
        input.select();
      }
    }
  }

  function itemOf(node) {
    return node.closest('.item');
  }

  function focusItem(id) {
    const li = els.list.querySelector(`[data-id="${CSS.escape(id)}"]`);
    if (li) li.querySelector('.check').focus();
  }

  // ---------------------------------------------------------------------------
  // edit
  // ---------------------------------------------------------------------------
  function startEdit(id) {
    state.editingId = id;
    render();
  }

  function finishEdit(save) {
    const id = state.editingId;
    if (!id) return;
    const input = els.list.querySelector('.edit-input');
    state.editingId = null;
    if (save && input) editTodo(id, input.value);
    else render();
    focusItem(id);
  }

  // ---------------------------------------------------------------------------
  // events
  // ---------------------------------------------------------------------------
  els.addForm.addEventListener('submit', (e) => {
    e.preventDefault();
    if (addTodo(els.addInput.value)) els.addInput.value = '';
    els.addInput.focus();
  });

  els.themeToggle.addEventListener('click', toggleTheme);
  darkQuery.addEventListener('change', applyTheme);

  els.carryBtn.addEventListener('click', carryOver);
  els.clearDone.addEventListener('click', clearDone);

  els.filters.addEventListener('click', (e) => {
    const btn = e.target.closest('button[data-filter]');
    if (btn) setFilter(btn.dataset.filter);
  });

  els.list.addEventListener('change', (e) => {
    if (!e.target.classList.contains('check')) return;
    const id = itemOf(e.target).dataset.id;
    toggleTodo(id);
    focusItem(id);
  });

  els.list.addEventListener('click', (e) => {
    const btn = e.target.closest('.item-btn');
    if (!btn) return;
    const li = itemOf(btn);
    const id = li.dataset.id;

    if (btn.classList.contains('star')) {
      toggleImportant(id);
      focusItem(id);
    } else if (btn.classList.contains('edit')) {
      startEdit(id);
    } else if (btn.classList.contains('delete')) {
      li.classList.add('removing');
      setTimeout(() => removeTodo(id), REMOVE_DELAY);
    }
  });

  els.list.addEventListener('dblclick', (e) => {
    if (e.target.classList.contains('text')) startEdit(itemOf(e.target).dataset.id);
  });

  els.list.addEventListener('keydown', (e) => {
    if (e.target.classList.contains('edit-input')) {
      if (e.key === 'Enter') {
        e.preventDefault();
        finishEdit(true);
      } else if (e.key === 'Escape') {
        e.preventDefault();
        finishEdit(false);
      }
      return;
    }

    if (e.altKey && (e.key === 'ArrowUp' || e.key === 'ArrowDown')) {
      e.preventDefault();
      const id = itemOf(e.target).dataset.id;
      moveBy(id, e.key === 'ArrowUp' ? -1 : 1);
      focusItem(id);
    }
  });

  els.list.addEventListener('focusout', (e) => {
    if (e.target.classList.contains('edit-input')) finishEdit(true);
  });

  // 드래그 앤 드롭
  let dragId = null;

  function clearDropMarks() {
    for (const li of els.list.querySelectorAll('.drop-before, .drop-after')) {
      li.classList.remove('drop-before', 'drop-after');
    }
  }

  function isAfter(li, e) {
    const rect = li.getBoundingClientRect();
    return e.clientY > rect.top + rect.height / 2;
  }

  els.list.addEventListener('dragstart', (e) => {
    const li = itemOf(e.target);
    if (!li) return;
    dragId = li.dataset.id;
    li.classList.add('dragging');
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', dragId);
  });

  els.list.addEventListener('dragover', (e) => {
    const li = itemOf(e.target);
    if (!dragId || !li) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    clearDropMarks();
    if (li.dataset.id !== dragId) li.classList.add(isAfter(li, e) ? 'drop-after' : 'drop-before');
  });

  els.list.addEventListener('drop', (e) => {
    const li = itemOf(e.target);
    if (!dragId || !li) return;
    e.preventDefault();
    const id = dragId;
    dragId = null;
    clearDropMarks();
    moveTodo(id, li.dataset.id, isAfter(li, e));
  });

  els.list.addEventListener('dragend', () => {
    dragId = null;
    clearDropMarks();
    for (const li of els.list.querySelectorAll('.dragging')) li.classList.remove('dragging');
  });

  // 날짜가 바뀌면 오늘 목록으로 전환
  function checkDateChange() {
    const key = toDateKey();
    if (key === state.dateKey) return;
    state.dateKey = key;
    state.todos = loadTodos(key);
    state.editingId = null;
    render();
  }

  setInterval(checkDateChange, 30 * 1000);
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) checkDateChange();
  });

  // ---------------------------------------------------------------------------
  // init
  // ---------------------------------------------------------------------------
  if (!['all', 'active', 'done'].includes(settings.filter)) settings.filter = 'all';
  applyTheme();
  render();
})();
