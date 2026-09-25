<?php
/**
 * Чат с сайта — приём заявок в Telegram.
 * © 2026 Alexandr. Основной код форка: OpenCode, MIT, © 2025 opencode
 *
 * Зачем отдельный файл: токен Telegram-бота — это секрет. На странице
 * его видно в исходниках, и через него пишут во все боты компании.
 * Здесь он лежит на сервере и наружу не отдаётся.
 *
 * НАСТРОЙКА
 *   1. Создай бота через @BotFather, получи токен
 *   2. Впиши токен в BOT_TOKEN ниже
 *   3. Узнай свой chat_id: напиши боту, открой
 *      https://api.telegram.org/bot<ТОКЕН>/getUpdates
 *      и впиши id сюда
 *   4. Файл кладётся в корень сайта, доступ: api/chat.php
 */

declare(strict_types=1);

const BOT_TOKEN = 'СЮДА_ТОКЕН_БОТА';
const CHAT_ID    = 'СЮДА_CHAT_ID';

// Не выпускаем наружу разметку PHP, даже если что-то сломается.
header('Content-Type: application/json; charset=utf-8');
header('X-Content-Type-Options: nosniff');

/**
 * Сайт не должен лежать в стороннем iframe: иначе чужие смогут
 * слать заявки от имени нашего имени и выкачивать их.
 */
$allowed = getenv('SPUTNIK_ALLOWED_ORIGIN') ?: '';
$origin  = $_SERVER['HTTP_ORIGIN'] ?? '';
if ($allowed !== '' && $origin !== '' && $origin !== $allowed) {
    http_response_code(403);
    exit(json_encode(['ok' => false, 'error' => 'источник не разрешён']));
}

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    http_response_code(405);
    exit(json_encode(['ok' => false, 'error' => 'нужен POST']));
}

// Токен бота ещё не вписан — отвечаем честно, а не падаем с 500.
if (str_starts_with(BOT_TOKEN, 'СЮДА_')) {
    http_response_code(503);
    exit(json_encode([
        'ok' => false,
        'error' => 'чат ещё не настроен, напишите в Telegram',
    ]));
}

$raw = file_get_contents('php://input') ?: '';
$in  = json_decode($raw, true);
if (!is_array($in)) {
    http_response_code(400);
    exit(json_encode(['ok' => false, 'error' => 'плохой запрос']));
}

/** Обрезаем и чистим: в Telegram всё равно не полезет длиннее 4096. */
function clean(mixed $value, int $max): string
{
    $text = trim(is_string($value) ? $value : '');
    $text = str_replace(["\r\n", "\r"], "\n", $text);
    $text = (string) preg_replace('/[ \t]+/u', ' ', $text);

    return mb_substr($text, 0, $max, 'UTF-8');
}

$name = clean($in['name'] ?? '', 80);
$text = clean($in['text'] ?? '', 3500);
$page = clean($in['page'] ?? '', 200);

if ($text === '') {
    http_response_code(400);
    exit(json_encode(['ok' => false, 'error' => 'сообщение пустое']));
}

$who = $name !== '' ? $name : 'без имени';

$lines = [
    'Новая заявка с сайта',
    '',
    'Кто: ' . $who,
    'Откуда: ' . ($page !== '' ? $page : 'не указано'),
    '',
    $text,
];
$message = implode("\n", $lines);

$url = 'https://api.telegram.org/bot' . BOT_TOKEN . '/sendMessage';

$ch = curl_init($url);
curl_setopt_array($ch, [
    CURLOPT_POST           => true,
    CURLOPT_POSTFIELDS     => http_build_query([
        'chat_id'    => CHAT_ID,
        'text'       => $message,
        'parse_mode' => 'HTML',
        'disable_web_page_preview' => true,
    ]),
    CURLOPT_RETURNTRANSFER => true,
    CURLOPT_TIMEOUT        => 12,
]);

$response = curl_exec($ch);
$status   = (int) curl_getinfo($ch, CURLINFO_HTTP_CODE);
curl_close($ch);

if ($status !== 200) {
    error_log('sputnik chat: telegram вернул ' . $status . ' — ' . substr((string) $response, 0, 200));
    http_response_code(502);
    exit(json_encode(['ok' => false, 'error' => 'Telegram не отвечает']));
}

http_response_code(200);
exit(json_encode(['ok' => true]));
