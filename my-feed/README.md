# MY FEED

**MY FEED** is a Telegram bot that generates a personal feed of publications from user-selected channels.

---

> Username: @scrollmyfeedbot 

---

- 🚀 A clean feed - no ads, affiliate posts, or trash.
- ⚡ Short posts - long texts are compressed into 1-2 sentences.
- 📜 Summary of the day - all the important news from your channels in one message.
- 💎 VIP mode - up to 50 channels, smart functions, priority speed.

---

**Start project**

*docker compose up --build*

---

### Technology stack:
1) Architecture of a distributed system with microservice interaction via Celery and Redis
2) Telegram bot based on Aiogram 3 for processing user commands and interacting with the API
3) A separate service on Telethon for collecting and analyzing publications from Telegram channels
4) Deploying the system in Docker containers