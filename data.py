import gspread
from oauth2client.service_account import ServiceAccountCredentials
import logging
import datetime
import asyncio

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', scope)
client = gspread.authorize(creds)

marks_buffer = []
committing = False


async def initialize_sheets():
    week_sheets = [ws.title for ws in client.open("NightCrowsApp").worksheets()]
    logging.info(f"Доступные листы с неделями: {week_sheets}")


async def record_mark(nickname, mark_time):
    global marks_buffer, committing
    marks_buffer.append((str(nickname), str(mark_time)))
    logging.info(f"Записанные отметки в буфер: {marks_buffer}")

    if marks_buffer and not committing:
        committing = True
        asyncio.create_task(commit_marks_after_delay())


async def commit_marks_after_delay():
    await asyncio.sleep(61)
    await commit_marks_data()


async def commit_marks_data():
    """Коммитит данные из буфера в Google Sheets."""
    global marks_buffer, committing

    if not marks_buffer:
        logging.info("Буфер пуст, ничего не коммитим.")
        committing = False
        return

    logging.info("Начинаем коммит отметок...")

    try:
        worksheet = await get_week_sheet(4)
        if worksheet is None:
            logging.error("Не удалось получить рабочий лист для недели 4.")
            committing = False
            return

        # Сохраняем ненаписанные данные в новый список
        new_commit_buffer = []

        while marks_buffer:
            batch = marks_buffer[:3]  # Берем первую пачку из 5 записей
            try:
                # Асинхронная запись в Google Sheets
                for nickname, mark_time in batch:
                    row_index = find_or_create_nickname_row(worksheet, nickname)
                    date_index = find_or_create_date_column(worksheet, mark_time)

                    current_value = worksheet.cell(row_index, date_index).value
                    current_value = int(current_value) if current_value and current_value.isdigit() else 0

                    logging.info(f"Обновляем {nickname}: текущее значение {current_value} для даты {mark_time}")

                    new_value = current_value + 1
                    await asyncio.get_event_loop().run_in_executor(None, worksheet.update_cell, row_index, date_index,
                                                                   new_value)

                    logging.info(
                        f"Обновлено значение для {nickname} в столбце {mark_time}: {current_value} -> {new_value}")

            except Exception as e:
                logging.error(f"Ошибка при коммите данных: {e}")
                # Если произошла ошибка, добавляем записи обратно в new_commit_buffer
                new_commit_buffer.extend(batch)
                # Добавляем задержку перед следующей попыткой
                await asyncio.sleep(61)  # Увеличиваем задержку до 61 секунд

            # Успешно обновляем записи, поэтому их можно удалить
            marks_buffer = marks_buffer[3:]  # Удаляем обработанные записи

        # Обновляем основной буфер с теми, которые остались не отправленными
        marks_buffer = new_commit_buffer

        if new_commit_buffer:
            logging.info("Некоторые данные не были отправлены и останутся в буфере для повторной отправки.")
        else:
            logging.info("Все данные успешно коммитятся в таблицу.")

    except Exception as e:
        logging.error(f"Ошибка при коммите отметок: {e}")
    finally:
        committing = False  # Сбрасываем флаг после завершения коммита


def find_or_create_nickname_row(worksheet, nickname):
    nicknames = worksheet.col_values(1)
    if nickname in nicknames:
        return nicknames.index(nickname) + 1
    else:
        worksheet.append_row([nickname] + ['' for _ in range(worksheet.col_count - 1)])
        return len(nicknames) + 1


def find_or_create_date_column(worksheet, target_date):
    column_index = 1
    found = False

    for cell in worksheet.row_values(1):
        if cell.strip() == target_date:
            found = True
            break
        column_index += 1

    if not found:
        worksheet.update_cell(1, column_index, target_date)

    return column_index


async def record_boss_kill(boss_name, kill_time_str, zone, difficulty_level, selected_channel_number):
    try:
        kill_time = datetime.datetime.strptime(kill_time_str, "%d.%m.%Y %H:%M")
        formatted_time = kill_time.strftime("%d.%m.%Y %H:%M")

        logging.info(f"Попытка записи в таблицу: Босс: {boss_name}, Время: {formatted_time}, Зона: {zone}, Сложность: {difficulty_level}, Канал: {selected_channel_number}")
        worksheet = await get_boss_worksheet()

        if worksheet:
            worksheet.append_row([boss_name, formatted_time, zone, difficulty_level, selected_channel_number])
            logging.info("Данные о убийстве босса успешно записаны.")

    except Exception as e:
        logging.error(f"Ошибка при записи: {e}")


async def get_week_sheet(week_number):
    try:
        return client.open("NightCrowsApp").worksheet("Неделя 4")
    except Exception as e:
        logging.error("Ошибка при получении рабочего листа недели %d: %s", week_number, e)
        return None


async def get_boss_worksheet():
    try:
        worksheet = client.open("NightCrowsApp").worksheet("Boss")
        return worksheet
    except Exception as e:
        logging.error("Ошибка при получении рабочего листа Boss: %s", e)
        return None