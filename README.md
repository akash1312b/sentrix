# Sentrix — AI-Powered Inventory Management for Small Shops

A Django + DRF backend for small-shop inventory management with **automated
stock alerts, auto-drafted purchase orders, and a Claude-powered chat
assistant** that can answer stock questions and record transactions through
natural conversation.

This isn't a toy CRUD app — the goal was to build something with the shape
of a real internal tool: multi-tenant data isolation, an audit trail for
every stock movement, background automation, and an AI layer that calls
real backend functions instead of hallucinating numbers.

---

## Why this project

Most portfolio inventory apps stop at "add/edit/delete product." This one
demonstrates:

- **Concurrency-safe stock updates** — `record_stock_transaction()` uses
  `select_for_update()` so two simultaneous sales can't oversell stock.
- **One source of truth for business logic** — the REST API, Django Admin,
  Celery tasks, and the AI chatbot all call the *same* service functions
  (`apps/*/services.py`), so behavior never diverges between surfaces.
- **Real AI tool-calling**, not a wrapper around a static prompt — the
  Claude assistant can only report numbers or make changes by invoking
  defined tools (`apps/chatbot/tools.py`) against the actual database.
- **Explainable automation** over black-box ML — stockout forecasting is a
  simple, auditable moving-average calculation; automation drafts purchase
  orders but always waits for owner approval before anything is "ordered."
- **A real test suite** (20 tests, `pytest-django`) covering services, the
  API layer, tenant isolation, and the chatbot's tool execution — not just
  scaffolding.

---

## Feature overview

| Area | What it does |
|---|---|
| **Inventory** | Products, categories, suppliers, barcode lookup, stock in/out with full audit trail |
| **Alerts** | Real-time low-stock / out-of-stock / expiry alerts, emailed to shop owners |
| **Automation** | Celery Beat jobs: daily stock/expiry checks, weekly sales summary, auto-drafted purchase orders |
| **Suppliers** | Purchase order lifecycle (draft → approved → received), receiving a PO auto-updates stock |
| **AI Assistant** | Chat endpoint backed by Claude with tool-calling: check stock, record sales, forecast stockouts, draft POs — all through conversation |
| **Multi-tenant** | One codebase supports multiple shops and staff roles (owner/manager/staff) via `Shop` + `Membership` |
| **API** | Full DRF REST API, JWT auth, OpenAPI schema at `/api/docs/` |

---

## Tech stack

- **Backend:** Django 5, Django REST Framework, `drf-spectacular` (OpenAPI docs)
- **Auth:** JWT (`djangorestframework-simplejwt`)
- **Database:** PostgreSQL (SQLite supported for quick local dev, see below)
- **Background jobs:** Celery + Redis + `django-celery-beat`
- **AI:** Anthropic Claude API (tool/function calling)
- **Deployment:** Docker + Docker Compose, Gunicorn + WhiteNoise for prod

---

## Project layout

```
sentrix/
├── config/
│   ├── settings/         # base.py / dev.py / prod.py
│   ├── celery.py         # Celery app + Beat schedule
│   └── urls.py
├── apps/
│   ├── core/             # abstract base models, tenant-scoping mixin, seed command
│   ├── accounts/         # custom User, Shop, Membership (roles), JWT auth views
│   ├── inventory/        # Product, Category, Supplier, StockTransaction + services
│   ├── suppliers/        # PurchaseOrder workflow + auto-draft automation
│   ├── alerts/           # Alert model + Celery tasks + email delivery
│   └── chatbot/          # ChatSession/Message + Claude tool-calling loop
├── requirements/         # base / dev / prod
├── docker-compose.yml
├── Dockerfile
└── pytest.ini / conftest.py
```

---

## Getting started (local, without Docker)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements/dev.txt

cp .env.example .env
# For a quick local run without installing Postgres/Redis, set in .env:
#   USE_SQLITE_FOR_DEV=True
#   CELERY_TASK_ALWAYS_EAGER=True

python manage.py migrate
python manage.py createsuperuser
python manage.py seed_demo_data      # optional: creates a demo shop + 30 days of sales history
python manage.py runserver
```

Visit:
- `http://localhost:8000/admin/` — Django admin
- `http://localhost:8000/api/docs/` — interactive Swagger docs
- `http://localhost:8000/api/v1/auth/register/` — create a shop owner account

## Getting started (Docker)

```bash
cp .env.example .env   # fill in ANTHROPIC_API_KEY at minimum for the chatbot
docker compose up --build
```

This starts Postgres, Redis, the Django app, a Celery worker, and Celery Beat.

---

## Multi-tenancy: the `X-Shop-Id` header

A user can belong to multiple shops (via `Membership`), so every
shop-scoped API call must include which shop it's acting on:

```
GET /api/v1/inventory/products/
X-Shop-Id: <shop-uuid>
Authorization: Bearer <jwt>
```

Requests without this header return `404`; requests for a shop the user
isn't a member of return `403`. This is enforced centrally by
`ShopScopedViewSetMixin` (`apps/core/mixins.py`) — individual views never
have to remember to filter by shop themselves.

---

## The AI assistant

```
POST /api/v1/assistant/chat/
X-Shop-Id: <shop-uuid>
{ "message": "How much Tata Salt do I have left?" }
```

Under the hood (`apps/chatbot/services.py`):

1. The message + conversation history is sent to Claude with a set of
   tool definitions (`apps/chatbot/tools.py`).
2. If Claude decides it needs data — e.g. `get_stock_level` — it returns a
   tool-use request instead of text.
3. The tool is executed locally against the real database
   (`apps/chatbot/tools.execute_tool`), and the result is fed back to
   Claude.
4. Claude replies in natural language, grounded entirely in that tool
   result. It cannot report a number it didn't just look up.

Supported tools out of the box: `get_stock_level`, `list_low_stock_products`,
`adjust_stock`, `estimate_stockout`, `create_purchase_order`.

Requires `ANTHROPIC_API_KEY` in `.env`.

---

## Automation (Celery Beat schedule)

Defined in `config/celery.py`:

| Task | Schedule | What it does |
|---|---|---|
| `check_low_stock_levels` | Daily 8:00 AM | Safety-net sweep for low stock (real-time check also fires on every sale) |
| `check_expiring_products` | Daily 8:15 AM | Flags products nearing their expiry date |
| `auto_generate_purchase_orders` | Daily 9:00 AM | Drafts POs (grouped by supplier) for anything low on stock — owner must approve |
| `send_weekly_sales_summary` | Weekly, Monday 7:00 AM | Emails a plain-text stock summary to each shop owner |

Run locally:
```bash
celery -A config worker -l info
celery -A config beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler
```

---

## Running tests

```bash
pytest
```

20 tests covering:
- Stock transaction correctness & overselling prevention (`apps/inventory/tests/test_services.py`)
- REST API behavior & tenant isolation (`apps/inventory/tests/test_api.py`)
- Purchase order automation (`apps/suppliers/tests/test_services.py`)
- AI chatbot tool execution (`apps/chatbot/tests/test_tools.py`)

---

## Possible next steps

- Predictive restocking upgraded from moving-average to a proper time-series model
- WhatsApp/SMS alerts via Twilio alongside email
- Frontend (React or HTMX) consuming the existing REST API
- Multi-currency / multi-language support for the chatbot
- Per-shop customizable alert thresholds and quiet hours
