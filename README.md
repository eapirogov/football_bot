# Football Bot — Telegram-бот футбольного расписания

Курсовая работа: бот, который уведомляет пользователя о предстоящих и завершившихся матчах его любимых команд и лиг, а по запросу присылает развёрнутую статистику матча.

## Основные возможности

- Подписка на любимые **команды** (без ограничения по количеству)
- Подписка на целые **лиги** — уведомления по всем матчам лиги
- Уведомление за **20 минут** до матча
- Уведомление о результате после матча с inline-кнопкой **«📊 Статистика»**
- Детализация: голы, ассисты, жёлтые/красные карточки, владение мячом, удары
- Часовой пояс — Europe/Moscow

## Стек

| Слой | Технология |
|---|---|
| Telegram | aiogram 3.x |
| База данных | PostgreSQL + SQLAlchemy 2.0 (async) + asyncpg |
| Миграции | Alembic |
| Планировщик | APScheduler с PostgreSQL JobStore |
| Источник данных | API-Football (api-football.com) |
| HTTP | httpx |
| Конфигурация | pydantic-settings |

## Архитектура

```
┌──────────────────┐       ┌────────────────┐       ┌──────────────────┐
│   Пользователь   │ <───> │  aiogram bot   │ <───> │   PostgreSQL     │
│   (Telegram)     │       │   (handlers)   │       │ (users, subs,    │
└──────────────────┘       └───────┬────────┘       │  fixtures, jobs) │
                                   │                └─────────▲────────┘
                                   │                          │
                                   ▼                          │
                          ┌─────────────────┐                 │
                          │  APScheduler    │─────────────────┘
                          │  (PG JobStore)  │
                          └────┬─────┬──────┘
                               │     │
        sync_fixtures (6h)─────┘     └──── send_pre / send_post (точечно)
                               │
                               ▼
                       ┌─────────────────┐
                       │  API-Football   │
                       └─────────────────┘
```

## Схема БД

| Таблица | Назначение |
|---|---|
| `users` | Telegram-пользователи (id, username) |
| `leagues` | Справочник лиг (заполняется сидом) |
| `teams` | Справочник команд |
| `favorite_teams` | Подписки пользователей на команды |
| `favorite_leagues` | Подписки пользователей на лиги |
| `fixtures` | Кэш ближайших матчей с актуальным статусом и счётом |
| `notifications` | Запланированные/отправленные уведомления (UNIQUE по user+fixture+kind) |

```
users ──┬── favorite_teams ── teams ── league_id ──┐
        │                                          │
        └── favorite_leagues ────── leagues ───────┤
                                                   │
                fixtures (league_id, home_team_id, away_team_id, kickoff_utc, status, scores)
                   │
                   └── notifications (kind: pre|post, scheduled_at, sent_at)
```

## Структура кода

```
football_bot/
├── alembic/                     # миграции
├── seeds/leagues_teams.py       # сид справочников из API
└── bot/
    ├── __main__.py              # entrypoint: `python -m bot`
    ├── config.py                # настройки из .env
    ├── db/
    │   ├── base.py              # async engine + session
    │   └── models.py            # SQLAlchemy модели
    ├── services/
    │   ├── football_api.py      # клиент к api-football.com
    │   ├── scheduler.py         # APScheduler с PG JobStore
    │   ├── fixtures_sync.py     # job: тянет расписание, планирует уведомления
    │   └── notifier.py          # рендер и отправка pre/post сообщений
    ├── handlers/
    │   ├── start.py             # /start, главное меню
    │   ├── leagues.py           # подписка на лиги
    │   ├── teams.py             # подписка на команды + поиск
    │   ├── favorites.py         # /my — список подписок
    │   └── stats.py             # callback кнопки «📊 Статистика»
    ├── keyboards/               # inline-клавиатуры с пагинацией
    ├── states/fsm.py            # FSM (поиск команды по имени)
    └── utils/time.py            # форматирование времени в МСК
```

## Установка и запуск

### 1. Подготовка окружения

```bash
cd football_bot
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. PostgreSQL

```bash
brew install postgresql@16 && brew services start postgresql@16
createdb football_bot
```

### 3. Ключи и настройки

1. Получить токен у [@BotFather](https://t.me/BotFather).
2. Зарегистрироваться на [api-football.com](https://www.api-football.com/) и взять API-ключ (бесплатный план — 100 запросов/день).
3. Скопировать `.env.example` в `.env` и заполнить:

```env
TELEGRAM_TOKEN=...
API_FOOTBALL_KEY=...
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/football_bot
TIMEZONE=Europe/Moscow
```

### 4. Миграции и сид

```bash
alembic upgrade head
python -m seeds.leagues_teams
```

### 5. Запуск

```bash
python -m bot
```

В Telegram отправить боту `/start` — появится главное меню.

## Логика уведомлений

1. При старте и каждые 6 часов `sync_fixtures` тянет матчи на ближайшие 7 дней по поддерживаемым лигам и кладёт их в `fixtures`.
2. Для каждого матча находятся подписчики (по командам + по лигам).
3. В таблицу `notifications` пишется запись с защитой от дублей (UNIQUE по `user_id + fixture_id + kind`), и в APScheduler регистрируется one-shot job:
   - `pre` — на `kickoff - 20 min`
   - `post` — на `kickoff + 110 min`
4. APScheduler хранит джобы в PostgreSQL (`apscheduler_jobs`), поэтому уведомления переживают рестарт бота.
5. По срабатыванию pre-job → `notifier.send_pre()`. По post-job → `notifier.send_post()` дополнительно проверяет реальный статус матча (на случай овертайма).
6. По нажатию кнопки «📊 Статистика» — `handlers/stats.py` тянет `events` и `statistics` из API и форматирует ответ.

## Поддерживаемые лиги

- АПЛ, Ла Лига, Серия А, Бундеслига, Лига 1
- Лига Чемпионов УЕФА, Лига Европы УЕФА
- РПЛ
- Чемпионат мира, Чемпионат Европы

Список настраивается в `bot/config.py` через `SUPPORTED_LEAGUE_IDS`.
