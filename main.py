import os
import discord
import asyncio
import logging
from discord.ext import commands
from dotenv import load_dotenv
import data
import datetime

# Загрузка переменных окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

TOKEN = os.getenv('DISCORD_TOKEN')

# Настройка Intents
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.reactions = True

bot = commands.Bot(command_prefix='!', intents=intents)

BOSS_ALERT_CHANNEL_ID = 1278955149208846356

# Маппинг боссов для разных уровней сложности
boss_mapping_normal = {
    '🐞': "Anggolt",
    '🐎': "Kiaron",
    '🐗': "Grish",
    '🦁': "Inferno"
}

boss_mapping_chaos = {
    '🐞': "Liantte",
    '🐎': "Seyron",
    '🐗': "Gottmol",
    '🦁': "Gehenna"
}

@bot.event
async def on_ready():
    logging.info(f"Мы вошли как {bot.user}")

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    logging.info(
        f"Сообщение получено: {message.content} в канале {message.channel.name} от {message.author.display_name}")

    if message.channel.name == 'arena':
        existing_channels = [channel.name for channel in message.guild.text_channels if
                             channel.name.startswith(f'arena-{message.author.display_name}')]

        if existing_channels:
            await message.channel.send("У вас уже есть открытый подканал: " + existing_channels[0])
            return

        await create_arena_channel(message)

async def create_arena_channel(message):
    logging.info("Создание текстового канала для пользователя: %s", message.author.display_name)

    base_channel_name = f'arena-{message.author.display_name}'
    category = discord.utils.get(message.guild.categories, name='Бот')

    new_channel_name = base_channel_name + '-1'  # Первоначальное имя канала
    logging.info("Попытка создать канал: %s", new_channel_name)

    try:
        channel = await message.guild.create_text_channel(new_channel_name, category=category)
        logging.info("Канал успешно создан: %s", channel.name)
    except Exception as e:
        logging.error("Ошибка при создании канала: %s", e)
        await message.channel.send("Не удалось создать канал. Убедитесь, что у меня есть разрешения.")
        return

    await asyncio.sleep(0.5)

    # Отправка сообщения с выбором сложности
    participation_message = await channel.send("Выберите сложность | Choose the difficulty:\n😇 - Обычный | Normal \n😈 - Хаос | Chaos")

    # Добавляем реакции к сообщению
    await safely_add_reaction(participation_message, "😇")  # 😇 emoji
    await safely_add_reaction(participation_message, "😈")  # 😈 emoji

    try:
        reaction, user = await bot.wait_for('reaction_add', timeout=300.0,
                                            check=lambda r, u: u == message.author and str(r.emoji) in ["😇", "😈"])
        difficulty_level = "Обычный" if str(reaction.emoji) == "😇" else "Хаос"
        logging.info("%s выбрал сложность: %s", message.author.display_name, difficulty_level)

        # В зависимости от выбранной сложности, используем соответствующий список боссов
        if difficulty_level == "Обычный":
            boss_mapping = boss_mapping_normal
            bosses_description = "Выберете босса! Выберите одну из реакций ниже:\n Choose a boss? Choose one of the reactions below:\n" \
                                 "🐞 - Anggolt\n🐎 - Kiaron\n🐗 - Grish\n🦁 - Inferno"
        else:
            boss_mapping = boss_mapping_chaos
            bosses_description = "Выберете босса! Выберите одну из реакций ниже:\n Choose a boss? Choose one of the reactions below:\n" \
                                 "🐞 - Liantte\n🐎 - Seyron\n🐗 - Gottmol\n🦁 - Gehenna"

        # Получение зоны через канал:
        zone_message = await channel.send("Выберите канал, где был убит босс:\nSelect the channel where the boss was killed:\n:one: - Канал 1 | Channel 1\n:two: - Канал 2 | Channel 2")
        await safely_add_reaction(zone_message, "1️⃣")  # Добавляем реакции
        await safely_add_reaction(zone_message, "2️⃣")  # Добавляем реакции

        reaction, user = await bot.wait_for('reaction_add', timeout=300.0,
                                            check=lambda r, u: u == message.author and str(r.emoji) in ["1️⃣", "2️⃣"])
        selected_channel_number = "Канал 1" if str(reaction.emoji) == "1️⃣" else "Канал 2"
        logging.info("%s выбрал канал: %s", message.author.display_name, selected_channel_number)

        # Отправляем описание боссов в зависимости от уровня сложности
        await channel.send(bosses_description)

        boss_message = await channel.send("Пожалуйста, выберите босса, добавив реакцию к этому сообщению.")
        for emoji in boss_mapping.keys():
            await safely_add_reaction(boss_message, emoji)

        reaction, user = await bot.wait_for('reaction_add', timeout=300.0,
                                            check=lambda r, u: u == message.author and str(r.emoji) in boss_mapping.keys())
        boss_name = boss_mapping[str(reaction.emoji)]
        logging.info("%s выбрал босса: %s", message.author.display_name, boss_name)

        await channel.send("Напишите уровень зоны, где был убит босс:\n Write the level of the zone where the boss was killed:")

        try:
            zone_message = await bot.wait_for('message', timeout=300.0,
                                              check=lambda m: m.author == message.author and m.channel == channel)
            zone = zone_message.content.strip()
            logging.info("%s выбрал зону: %s", message.author.display_name, zone)

            kill_time = datetime.datetime.now().strftime("%d.%m.%Y %H:%M")
            await data.record_boss_kill(boss_name, kill_time, zone, difficulty_level, selected_channel_number)

            await channel.send("Данные о убийстве босса успешно записаны в таблицу.")
            await close_channel_after_delay(channel, 10)  # Закрытие канала через 10 секунд

        except asyncio.TimeoutError:
            await channel.send("Вы не указали уровень зоны вовремя. Канал будет закрыт.")
            await close_channel_after_delay(channel, 10)  # Закрыть канал через 10 секунд в случае тайм-аута

    except Exception as e:
        logging.error("Ошибка при создании арены: %s", e)
        await channel.send("Не удалось создать арену.")
        await close_channel_after_delay(channel, 10)  # Закрыть канал через 10 секунд в случае ошибки


async def safely_add_reaction(message, emoji):
    try:
        await message.add_reaction(emoji)
        await asyncio.sleep(0.2)  # Немного подождем между реакциями
    except discord.HTTPException as e:
        if e.status == 429:
            retry_after = e.data.get('retry_after', 0) / 1000.0
            logging.warning(f"Rate limited! Retrying after {retry_after} seconds.")
            await asyncio.sleep(retry_after)
            await safely_add_reaction(message, emoji)


async def close_channel_after_delay(channel, delay):
    logging.info(f"Закрытие канала через {delay} секунд...")
    await asyncio.sleep(delay)
    try:
        await channel.delete()
        logging.info("Канал %s был закрыт после истечения времени", channel.name)
    except discord.NotFound:
        logging.warning("Канал %s уже не существует.", channel.name)
    except Exception as e:
        logging.error("Ошибка при удалении канала: %s", e)


bot.run(TOKEN)