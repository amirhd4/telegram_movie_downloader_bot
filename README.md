# 🎬 Telegram Movie Distribution Bot

A Telegram bot built with Python that manages and distributes movie content through a controlled access workflow. Users must join required channels and complete a viewing step before receiving access to movie files.

---

## ✨ Features

* Deep-link access for each movie using Telegram start parameters (`/start movie_<id>`)
* Multi-step access verification process
* Membership validation across required Telegram channels
* Simulated post-view confirmation with configurable waiting time
* Admin tools for managing movies and channels
* SQLite database for persistent storage
* Support for movie posters, descriptions, and video files
* Clean and extensible codebase

---

## 🧠 Overview

The bot is designed for controlled movie distribution through Telegram.

For each movie, administrators can generate a unique deep link and place it inside channel posts. When a user clicks the link, the bot guides them through the following process:

1. Verify membership in all required channels.
2. Complete a viewing/waiting step.
3. Receive access to the requested movie.

---

## 🧩 Project Structure

```text
project/
 ├── main.py                # Main bot application
 ├── movies_bot.db          # SQLite database (auto-generated)
 ├── README.md              # Documentation
```

---

## ⚙️ Setup

### 1. Create a Telegram Bot

Create a bot using @BotFather and obtain your bot token.

### 2. Environment Variables

Create a `.env` file or define the following environment variables:

```env
BOT_TOKEN=your_bot_token_here
ADMIN_IDS=123456789,987654321
VIEW_SECONDS=20
DB_PATH=movies_bot.db
```

| Variable     | Description                               |
| ------------ | ----------------------------------------- |
| BOT_TOKEN    | Telegram bot token                        |
| ADMIN_IDS    | Comma-separated list of administrator IDs |
| VIEW_SECONDS | Waiting time before content delivery      |
| DB_PATH      | SQLite database path                      |

---

### 3. Install Dependencies

```bash
pip install python-telegram-bot==22.5
```

### 4. Run the Bot

```bash
python main.py
```

---

## 🛠 Admin Commands

| Command                                      | Description                                |
| -------------------------------------------- | ------------------------------------------ |
| `/addchannel <@username or chat_id> <title>` | Register a required channel                |
| `/listchannels`                              | Display registered channels                |
| `/addmovie`                                  | Add a movie by replying to a video message |
| `/listmovies`                                | Show all movies and generated deep links   |

---

## 📲 User Workflow

1. User clicks a movie button inside a Telegram channel.
2. The bot verifies channel memberships.
3. If all requirements are met, the viewing step becomes available.
4. After the configured waiting period, the movie is delivered.

---

## 📦 Deep Link Format

Administrators can create movie buttons using:

```text
https://t.me/<bot_username>?start=movie_<ID>
```

The movie ID can be obtained from the `/listmovies` command.

---

## 💾 Database

### Tables

* `movies` – Movie metadata, posters, descriptions, and video references
* `channels` – Required channels for membership verification
* `user_state` – Temporary user workflow state

---

## 🧱 Main Components

* `init_db()` – Database initialization
* `start_handler()` – Deep-link entry point
* `callback_check_members()` – Membership verification
* `callback_check_view()` – Waiting-step validation and movie delivery
* Admin management commands
* `main()` – Bot startup and polling

---

## 🚀 Technologies Used

* Python
* python-telegram-bot
* SQLite
* Telegram Bot API

---

## License

This project is intended for educational and demonstration purposes.
