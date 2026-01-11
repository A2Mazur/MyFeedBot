import time
import logging

logging.basicConfig(level=logging.INFO)

def main():
    # Пока что тут заглушка, позже тут будет Telethon-сборщик
    while True:
        logging.info("Collector alive")
        time.sleep(10)

if __name__ == "__main__":
    main()
