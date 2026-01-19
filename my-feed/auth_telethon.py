from telethon import TelegramClient

api_id = 23244387
api_hash = "2840fa3c42d5caabbbc2f4347b193dc8"

client = TelegramClient("collector2", api_id, api_hash)
client.start()  # попросит телефон/код
print("OK")
client.disconnect()
