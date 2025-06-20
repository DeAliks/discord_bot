from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import asyncio
import os
import discord
from dotenv import load_dotenv

load_dotenv()  # Загружаем переменные окружения из .env файла

DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
CHANNEL_ID = 1285475306442063992  # Используйте ID вашего канала

# Создаем intents
intents = discord.Intents.default()
intents.messages = True  # Разрешаем боту получать события сообщений

client = discord.Client(intents=intents)


async def send_message(channel, message):
    await channel.send(message)


async def check_price():
    """Асинхронная функция для проверки цены."""
    chrome_options = Options()
    chrome_options.add_argument("--headless")  # Включаем headless режим
    chrome_options.add_argument("--no-sandbox")  # Убираем песочницу
    chrome_options.add_argument("--disable-dev-shm-usage")  # Отключаем использование памяти Docker

    service = Service()
    driver = webdriver.Chrome(service=service, options=chrome_options)

    try:
        driver.get('https://wemixplay.com/tokens?search=CROW')

        while True:
            driver.refresh()  # Обновляем страницу

            price_element = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.XPATH,
                                                '/html/body/div[1]/div[3]/main/div/div[2]/div/div/div[2]/div[1]/div/article[2]/div/div[1]/div/table/tbody/tr[1]/td[2]/button/div/p'))
            )

            current_price = float(price_element.text.strip().replace('$', ''))
            print(f'Текущая цена токена: ${current_price}')

            if current_price >= 0.75:
                channel = client.get_channel(CHANNEL_ID)
                message = f"@everyone Чеканка CROW доступна! Текущая цена на бирже за 24ч: ${current_price:.2f}"
                await send_message(channel, message)  # Отправляем сообщение
                break

            await asyncio.sleep(900)  # Общая задержка перед следующей проверкой (15 минут)

    except Exception as e:
        print("Ошибка при получении цены токена:", e)
    finally:
        driver.quit()


@client.event
async def on_ready():
    print(f'Зашел как {client.user}')
    await check_price()  # Запускаем проверку цены в основном асинхронном контексте


# Запуск клиента Discord
client.run(DISCORD_TOKEN)