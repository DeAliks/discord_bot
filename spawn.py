import os
import discord
import logging
import asyncio
import datetime
from discord.ext import commands, tasks
from oauth2client.service_account import ServiceAccountCredentials
import gspread
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Определяем доступы для Google Sheets
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', scope)
client = gspread.authorize(creds)

# Словарь для хранения времени последнего уведомления о спавне для каждого босса
last_notification_time = {}
boss_cache = []
cache_last_update = datetime.datetime.now() - datetime.timedelta(minutes=15)

# Интервалы появления боссов в минутах
boss_spawn_times = {
    "Anggolt": 7 * 60,
    "Kiaron": 9 * 60,
    "Grish": 11 * 60,
    "Inferno": 13 * 60,
    "Liantte": 5 * 60 + 30,
    "Seyron": 6 * 60 + 30,
    "Gottmol": 7 * 60 + 30,
    "Gehenna": 8 * 60 + 30
}

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.reactions = True
bot = commands.Bot(command_prefix='!', intents=intents)

async def get_boss_worksheet():
    retries = 3
    for i in range(retries):
        try:
            worksheet = client.open("NightCrowsApp").worksheet("Boss")
            return worksheet
        except Exception as e:
            logging.error("Ошибка при получении рабочего листа Boss: %s", e)
            if i < retries - 1:  # Если это не последняя попытка
                await asyncio.sleep(61)  # Подождите 61 секунду перед повторной попыткой
    return None

async def update_boss_cache():
    global cache_last_update, boss_cache
    now = datetime.datetime.now()

    if (now - cache_last_update).total_seconds() >= 15 * 60:
        logging.info("Обновление кэша боссов...")
        worksheet = await get_boss_worksheet()
        if worksheet is None:
            logging.error("Не удалось получить рабочий лист Boss.")
            return

        logging.info("Получение данных с рабочего листа...")
        try:
            all_rows = worksheet.get_all_values()[1:]  # Получаем все строки начиная со второй
            boss_cache = []  # Сбрасываем кэш перед обновлением

            for row in all_rows:
                # Проверяем на наличие данных только в первых пяти столбцах
                if len(row) >= 5 and all(row[:5]):
                    try:
                        kill_time = datetime.datetime.strptime(row[1].strip(), "%d.%m.%Y %H:%M")  # Удаляем лишние пробелы
                        boss_cache.append({
                            "name": row[0],
                            "kill_time": row[1],
                            "zone": row[2],
                            "difficulty": row[3],  # Получаем сложность
                            "channel": row[4],  # Получаем канал
                            "row_index": all_rows.index(row) + 2  # Сохраняем индекс строки для удаления
                        })
                    except ValueError as ve:
                        logging.warning("Ошибка при разборе времени: %s. Строка: %s", ve, row[1])
            logging.info(f"Кэш обновлен: {len(boss_cache)} босс(ов) добавлено.")
        except Exception as e:
            logging.error("Ошибка при обновлении кэша: %s", e)
        finally:
            cache_last_update = now

@tasks.loop(minutes=1)
async def check_boss_spawn():
    await update_boss_cache()
    logging.info("Проверка появления боссов...")

    now = datetime.datetime.now()
    category = discord.utils.get(bot.guilds[0].categories, name='Бот')  # Укажите правильные категории
    channel = discord.utils.get(category.text_channels, name='alert_arena')

    for boss in boss_cache:
        boss_name = boss["name"]
        kill_time_str = boss["kill_time"]
        zone = boss["zone"]
        difficulty = boss["difficulty"]
        alert_channel = boss["channel"]
        row_index = boss["row_index"]

        logging.info(f"Обрабатываем босса: {boss_name}")

        if not kill_time_str:
            logging.warning(f"Пропускаем босса {boss_name}, так как kill_time пуст.")
            continue

        try:
            kill_time = datetime.datetime.strptime(kill_time_str, "%d.%m.%Y %H:%M")
        except ValueError as e:
            logging.warning("Ошибка при разборе времени: %s. Строка: %s", e, kill_time_str)
            continue

        next_spawn_time = kill_time + datetime.timedelta(minutes=boss_spawn_times.get(boss_name, 0))
        time_to_spawn = (next_spawn_time - now).total_seconds() / 60
        time_to_spawn = round(time_to_spawn)

        logging.info(f"Босс: {boss_name}, время до появления: {time_to_spawn} минут.")

        if time_to_spawn <= 0:
            logging.info(f"Босс {boss_name} уже появился, пропускаем уведомление.")
            continue

        # Уведомление за 5 минут до появления и добавление реакций
        if 0 < time_to_spawn <= 5:
            if boss_name not in last_notification_time or now >= last_notification_time[boss_name]:
                if channel:
                    msg = await channel.send(f"@everyone Босс \"{boss_name}\" появится в зоне уровня \"{zone}\", "
                                             f"в режиме \"{difficulty}\" на канале \"{alert_channel}\" через {time_to_spawn} минут.")
                    await msg.add_reaction("👍")  # палец вверх
                    await msg.add_reaction("👎")  # палец вниз

                    # Ожидание реакции пользователя
                    def check(reaction, user):
                        return user != bot.user and str(reaction.emoji) in ["👍", "👎"] and reaction.message.id == msg.id
                    try:
                        reaction, user = await bot.wait_for('reaction_add', timeout=3000.0, check=check)
                        # Записываем в таблицу
                        appeared = "Да" if str(reaction.emoji) == "👍" else "Нет"
                        reaction_time = datetime.datetime.now().strftime("%d.%m.%Y %H:%M")
                        await update_boss_status(boss, appeared, reaction_time)
                    except asyncio.TimeoutError:
                        logging.info("Пользователь не отреагировал вовремя.")
                    logging.info(f"Уведомление о спавне босса {boss_name} отправлено в канал для уведомлений.")
                    last_notification_time[boss_name] = now + datetime.timedelta(minutes=5)

                    # Удаление записи из таблицы после отправки уведомления
                    try:
                        logging.info(f"Удаление записи для босса {boss_name} из таблицы.")
                        worksheet = await get_boss_worksheet()  # Получаем обновленный рабочий лист
                        worksheet.delete_row(row_index)  # Удаляем строку из таблицы
                        logging.info(f"Запись для босса {boss_name} успешно удалена.")
                    except Exception as e:
                        logging.error("Ошибка при удалении записи для босса %s: %s", boss_name, e)

        if time_to_spawn > 5:
            logging.info(f"Босс {boss_name} появится позже, чем через 5 минут. Время до появления: {time_to_spawn} минут.")

async def update_boss_status(boss, appeared, reaction_time):
    """Обновляем статус босса в таблице."""
    worksheet = await get_boss_worksheet()
    if worksheet is None:
        logging.error("Не удалось получить рабочий лист Boss.")
        return

    try:
        row_index = boss["row_index"]
        worksheet.update_cell(row_index, 6, appeared)  # Обновляем столбец "Появился" (6-й столбец)
        worksheet.update_cell(row_index, 7, reaction_time)  # Обновляем столбец "Тайм" (7-й столбец)
        logging.info(f"Статус босса {boss['name']} обновлен: {appeared}, Тайм: {reaction_time}")
    except Exception as e:
        logging.error("Ошибка при обновлении статуса босса %s: %s", boss["name"], e)

@bot.event
async def on_ready():
    logging.info(f'Бот успешно запущен как {bot.user}')
    check_boss_spawn.start()  # Запускаем задачу проверки появления боссов

@bot.command(name='s', aliases=['spawn', 'спавн', 'с', 'c', 'ы'])  # Объединяем все команды в одну
async def spawn_bosses(ctx):
    await update_boss_cache()  # Обновляем кэш боссов перед отправкой
    if ctx.channel.id != 1278955149208846356:
        await ctx.send("Эта команда может использоваться только в канале для спавнов.")
        return

    now = datetime.datetime.now()
    response_message = []

    for boss in boss_cache:
        boss_name = boss["name"]
        kill_time_str = boss["kill_time"]
        zone = boss["zone"]
        difficulty = boss["difficulty"]
        alert_channel = boss["channel"]

        if not kill_time_str:
            logging.warning(f"Пропускаем босса {boss_name}, так как kill_time пуст.")
            continue

        try:
            kill_time = datetime.datetime.strptime(kill_time_str, "%d.%m.%Y %H:%M")
        except ValueError as e:
            logging.warning("Ошибка при разборе времени: %s. Строка: %s", e, kill_time_str)
            continue

        next_spawn_time = kill_time + datetime.timedelta(minutes=boss_spawn_times.get(boss_name, 0))
        time_to_spawn = (next_spawn_time - now).total_seconds() / 60

        if time_to_spawn > 5:  # Проверяем, осталось ли больше 5 минут
            response_message.append(
                f"Босс \"{boss_name}\" появится в зоне уровня \"{zone}\", в режиме \"{difficulty}\" на канале \"{alert_channel}\" через {round(time_to_spawn)} минут."
            )

    if response_message:
        await ctx.send("\n".join(response_message))
    else:
        await ctx.send("Нет боссов, которые появятся через более чем 5 минут.")

# Запуск бота
if __name__ == "__main__":
    TOKEN = os.getenv('DISCORD_TOKEN')
    if TOKEN is None:
        logging.error("Токен Discord не найден. Проверьте ваш файл .env.")
    else:
        bot.run(TOKEN)