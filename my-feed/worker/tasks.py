import asyncio

from worker.celery_app import celery
from bot.short_feed import summarize_to_one_sentence

@celery.task
def ping():
    return "pong"

@celery.task
def summarize_text(text: str) -> str:
    return asyncio.run(summarize_to_one_sentence(text))
