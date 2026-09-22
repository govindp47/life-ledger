# LifeLedger 📖

**LifeLedger** is a simple, local-first command-line tracker for maintaining balance across the things that matter in everyday life.

Instead of tracking productivity or chasing a score, LifeLedger helps you answer a simpler question:

> **Am I consistently giving attention to the things I consider important?**

For each task, you define a minimum daily **cutoff**. Each day, you record whether you met it.

```text
Exercise
Minimum: At least 30 minutes of physical activity
Done? [y/n]: y
```

Over time, LifeLedger shows your history, consistency, trends, and how evenly your attention is distributed across tasks.

---

## ✨ Features

- 📝 Create and manage daily tasks
- 🎯 Define a minimum cutoff for every task
- ✅ Record daily `YES` / `NO` completion
- 📅 Track historical dates
- 📊 View 7, 30, 90-day and longer-term statistics
- 📈 See consistency and trends over time
- ⚖️ Compare completion rates across tasks
- 🗂️ Archive tasks without losing their history
- 💾 Local SQLite database
- 🔒 Fully offline — no cloud, accounts, or telemetry

### Important

An unrecorded day is **not** treated as a failed day.

LifeLedger distinguishes between:

```text
YES            → cutoff was met
NO             → cutoff was not met
NOT RECORDED   → no entry exists
```

This keeps the statistics faithful to what was actually recorded.

---

## 🛠️ Tech Stack

- Python
- [uv](https://docs.astral.sh/uv/)
- SQLite
- Click
- Rich
- pytest
- Ruff
- mypy

The project uses a simple `src/` layout and avoids unnecessary infrastructure or abstractions.

---

## 🚀 Setup

Clone the repository and enter it:

```bash
git clone <repository-url>
cd life-ledger
```

Create the virtual environment and install dependencies:

```bash
uv sync
```

Run LifeLedger:

```bash
uv run life-ledger --help
```

---

## 📋 Basic Usage

### Add a task

```bash
uv run life-ledger task add
```

You will be asked for:

- Task name
- Minimum cutoff message

For example:

```text
Task name: Exercise
Minimum cutoff: At least 30 minutes of physical activity
```

### List tasks

```bash
uv run life-ledger task list
```

### Track today

```bash
uv run life-ledger today
```

LifeLedger will show each active task and its cutoff, then ask whether the minimum was met.

### Track a specific date

```bash
uv run life-ledger log --date 2026-09-21
```

Existing entries for that date are updated rather than duplicated.

### View a day

```bash
uv run life-ledger show --date 2026-09-21
```

### View history

```bash
uv run life-ledger history
```

Or for a specific task:

```bash
uv run life-ledger history Exercise
```

### View statistics

```bash
uv run life-ledger stats --days 7
uv run life-ledger stats --days 30
uv run life-ledger stats --days 90
```

### View the dashboard

```bash
uv run life-ledger dashboard
```

The dashboard summarizes completion rates, tracking coverage, trends, and the spread between tasks.

---

## ⚖️ Balance

LifeLedger does **not** create an arbitrary "life balance score".

Instead, it exposes transparent measurements such as:

```text
Exercise          83%
Learning          73%
Social            67%
Reading           27%

Highest            83%
Lowest             27%
Spread             56 pp
```

The purpose is to make patterns visible without telling you how you should live.

---

## 🗂️ Task Lifecycle

Removing a task archives it rather than deleting it.

```bash
uv run life-ledger task remove Reading
```

Its historical data remains available.

It can later be restored:

```bash
uv run life-ledger task restore Reading
```

This keeps your personal history intact.

---

## 💾 Data

LifeLedger stores data locally in SQLite.

Your personal database is kept outside the repository by default, so source code and personal tracking data remain separate.

No network connection is required.

---

## 🧪 Development

Run tests:

```bash
uv run pytest
```

Run tests with coverage:

```bash
uv run pytest --cov
```

Format and lint:

```bash
uv run ruff format .
uv run ruff check .
```

Type-check:

```bash
uv run mypy .
```

---

## 🏗️ Project Structure

```text
life-ledger/
├── src/
│   └── life_ledger/
│       ├── cli/
│       ├── domain/
│       ├── storage/
│       └── config.py
│
├── tests/
│   ├── unit/
│   └── integration/
│
├── pyproject.toml
├── uv.lock
└── README.md
```

The application intentionally keeps the architecture small:

```text
CLI
 ↓
Application / Domain
 ↓
Repositories
 ↓
SQLite
```

---

## 📌 Philosophy

LifeLedger is built around a simple idea:

> **Consistency matters, but balance matters too.**

The goal is not to maximize the number of completed tasks.

It is to make long-term patterns visible so you can reflect on where your time and attention are actually going.

---

## License

See [LICENSE](LICENSE).
