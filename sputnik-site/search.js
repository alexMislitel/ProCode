/*
 * Спутник — поиск по услугам.
 * © 2026 Alexandr. Основной код форка: OpenCode, MIT, (c) 2025 opencode
 *
 * Поиск идёт по названию и описанию, без учёта регистра.
 *
 * Отдельно про букву «ё»: русский человек почти всегда набирает «е»
 * вместо «ё». Без нормализации «приём» не находился бы по запросу
 * «прием», а это четверть всех обращений. Поэтому перед сравнением
 * «ё» приводится к «е».
 */

const MARK = '';

function normalize(text) {
  return text
    .toLowerCase()
    .replace(/ё/g, 'е')
    .replace(/\s+/g, ' ')
    .trim();
}

/** Русские окончания не учитываем: ищем по началу слова. */
function matches(haystack, needle) {
  if (!needle) return true;
  const words = haystack.split(' ');
  return words.some((word) => word.startsWith(needle) || word.includes(needle));
}

function initSearch() {
  const input = document.getElementById('q');
  const counter = document.getElementById('count');
  const empty = document.getElementById('empty');
  const groups = [...document.querySelectorAll('[data-group]')];
  const tiles = [...document.querySelectorAll('.tile')];

  if (!input || tiles.length === 0) return;

  // Заранее готовим нормализованный текст один раз, а не на каждое
  // нажатие клавиши.
  const prepared = tiles.map((tile) => normalize(
    `${tile.dataset.name ?? ''} ${tile.textContent}`,
  ));

  function apply() {
    const query = normalize(input.value);
    let visible = 0;

    tiles.forEach((tile, index) => {
      const hit = matches(prepared[index], query);
      tile.hidden = !hit;
      if (hit) visible += 1;
    });

    // Пустая группа выглядит как ошибка, её прячем.
    groups.forEach((group) => {
      const any = [...group.querySelectorAll('.tile')].some((tile) => !tile.hidden);
      group.hidden = !any;
    });

    if (counter) {
      counter.textContent = query
        ? `найдено ${visible} из ${tiles.length}`
        : `${tiles.length} услуг`;
    }

    if (empty) empty.hidden = visible > 0;
  }

  input.addEventListener('input', apply);
  input.addEventListener('search', apply);

  // Ctrl+K, Esc и очистка по клику на крестик.
  document.addEventListener('keydown', (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
      event.preventDefault();
      input.focus();
      input.select();
    }
    if (event.key === 'Escape' && document.activeElement === input) {
      input.value = '';
      apply();
      input.blur();
    }
  });

  const clear = document.getElementById('clear');
  if (clear) {
    clear.addEventListener('click', () => {
      input.value = '';
      apply();
      input.focus();
    });
  }

  apply();
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initSearch);
} else {
  initSearch();
}
