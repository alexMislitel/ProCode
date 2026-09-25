/*
 * Чат с сайта — Спутник
 * © 2026 Alexandr. Основной код форка: OpenCode, MIT, (c) 2025 opencode
 *
 * Виджет в правом нижнем углу. Посетитель пишет — сообщение приходит
 * в Telegram через api/chat.php на сервере.
 *
 * ПОЧЕМУ ЧЕРЕЗ СЕРВЕР, А НЕ ПРЯМО В БРАУЗЕР:
 * токен Telegram-бота — это секрет. Если положить его в код страницы,
 * он виден каждому, кто открыл исходники, и через него напишут во все
 * боты компании. Поэтому токен живёт только на сервере, в chat.php.
 *
 * Без сервера нельзя. На статике токен утечёт — это не страшилка,
 * а ровно то, что происходит.
 *
 * НАСТРОЙКА ОДНА СТРОЧКА: BOT_TOKEN в api/chat.php.
 */

const CONFIG = {
  endpoint: './api/chat.php',
  // Куда приводить к обещанию, что ответим. Заменяется на канал.
  promise: 'Отвечаем в Telegram',
};

const el = {};

function build() {
  el.button = document.createElement('button');
  el.button.className = 'chat-fab';
  el.button.type = 'button';
  el.button.setAttribute('aria-label', 'Написать нам');
  el.button.setAttribute('aria-expanded', 'false');
  el.button.innerHTML = `
    <svg viewBox="0 0 24 24" width="24" height="24" aria-hidden="true">
      <path d="M12 3c5 0 9 3.4 9 7.6 0 4.2-4 7.6-9 7.6-.9 0-1.8-.1-2.6-.3L4 20l1.2-3.9C3.8 14.7 3 12.7 3 10.6 3 6.4 7 3 12 3z"
            fill="currentColor"/>
    </svg>`;
  el.button.addEventListener('click', toggle);

  el.panel = document.createElement('div');
  el.panel.className = 'chat-panel';
  el.panel.hidden = true;
  el.panel.innerHTML = `
    <div class="chat-head">
      <div>
        <b>Написать нам</b>
        <span>${CONFIG.promise}</span>
      </div>
      <button type="button" class="chat-x" aria-label="Закрыть">×</button>
    </div>
    <form class="chat-form">
      <div class="rec-row">
        <button type="button" class="rec" id="rec" aria-label="Записать голосом">
          <svg viewBox="0 0 24 24" width="17" height="17" aria-hidden="true">
            <path d="M12 15a3 3 0 0 0 3-3V6a3 3 0 0 0-6 0v6a3 3 0 0 0 3 3z" fill="currentColor"/>
            <path d="M18 11a1 1 0 1 0-2 0 4 4 0 0 1-8 0 1 1 0 1 0-2 0 6 6 0 0 0 5 5.9V19H9a1 1 0 1 0 0 2h6a1 1 0 1 0 0-2h-2v-2.1A6 6 0 0 0 18 11z" fill="currentColor"/>
          </svg>
          <span id="rec-label">Говорить</span>
        </button>
        <p class="rec-hint" id="rec-hint"></p>
      </div>
      <label>
        Как вас зовут
        <input name="name" type="text" autocomplete="name" placeholder="Имя" maxlength="80">
      </label>
      <label>
        Что нужно
        <textarea name="text" rows="4" maxlength="4000"
          placeholder="Напишите или нажмите «Говорить»"></textarea>
      </label>
      <button type="submit" class="chat-send">Отправить</button>
      <p class="chat-note" role="status" aria-live="polite"></p>
    </form>`;

  el.form = el.panel.querySelector('.chat-form');
  el.note = el.panel.querySelector('.chat-note');
  el.rec = el.panel.querySelector('#rec');
  el.recHint = el.panel.querySelector('#rec-hint');
  el.panel.querySelector('.chat-x').addEventListener('click', () => toggle(false));
  el.form.addEventListener('submit', send);
  el.rec.addEventListener('click', toggleRecord);

  document.body.append(el.panel, el.button);
}

function toggle(force) {
  const open = force ?? el.panel.hidden;
  el.panel.hidden = !open;
  el.button.setAttribute('aria-expanded', String(open));
  if (open) el.form.querySelector('textarea').focus();
}

async function send(event) {
  event.preventDefault();

  const data = new FormData(el.form);
  const text = String(data.get('text') ?? '').trim();
  if (!text) return;

  const button = el.form.querySelector('.chat-send');
  button.disabled = true;
  button.textContent = 'Отправляю…';
  el.note.className = 'chat-note';

  try {
    const response = await fetch(CONFIG.endpoint, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({
        name: String(data.get('name') ?? '').trim(),
        text,
        // Страница нужна для контекста: откуда человек пришёл.
        page: location.pathname,
      }),
    });

    const payload = await response.json().catch(() => ({}));

    if (!response.ok || payload.ok === false) {
      throw new Error(payload.error || 'не отправилось');
    }

    el.form.reset();
    el.note.className = 'chat-note good';
    el.note.textContent = 'Отправлено. Ответим в Telegram.';
    setTimeout(() => { el.note.textContent = ''; }, 6000);
  } catch (error) {
    el.note.className = 'chat-note bad';
    el.note.textContent = error.message === 'не отправилось'
      ? 'Не отправилось. Напишите в Telegram напрямую.'
      : error.message;
  } finally {
    button.disabled = false;
    button.textContent = 'Отправить';
  }
}

/* ---------------------------------------------------------------- голос */

const SpeechRecognition =
  window.SpeechRecognition ?? window.webkitSpeechRecognition ?? null;

let recognition = null;
let recording = false;
let heard = ''; // всё, что распознано за текущий сеанс

/**
 * Распознавание речи в браузере.
 *
 * ЧЕСТНО ПРО ЗВУК: браузер отправляет аудио в Google или Apple — это
 * встроенный веб-сервис, мимо него не пройти. Наш код звук не видит
 * и никуда не передаёт, но в браузере распознаёт не он, а его поставщик.
 *
 * Настоящее локальное распознавание ставится отдельным сервисом на
 * сервере. Как только он появится, здесь меняется одна функция.
 */

function toggleRecord() {
  if (recording) {
    stopRecord();
    return;
  }

  if (!SpeechRecognition) {
    el.recHint.textContent = 'Браузер не умеет распознавать речь. Напишите текстом.';
    el.recHint.className = 'rec-hint bad';
    return;
  }

  recognition = new SpeechRecognition();
  recognition.lang = 'ru-RU';
  recognition.continuous = true;
  recognition.interimResults = true;

  recognition.onresult = (event) => {
    let interim = '';
    for (let i = event.resultIndex; i < event.results.length; i += 1) {
      const chunk = event.results[i][0].transcript;
      if (event.results[i].isFinal) heard += `${chunk} `;
      else interim += chunk;
    }
    el.form.elements.text.value = (heard + interim).trimStart();
  };

  recognition.onerror = (event) => {
    const messages = {
      'no-speech': 'Речи не услышали.',
      'not-allowed': 'Браузер запретил микрофон.',
      'audio-capture': 'Микрофон не найден.',
      network: 'Нужен интернет: распознаёт браузер, не мы.',
    };
    el.recHint.textContent = messages[event.error] ?? `Ошибка: ${event.error}`;
    el.recHint.className = 'rec-hint bad';
    stopRecord();
  };

  recognition.onend = () => {
    // Браузер самопроизвольно рвёт сеанс — поднимаем заново,
    // пока человек не нажал кнопку.
    if (recording) {
      try { recognition.start(); } catch { stopRecord(); }
    }
  };

  try {
    recognition.start();
  } catch {
    el.recHint.textContent = 'Не смог включить микрофон.';
    el.recHint.className = 'rec-hint bad';
    return;
  }

  recording = true;
  heard = el.form.elements.text.value.trim() ? `${el.form.elements.text.value.trim()} ` : '';
  el.rec.classList.add('on');
  el.rec.setAttribute('aria-pressed', 'true');
  el.form.elements.text.readOnly = true;
  el.recHint.className = 'rec-hint';
  el.recHint.textContent = 'Слушаю. Нажми ещё раз, чтобы остановить.';
}

function stopRecord() {
  recording = false;
  try { recognition?.stop(); } catch { /* уже остановлено */ }

  el.rec.classList.remove('on');
  el.rec.setAttribute('aria-pressed', 'false');
  el.form.elements.text.readOnly = false;

  const text = el.form.elements.text.value.trim();
  if (text) {
    el.recHint.className = 'rec-hint good';
    el.recHint.textContent = 'Записано. Проверь и отправляй.';
  } else {
    el.recHint.className = 'rec-hint bad';
    el.recHint.textContent = 'Ничего не услышали.';
  }
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', build);
} else {
  build();
}
