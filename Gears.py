import os
import discord
import logging
import asyncio
from dotenv import load_dotenv
from discord.ext import commands
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import datetime
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

load_dotenv()  # Загружаем переменные окружения

DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')

# Установка логирования
logging.basicConfig(level=logging.INFO)

# Настройка доступа к Google Sheets
def setup_google_sheets():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', scope)
    client = gspread.authorize(creds)
    return client

client = setup_google_sheets()
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)

def authenticate_drive():
    scopes = ['https://www.googleapis.com/auth/drive.file']
    creds = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', scopes)
    return build('drive', 'v3', credentials=creds)

def upload_image(file_path):
    drive_service = authenticate_drive()

    # Создание метаданных для файла
    file_metadata = {
        'name': os.path.basename(file_path),
        'mimeType': 'image/jpeg'  # Укажите правильный тип MIME
    }

    media = MediaFileUpload(file_path, mimetype='image/jpeg')
    file = drive_service.files().create(body=file_metadata, media_body=media, fields='id').execute()

    # Получаем ID загруженного файла
    file_id = file.get('id')
    drive_service.permissions().create(fileId=file_id, body={'role': 'reader', 'type': 'anyone'}).execute()

    # Возвращаем прямую ссылку на файл
    return f'https://drive.google.com/uc?id={file_id}'

@bot.event
async def on_ready():
    logging.info(f'Бот успешно запущен как {bot.user}')

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    if message.channel.name == 'прогресс':  # Проверка канала для сбора данных
        await create_progress_channel(message.guild, message.author)

async def create_progress_channel(guild, user):
    category = discord.utils.get(guild.categories, name='Бот')  # Укажите имя категории, если она есть
    channel_name = f'прогрес-{user.display_name.lower().replace(" ", "-")}'  # Форматирование имени канала

    # Проверка существования подканала
    existing_channel = discord.utils.get(guild.text_channels, name=channel_name)
    if existing_channel:
        await user.send(f"Канал {channel_name} уже существует. Пожалуйста, продолжайте в этом канале.")
        return

    # Создание подканала
    progress_channel = await guild.create_text_channel(channel_name, category=category)

    await progress_channel.send("Заполните данные:\nLevel\nВведите ваш уровень:")
    lvl_msg = await bot.wait_for('message', check=lambda m: m.author == user and m.channel == progress_channel)
    lvl = lvl_msg.content.strip()

    await progress_channel.send("Введите вашу атаку:")
    attack_msg = await bot.wait_for('message', check=lambda m: m.author == user and m.channel == progress_channel)
    attack = attack_msg.content.strip()

    await progress_channel.send("Введите вашу защиту:")
    defence_msg = await bot.wait_for('message', check=lambda m: m.author == user and m.channel == progress_channel)
    defence = defence_msg.content.strip()

    await progress_channel.send("Введите вашу точность:")
    accuracy_msg = await bot.wait_for('message', check=lambda m: m.author == user and m.channel == progress_channel)
    accuracy = accuracy_msg.content.strip()

    await progress_channel.send("Введите ваш Gear Score:")
    gear_score_msg = await bot.wait_for('message', check=lambda m: m.author == user and m.channel == progress_channel)
    gear_score = gear_score_msg.content.strip()

    await progress_channel.send("Прикрепите изображение с вашим Gear Score.")

    def check_image(msg):
        return (msg.attachments and msg.channel == progress_channel and msg.author == user) or \
               (msg.content.startswith("http") and msg.channel == progress_channel and msg.author == user)

    image_msg = await bot.wait_for('message', check=check_image)

    if image_msg.attachments:
        image_file = image_msg.attachments[0]
        local_file_path = f'./{image_file.filename}'  # Сохранение файла локально
        await image_file.save(local_file_path)  # Сохранение файла
        gs_image = upload_image(local_file_path)  # Загрузка на Google Drive
    else:
        gs_image = image_msg.content.strip()  # берём текстовый контент как ссылку

    # Сохранение данных в таблицу Google Sheets
    await record_progress(user.display_name, lvl, gear_score, attack, defence, accuracy, gs_image)

    await progress_channel.send("Данные успешно сохранены! Подканал будет закрыт через 3 минуты.")
    await asyncio.sleep(180)  # 3 минуты ожидания
    await progress_channel.delete()

async def record_progress(nickname, lvl, gear_score, attack, defence, accuracy, image):
    try:
        sheet_name = "GearScore"
        worksheet = client.open("NightCrowsApp").worksheet(sheet_name)

        # Поиск существующего ника в таблице
        nicknames = worksheet.col_values(1)
        if nickname in nicknames:
            row = nicknames.index(nickname) + 1

            # Получаем прошлые значения
            old_lvl = worksheet.cell(row, 2).value
            old_gear_score = worksheet.cell(row, 3).value
            old_attack = worksheet.cell(row, 5).value
            old_defence = worksheet.cell(row, 7).value
            old_accuracy = worksheet.cell(row, 9).value

            # Логируем старые значения
            logging.debug("Старые значения для %s: Уровень=%s, GearScore=%s, Attack=%s, Defence=%s, Accuracy=%s",
                          nickname, old_lvl, old_gear_score, old_attack, old_defence, old_accuracy)

            # Преобразуем значения, убираем пробелы
            old_lvl = int(old_lvl) if old_lvl and old_lvl.isdigit() else 0
            old_gear_score = int(old_gear_score.replace(' ', '').replace(' ', '')) if old_gear_score and old_gear_score.replace(' ', '').replace(' ', '').isdigit() else 0
            old_attack = int(old_attack) if old_attack and old_attack.isdigit() else 0
            old_defence = int(old_defence) if old_defence and old_defence.isdigit() else 0
            old_accuracy = int(old_accuracy) if old_accuracy and old_accuracy.isdigit() else 0

            # Получаем новое значение GearScore
            new_gear_score = int(gear_score.replace(' ', '').replace(' ', ''))  # Очищаем пробелы
            gs_change = new_gear_score - old_gear_score  # Вычисляем изменение GS

            logging.debug("Новые значения: GearScore=%s, Изменение GS=%s", new_gear_score, gs_change)

            # Обновляем таблицу
            worksheet.update_cell(row, 2, int(lvl))
            await asyncio.sleep(0.1)
            worksheet.update_cell(row, 3, new_gear_score)  # Записываем новое значение GearScore
            await asyncio.sleep(0.1)
            worksheet.update_cell(row, 4, gs_change)  # Записываем изменение GearScore
            await asyncio.sleep(0.1)
            worksheet.update_cell(row, 5, int(attack))  # Attack
            # Изменение Attack
            worksheet.update_cell(row, 6, int(attack) - old_attack)
            await asyncio.sleep(0.1)
            worksheet.update_cell(row, 7, int(defence))  # Defence
            worksheet.update_cell(row, 8, int(defence) - old_defence)  # Изменение Defence
            await asyncio.sleep(0.1)
            worksheet.update_cell(row, 9, int(accuracy))  # Accuracy
            worksheet.update_cell(row, 10, int(accuracy) - old_accuracy)  # Изменение Accuracy
            await asyncio.sleep(0.1)
            worksheet.update_cell(row, 11, image)
            await asyncio.sleep(0.1)
            worksheet.update_cell(row, 12, datetime.datetime.now().strftime('%d.%m.%Y'))  # Date
            await asyncio.sleep(0.1)

            logging.info("Данные о прогрессе успешно обновлены для %s", nickname)
        else:
            new_gear_score = int(gear_score.replace(' ', '').replace(' ', ''))  # Очищаем пробелы
            worksheet.append_row([nickname, int(lvl), new_gear_score, '', int(attack), '', int(defence), '',
                                  int(accuracy), '', image, datetime.datetime.now().strftime('%d.%m.%Y')])
            logging.info("Данные о прогрессе успешно записаны для %s", nickname)

        await asyncio.sleep(1)

    except Exception as e:
        logging.error("Ошибка при записи прогресса: %s", e)

bot.run(DISCORD_TOKEN)