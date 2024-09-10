import sys
sys.path.append('/path/to/your/module')

import schedule
import time
from datetime import datetime
from telegram import Bot, Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, CallbackContext, ConversationHandler
import asyncio
import logging
import sqlite3
import pytz  # Добавлено для работы с часовыми поясами
from dotenv import load_dotenv
import os

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Определение состояний для ConversationHandlerç
ADDING_TASK = 1
ADDING_REGRESS_PRODUCT = 2

class NotificationBot:
    def __init__(self, token):
        self.application = ApplicationBuilder().token(token).build()
        self.conn_tasks = sqlite3.connect('tasks.db')
        self.conn_notifications = sqlite3.connect('notifications.db')
        self.create_tables()
        
        # Установка команд
        self.set_commands()

        # Добавление обработчиков команд
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("notify", self.notify_command))
        self.application.add_handler(CommandHandler("listtasks", self.list_tasks_command))
        self.application.add_handler(CommandHandler("closetask", self.close_task_command))
        self.application.add_handler(CommandHandler("setnotification", self.set_notification_command))
        self.application.add_handler(CommandHandler("listnotifications", self.list_notifications_command))
        self.application.add_handler(CommandHandler("deletenotification", self.delete_notification_command))
        self.application.add_handler(CommandHandler("useful_links", self.useful_links_command))
        self.application.add_handler(CommandHandler("setregressproduct", self.set_regress_product_command))
        self.application.add_handler(CommandHandler("currentregressproduct", self.current_regress_product_command))
        self.application.add_handler(CommandHandler("remind_fill_table", self.remind_fill_table_command))
        self.application.add_handler(CommandHandler("onboarding", self.onboarding_command))
        
        # Добавление ConversationHandler для добавления задач
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler('addtask', self.add_task_command)],
            states={
                ADDING_TASK: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.save_task)],
                ADDING_REGRESS_PRODUCT: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.save_regress_product)]
            },
            fallbacks=[CommandHandler('cancel', self.cancel_command)]
        )
        self.application.add_handler(conv_handler)
        
        # Планирование всех уведомлений из базы данных
        self.schedule_all_notifications()
        
        # Планирование уведомлений о регрессном продакте
        self.schedule_regress_product_notification()
        
        logger.info("Бот инициализирован")

    def set_commands(self):
        # Установка команд для отображения в интерфейсе Telegram
        commands = [
            ("start", "Запустить бота"),
            ("help", "Помощь"),
            ("notify", "Отправить уведомление во все чаты"),
            ("listtasks", "Список задач в общем списке"),
            ("closetask", "Закрыть задачу по номеру"),
            ("setnotification", "Установить уведомление на определенное время"),
            ("listnotifications", "Список всех уведомлений"),
            ("deletenotification", "Удалить уведомление по номеру"),
            ("addtask", "Добавить задачу в общий список"),
            ("cancel", "Отменить добавление задачи"),
            ("useful_links", "Полезные ссылки"),
            ("setregressproduct", "Установить регрессного продакта"),
            ("currentregressproduct", "Текущий регрессный продакт"),
            ("onboarding", "Информация для новых пользователей")  # Добавлено
        ]
        self.application.bot.set_my_commands(commands)
        logger.info("Команды установлены")

    def create_tables(self):
        # Создание таблиц задач и чатов, если они не существуют
        with self.conn_tasks:
            self.conn_tasks.execute('''
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task TEXT NOT NULL
                )
            ''')
            self.conn_tasks.execute('''
                CREATE TABLE IF NOT EXISTS chats (
                    id INTEGER PRIMARY KEY
                )
            ''')
        with self.conn_notifications:
            self.conn_notifications.execute('''
                CREATE TABLE IF NOT EXISTS notifications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL,
                    time TEXT NOT NULL
                )
            ''')
            self.conn_notifications.execute('''
                CREATE TABLE IF NOT EXISTS regress_product (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL
                )
            ''')
        logger.info("Таблицы созданы или уже существуют")

    async def start_command(self, update: Update, context: CallbackContext):
        # Обработчик команды /start
        chat_id = update.effective_chat.id
        self.add_chat(chat_id)
        await update.message.reply_text("Привет! Я бот для уведомлений. Используйте /help для получения списка команд и /onboarding для ознакомления с ботом.")
        logger.info(f"Команда /start выполнена в чате {chat_id}")

    async def help_command(self, update: Update, context: CallbackContext):
        # Обработчик команды /help
        await update.message.reply_text(
            "Доступные команды:\n"
            "/start - Приветствие\n"
            "/help - Список команд\n"
            "/notify - Отправить уведомления во все чаты\n"
            "/addtask - Добавить задачу в общий список\n"
            "/listtasks - Показать список задач в общем списке\n"
            "/closetask <номер> - Закрыть задачу по номеру\n"
            "/setnotification <время> - Установить уведомление на определенное время\n"
            "/listnotifications - Показать список всех уведомлений\n"
            "/deletenotification <номер> - Удалить уведомление по номеру\n"
            "/useful_links - Полезные ссылки\n"
            "/setregressproduct <@продакт> - Установить регрессного продакта\n"
            "/currentregressproduct - Текущий регрессный продакт\n"
            "/onboarding - Информация для новых пользователей"
        )
        logger.info("Команда /help выполнена")

    async def notify_command(self, update: Update, context: CallbackContext):
        # Обработчик команды /notify
        chat_ids = self.get_chat_ids()
        for chat_id in chat_ids:
            await self.send_task_list(chat_id)
        await update.message.reply_text("Список задач отправлен во все чаты.")
        logger.info("Команда /notify выполнена")

    async def set_notification_command(self, update: Update, context: CallbackContext):
        # Обработчик команды /setnotification
        if len(context.args) != 1:
            await update.message.reply_text("Пожалуйста, введите время для уведомлений в формате ЧЧ:ММ. Пример: /setnotification 13:10")
            return

        notification_time = context.args[0]
        chat_id = update.effective_chat.id

        # Проверка формата времени
        try:
            datetime.strptime(notification_time, "%H:%M")
        except ValueError:
            await update.message.reply_text("Неверный формат времени. Пожалуйста, введите время в формате ЧЧ:ММ.")
            return

        self.add_notification(chat_id, notification_time)
        self.schedule_notification(chat_id, notification_time)
        await update.message.reply_text(f"Уведомления настроены на {notification_time}.")
        logger.info(f"Уведомления для чата {chat_id} настроены на {notification_time}")

        # Отправка списка всех уведомлений
        await self.list_notifications_command(update, context)

    async def list_notifications_command(self, update: Update, context: CallbackContext):
        # Обработчик команды /listnotifications
        notifications = self.get_notifications()
        if notifications:
            notifications_list = "\n".join(f"{i+1}. Чат {chat_id}: {time}" for i, (chat_id, time) in enumerate(notifications))
            await update.message.reply_text(f"Текущие уведомления:\n{notifications_list}")
        else:
            await update.message.reply_text("Список уведомлений пуст.")
        logger.info("Команда /listnotifications выполнена")

    async def delete_notification_command(self, update: Update, context: CallbackContext):
        # Обработчик команды /deletenotification
        try:
            notification_number = int(context.args[0]) - 1
            if self.delete_notification(notification_number):
                await update.message.reply_text(f"Уведомление номер {notification_number + 1} удалено.")
                logger.info(f"Уведомление номер {notification_number + 1} удалено")
            else:
                await update.message.reply_text(f"Уведомление номер {notification_number + 1} не найдено.")
                logger.info(f"Уведомление номер {notification_number + 1} не найдено")
        except (IndexError, ValueError):
            await update.message.reply_text("Пожалуйста, укажите корректный номер уведомления.")
            logger.info("Некорректный номер уведомления для команды /deletenotification")

    def add_chat(self, chat_id):
        # Добавление чата в базу данных
        with self.conn_tasks:
            self.conn_tasks.execute('INSERT OR IGNORE INTO chats (id) VALUES (?)', (chat_id,))
        logger.info(f"Чат {chat_id} добавлен в базу данных")

    def get_chat_ids(self):
        # Получение всех идентификаторов чатов из базы данных
        with self.conn_tasks:
            cursor = self.conn_tasks.execute('SELECT id FROM chats')
            chat_ids = [row[0] for row in cursor.fetchall()]
        return chat_ids

    def add_notification(self, chat_id, time):
        # Добавление уведомления в базу данных
        with self.conn_notifications:
            self.conn_notifications.execute('INSERT INTO notifications (chat_id, time) VALUES (?, ?)', (chat_id, time))
        logger.info(f"Уведомление для чата {chat_id} добавлено на {time}")

    def get_notifications(self):
        # Получение всех уведомлений из базы данных
        with self.conn_notifications:
            cursor = self.conn_notifications.execute('SELECT chat_id, time FROM notifications')
            notifications = cursor.fetchall()
        return notifications

    def delete_notification(self, notification_number):
        # Удаление уведомления по номеру
        notifications = self.get_notifications()
        if 0 <= notification_number < len(notifications):
            notification_to_delete = notifications[notification_number]
            with self.conn_notifications:
                self.conn_notifications.execute('DELETE FROM notifications WHERE chat_id = ? AND time = ?', notification_to_delete)
            logger.info(f"Уведомление для чата {notification_to_delete[0]} на {notification_to_delete[1]} удалено из базы данных")
            return True
        return False

    def schedule_notification(self, chat_id, time):
        # Планирование уведомления
        schedule.every().day.at(time).do(self.schedule_notify, chat_id=chat_id)
        logger.info(f"Уведомление для чата {chat_id} запланровано на {time}")

    def schedule_all_notifications(self):
        # Планирование всех уведомлений из базы данных
        notifications = self.get_notifications()
        for chat_id, time in notifications:
            self.schedule_notification(chat_id, time)
        logger.info(f"Все уведомления запланированы: {notifications}")

    async def list_tasks_command(self, update: Update, context: CallbackContext):
        # Обработчик команды /listtasks
        tasks = self.get_tasks()
        if tasks:
            tasks_list = "\n".join(f"{i+1}. {task}" for i, task in enumerate(tasks))
            await update.message.reply_text(f"Текущие задачи:\n{tasks_list}")
        else:
            await update.message.reply_text("Список задач пуст.")
        logger.info("Команда /listtasks выполнена")

    async def add_task_command(self, update: Update, context: CallbackContext):
        # Обработчик команды /addtask
        await update.message.reply_text("Пожалуйста, введите задачу, которую хотите добавить.")
        return ADDING_TASK

    async def save_task(self, update: Update, context: CallbackContext):
        # Сохранение новой задачи
        task = update.message.text
        self.add_task(task)
        await update.message.reply_text(f"Задача '{task}' добавлена.")
        logger.info(f"Добавлена задача: {task}")
        return ConversationHandler.END

    async def cancel_command(self, update: Update, context: CallbackContext):
        # Обработчик команды /cancel
        await update.message.reply_text("Добавление задачи отменено.")
        return ConversationHandler.END

    async def close_task_command(self, update: Update, context: CallbackContext):
        # Обработчик команды /closetask
        try:
            task_number = int(context.args[0]) - 1
            if self.delete_task(task_number):
                await update.message.reply_text(f"Задача номер {task_number + 1} закрыта.")
                logger.info(f"Задача номер {task_number + 1} закрыта")
            else:
                await update.message.reply_text(f"Задача номер {task_number + 1} не найдена.")
                logger.info(f"Задача номер {task_number + 1} не найдена")
        except (IndexError, ValueError):
            await update.message.reply_text("Пожалуйста, укажите корректный номер задачи.")
            logger.info("Некорректный номер задачи для команды /closetask")

    async def send_task_list(self, chat_id):
        # Метод для отправки списка задач
        tasks = self.get_tasks()
        if tasks:
            tasks_list = "\n".join(f"{i+1}. {task}" for i, task in enumerate(tasks))
            await self.application.bot.send_message(chat_id=chat_id, text=f"Текущие задачи:\n{tasks_list}")
        else:
            await self.application.bot.send_message(chat_id=chat_id, text="Список задач пуст.")
        logger.info(f"Список задач отправлен в чат {chat_id}")

    def add_task(self, task):
        # Добавление задачи в базу данных
        with self.conn_tasks:
            self.conn_tasks.execute('INSERT INTO tasks (task) VALUES (?)', (task,))
        logger.info(f"Задача '{task}' добавлена в базу данных")

    def get_tasks(self):
        # Получение всех задач из базы данных
        with self.conn_tasks:
            cursor = self.conn_tasks.execute('SELECT task FROM tasks')
            tasks = [row[0] for row in cursor.fetchall()]
        return tasks

    def delete_task(self, task_number):
        # Удаление задачи по номеру
        tasks = self.get_tasks()
        if 0 <= task_number < len(tasks):
            task_to_delete = tasks[task_number]
            with self.conn_tasks:
                self.conn_tasks.execute('DELETE FROM tasks WHERE task = ?', (task_to_delete,))
            logger.info(f"Задача '{task_to_delete}' удалена из базы данных")
            return True
        return False

    async def start(self):
        # Метод для запуска бота
        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling(drop_pending_updates=True)
        logger.info("Бот запущен и работает в режиме polling")

    async def run_scheduler(self):
        # Метод для запуска шедулера
        while True:
            schedule.run_pending()
            await asyncio.sleep(1)

    def schedule_notify(self, chat_id):
        # Метод для планирования уведомлений
        asyncio.run_coroutine_threadsafe(self.notify_chat(chat_id), asyncio.get_event_loop())
        logger.info(f"Запланированное уведомление отправлено в чат {chat_id}")

    async def notify_chat(self, chat_id):
        # Метод для отправки уведомлений в чат
        await self.send_task_list(chat_id)
        logger.info(f"Уведомление отправлено в чат {chat_id}")

    async def run(self):
        # Метод для запуска бота и шедулера
        try:
            await asyncio.gather(self.start(), self.run_scheduler())
        except asyncio.CancelledError:
            logger.info("Завершение работы бота и шедулера")

    async def useful_links_command(self, update: Update, context: CallbackContext):
        # Обработчик команды /useful_links
        try:
            with open('useful_links.txt', 'r', encoding='utf-8') as file:
                links = file.read()
            await update.message.reply_text(links)
            logger.info("Команда /useful_links выполнена")
        except FileNotFoundError:
            await update.message.reply_text("Файл с полезными ссылками не найден.")
            logger.error("Файл useful_links.txt не найден")

    async def set_regress_product_command(self, update: Update, context: CallbackContext):
        # Обработчик команды /setregressproduct
        if len(context.args) != 1 or not context.args[0].startswith('@'):
            await update.message.reply_text("Пожалуйста, введите имя регрессного продакта в формате @имя. Пример: /setregressproduct @product_name")
            return

        regress_product = context.args[0]
        self.add_regress_product(regress_product)
        await update.message.reply_text(f"Регрессный продакт '{regress_product}' установлен.")
        logger.info(f"Регрессный продакт '{regress_product}' установлен")

    async def save_regress_product(self, update: Update, context: CallbackContext):
        # Сохранение регрессного продакта
        regress_product = update.message.text
        self.add_regress_product(regress_product)
        await update.message.reply_text(f"Регрессный продакт '{regress_product}' добавлен.")
        logger.info(f"Добавлен регрессный продакт: {regress_product}")
        return ConversationHandler.END

    def add_regress_product(self, name):
        # Добавление регрессного продакта в базу данных
        with self.conn_notifications:
            self.conn_notifications.execute('INSERT INTO regress_product (name) VALUES (?)', (name,))
        logger.info(f"Регрессный продакт '{name}' добавлен в базу данных")

    async def current_regress_product_command(self, update: Update, context: CallbackContext):
        # Обработчик команды /currentregressproduct
        if context.args:
            regress_product = context.args[0]
            self.add_regress_product(regress_product)
            await update.message.reply_text(f"Регрессный продакт '{regress_product}' установлен.")
            logger.info(f"Регрессный продакт '{regress_product}' установлен")
        else:
            regress_product = self.get_current_regress_product()
            if regress_product:
                await update.message.reply_text(f"Текущий регрессный продакт: {regress_product}.\n\nДорогой, ты сегодня регрессный продакт.\nПросьба обновить tnps и отзывы. Вот ссылка: https://docs.google.com/spreadsheets/d/18kJ5GEui0bA0GiGiwe_ZUQd2l7-iwVe4QUCzvJLfmac/edit?usp=sharing")
            else:
                await update.message.reply_text("Регрессный продакт не установлен.")
            logger.info("Команда /currentregressproduct выполнена")

    def get_current_regress_product(self):
        # Получение текущего регрессного продакта из базы данных
        with self.conn_notifications:
            cursor = self.conn_notifications.execute('SELECT name FROM regress_product ORDER BY id DESC LIMIT 1')
            result = cursor.fetchone()
        return result[0] if result else None

    def schedule_regress_product_notification(self):
        # Планирование уведомлений о регрессном продакте
        schedule.every().wednesday.at("12:00").do(self.schedule_regress_product_notify)
        logger.info("Уведомления о регрессном продакте запланированы на каждую среду в 12:00 по Москве")

    def schedule_regress_product_notify(self):
        # Метод для планирования уведомлений о регрессном продакте
        chat_ids = self.get_chat_ids()
        for chat_id in chat_ids:
            asyncio.run_coroutine_threadsafe(self.notify_regress_product(chat_id), asyncio.get_event_loop())
        logger.info("Запланированное уведомление о регрессном продакте отправлено во все чаты")

    async def notify_regress_product(self, chat_id):
        # Метод для отправки уведомлений о регрессном продакте в чат
        regress_product = self.get_current_regress_product()
        if regress_product:
            message = f"Дорогой, ты сегодня регрессный продакт. Просьба обновить tnps и отзывы. Вот ссылка: https://docs.google.com/spreadsheets/d/18kJ5GEui0bA0GiGiwe_ZUQd2l7-iwVe4QUCzvJLfmac/edit?usp=sharing"
            await self.application.bot.send_message(chat_id=chat_id, text=message)
            logger.info(f"Уведомление о регрессном продакте отправлено в чат {chat_id}")
        else:
            logger.info("Регрессный продакт не установлен, уведомление не отправлено")

    async def remind_fill_table_command(self, update: Update, context: CallbackContext):
        # Скрытая команда для отправки напоминаний о заполнении таблички
        chat_id = update.effective_chat.id
        message = "Напоминание: Пожалуйста, заполните табличку. Вот ссылка: https://docs.google.com/spreadsheets/d/18kJ5GEui0bA0GiGiwe_ZUQd2l7-iwVe4QUCzvJLfmac/edit?usp=sharing"
        await self.application.bot.send_message(chat_id=chat_id, text=message)
        logger.info(f"Напоминание о заполнении таблички отправлено в чат {chat_id}")

    async def onboarding_command(self, update: Update, context: CallbackContext):
        # Обработчик команды /onboarding
        message = (
            "Добро пожаловать! Я бот для уведомлений и управления задачами. Вот как я могу вам помочь:\n\n"
            "1. **Запуск и помощь**:\n"
            "   - /start: Запустить бота и добавить текущий чат в базу данных.\n"
            "   - /help: Показать список всех доступных команд.\n\n"
            "2. **Управление задачами**:\n"
            "   - /addtask: Начать процесс добавления новой задачи.\n"
            "   - /listtasks: Показать список всех текущих задач.\n"
            "   - /closetask <номер>: Закрыть задачу по её номеру.\n\n"
            "3. **Уведомления**:\n"
            "   - /setnotification <время>: Установить ежедневное уведомление на указанное время (формат ЧЧ:ММ).\n"
            "   - /listnotifications: Показать список всех текущих уведомлений.\n"
            "   - /deletenotification <номер>: Удалить уведомление по его номеру.\n"
            "   - /notify: Отправить список задач во все чаты.\n\n"
            "4. **Полезные ссылки**:\n"
            "   - /useful_links: Показать список полезных ссылок.\n\n"
            "5. **Регрессный продакт**:\n"
            "   - /setregressproduct <@имя>: Установить текущего регрессного продакта.\n"
            "   - /currentregressproduct: Показать текущего регрессного продакта.\n\n"
            "6. **Напоминания**:\n"
            "   - /remind_fill_table: Отправить напоминание о заполнении таблички.\n\n"
            "Если у вас есть вопросы или нужна помощь, используйте команду /help. Удачи!"
        )
        await update.message.reply_text(message)
        logger.info("Команда /onboarding выполнена")

if __name__ == "__main__":
    load_dotenv()
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    
    if not token:
        logger.error("Токен не найден в файле .env")
    else:
        bot = NotificationBot(token)
        try:
            asyncio.run(bot.run())
        except KeyboardInterrupt:
            logger.info("Бот остановлен пользователем")
