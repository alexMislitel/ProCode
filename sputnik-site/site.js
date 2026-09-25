/*
 * Спутник — общие ссылки и меню.
 * © 2026 Alexandr. Основной код форка: OpenCode, MIT, (c) 2025 opencode
 *
 * ЗАЧЕМ ЭТОТ ФАЙЛ
 *
 * Все адреса собраны здесь, в одном месте. Правится один раз —
 * меняется везде. Иначе ссылка на канал в пяти файлах разъезжается
 * сама с собой через неделю, и сайт начинает вести в никуда.
 *
 * Пока внешняя ссылка пустая, скрипт не рисует ссылку, а показывает её как
 * обычный текст. Мёртвой ссылки на странице не появляется.
 */

const LINKS = {
  name: 'Спутник',
  tagline: '',

  // --- внешнее: впиши свои, когда будет ---
  GITHUB_REPO: 'https://github.com/alexMislitel/sputnik',
  TELEGRAM: 'https://t.me/alex2zeus',
  EMAIL: 'alexgold917@gmail.com',

  // --- внутреннее: эти страницы всегда рядом ---
  pages: {
    home: './index.html',
    download: './download.html',
    features: './features.html',
    pricing: './pricing.html',
    faq: './faq.html',
  },
};

const NAV = [
  { key: 'home', label: 'Главная' },
  { key: 'download', label: 'Скачать' },
  { key: 'features', label: 'Возможности' },
  { key: 'pricing', label: 'Тарифы' },
  { key: 'faq', label: 'Вопросы' },
];

/** Внешняя ссылка или обычный текст, если адрес не задан. */
function external(key) {
  const value = LINKS[key];
  if (!value) return null;
  if (key === 'EMAIL') return { href: `mailto:${value}`, text: value, external: false };
  return { href: value, text: value, external: true };
}

function currentPage() {
  const file = location.pathname.split('/').pop();
  return !file || file === '' ? 'index.html' : file;
}

function render() {
  const here = currentPage();

  // --- знак и название ---
  document.querySelectorAll('[data-site-name]').forEach((node) => {
    node.textContent = LINKS.name;
  });

  // --- меню ---
  document.querySelectorAll('[data-nav]').forEach((host) => {
    host.innerHTML = NAV.map((item) => {
      const active = LINKS.pages[item.key] === `./${here}` ? ' class="on"' : '';
      return `<a href="${LINKS.pages[item.key]}"${active}>${item.label}</a>`;
    }).join('');

    const repo = external('GITHUB_REPO');
    host.insertAdjacentHTML(
      'beforeend',
      repo
        ? `<a class="ghost" href="${repo.href}" target="_blank" rel="noopener">GitHub</a>`
        : '<span class="ghost off">GitHub</span>',
    );
  });

  // --- подвал ---
  document.querySelectorAll('[data-external]').forEach((node) => {
    const target = external(node.dataset.external);
    if (target) {
      const rel = target.external ? ' target="_blank" rel="noopener"' : '';
      node.href = target.href;
      node.textContent = target.text;
      node.classList.remove('off');
    } else {
      // Адрес не задан: показываем честно, что ждёт, вместо мёртвой ссылки
      const waiting = { GITHUB_REPO: 'репозиторий готовится', TELEGRAM: 'канал готовится', EMAIL: 'почта готовится' };
      node.removeAttribute('href');
      node.classList.add('off');
      node.textContent = waiting[node.dataset.external] || 'скоро';
    }
  });
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', render);
} else {
  render();
}
