import logging
from datetime import datetime
import pytz
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ConversationHandler, ContextTypes, filters
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

import database as db
import config

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

CHOOSE_FREQUENCY, CHOOSE_DAY, CHOOSE_AMOUNT, ENTER_CUSTOM_AMOUNT, EDIT_AMOUNT = range(5)


def main_menu_keyboard():
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("💰 صدقه فوری"), KeyboardButton("✅ پرداخت کردم")],
            [KeyboardButton("⚙️ تنظیمات من"), KeyboardButton("📊 وضعیت من")],
            [KeyboardButton("ℹ️ راهنما")]
        ],
        resize_keyboard=True
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.init_db()

    existing = db.get_user(user.id)
    if existing:
        await update.message.reply_text(
            f"🌷 *خوش آمدید {user.first_name}*\n\n"
            f"شما قبلاً ثبت‌نام کرده‌اید.\n"
            f"💰 مبلغ: {existing["amount"]:,} تومان\n"
            f"📅 یادآوری: هر {"ماه" if existing["frequency"] == "monthly" else "۱۰ روز"}",
            reply_markup=main_menu_keyboard(),
            parse_mode="Markdown"
        )
        return ConversationHandler.END

    await update.message.reply_text(
        config.WELCOME_MESSAGE,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📝 ثبت‌نام", callback_data="register")],
            [InlineKeyboardButton("ℹ️ راهنما", callback_data="help")]
        ])
    )
    return ConversationHandler.END


async def register_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    keyboard = [
        [InlineKeyboardButton("📅 هر ماه", callback_data="freq_monthly")],
        [InlineKeyboardButton("📆 هر ۱۰ روز", callback_data="freq_10days")]
    ]
    await query.edit_message_text(
        "🗓 *نوع یادآوری خود را انتخاب کنید:*",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    return CHOOSE_FREQUENCY


async def choose_frequency(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    frequency = "monthly" if query.data == "freq_monthly" else "10days"
    context.user_data["frequency"] = frequency

    if frequency == "10days":
        await query.edit_message_text(
            "✅ یادآوری هر ۱۰ روز انتخاب شد.\n\n"
            "📌 *نکته:* یادآوری ۱۰ روزه بر اساس روز ثبت‌نام شما محاسبه می‌شود.\n\n"
            "💰 حالا مبلغ صدقه خود را انتخاب کنید:",
            parse_mode="Markdown"
        )
        return await show_amount_buttons(query, context)
    else:
        days_buttons = []
        for start in range(1, 29, 5):
            row = [
                InlineKeyboardButton(str(i), callback_data=f"day_{i}")
                for i in range(start, min(start + 5, 29))
            ]
            days_buttons.append(row)

        await query.edit_message_text(
            "📅 *روز یادآوری ماهانه را انتخاب کنید (۱ تا ۲۸):*",
            reply_markup=InlineKeyboardMarkup(days_buttons),
            parse_mode="Markdown"
        )
        return CHOOSE_DAY


async def choose_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    day = int(query.data.split("_")[1])
    context.user_data["day"] = day

    await query.edit_message_text(
        f"✅ روز {day} ام هر ماه برای یادآوری شما ثبت شد.\n\n"
        "💰 *مبلغ صدقه ماهانه خود را انتخاب کنید:*",
        parse_mode="Markdown"
    )
    return await show_amount_buttons(query, context)


async def show_amount_buttons(query, context):
    amounts = db.get_custom_amounts()
    keyboard = []
    row = []
    for amount in amounts:
        row.append(InlineKeyboardButton(
            f"{amount:,}", callback_data=f"amt_{amount}"
        ))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("✏️ مبلغ دلخواه", callback_data="amt_custom")])

    await query.edit_message_text(
        "💰 *مبلغ صدقه ماهانه خود را انتخاب کنید:*\n\n"
        "از مبالغ پیشنهادی انتخاب کنید یا مبلغ دلخواه خود را وارد کنید.",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    return CHOOSE_AMOUNT


async def choose_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "amt_custom":
        await query.edit_message_text(
            "✏️ *مبلغ دلخواه خود را به تومان وارد کنید:*\n\n"
            "مثال: ۷۵۰۰۰",
            parse_mode="Markdown"
        )
        return ENTER_CUSTOM_AMOUNT

    amount = int(query.data.split("_")[1])
    context.user_data["amount"] = amount
    return await complete_registration(query, context)


async def enter_custom_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        text = update.message.text.replace(",", "").replace("،", "").strip()
        amount = int(text)
        if amount < 1000 or amount > 100000000:
            await update.message.reply_text(
                "❌ مبلغ باید بین ۱,۰۰۰ تا ۱۰۰,۰۰۰,۰۰۰ تومان باشد."
            )
            return ENTER_CUSTOM_AMOUNT
        context.user_data["amount"] = amount
        return await complete_registration_msg(update, context)
    except ValueError:
        await update.message.reply_text(
            "❌ لطفاً فقط عدد وارد کنید.\n\nمثال: ۵۰۰۰۰"
        )
        return ENTER_CUSTOM_AMOUNT


async def complete_registration(query, context):
    user = query.from_user
    amount = context.user_data["amount"]
    frequency = context.user_data["frequency"]
    day = context.user_data.get("day", 0)

    db.add_user(user.id, user.username, user.first_name, frequency, day, amount)

    freq_text = "ماه" if frequency == "monthly" else "۱۰ روز"
    day_info = f"📆 روز: {day} ام ماه\n" if frequency == "monthly" else "📆 بر اساس تاریخ ثبت‌نام\n"

    await query.edit_message_text(
        f"✅ *ثبت‌نام شما با موفقیت انجام شد*\n\n"
        f"📅 یادآوری: هر {freq_text}\n"
        f"{day_info}"
        f"💰 مبلغ: {amount:,} تومان\n"
        f"🕐 ساعت یادآوری: ۱۹:۰۰\n\n"
        f"از خداوند پاداش نصیب شما باد 🤲",
        parse_mode="Markdown"
    )

    await query.message.reply_text(
        "از منوی زیر استفاده کنید:",
        reply_markup=main_menu_keyboard()
    )
    return ConversationHandler.END


async def complete_registration_msg(update, context):
    user = update.effective_user
    amount = context.user_data["amount"]
    frequency = context.user_data["frequency"]
    day = context.user_data.get("day", 0)

    db.add_user(user.id, user.username, user.first_name, frequency, day, amount)

    freq_text = "ماه" if frequency == "monthly" else "۱۰ روز"
    day_info = f"📆 روز: {day} ام ماه\n" if frequency == "monthly" else "📆 بر اساس تاریخ ثبت‌نام\n"

    await update.message.reply_text(
        f"✅ *ثبت‌نام شما با موفقیت انجام شد*\n\n"
        f"📅 یادآوری: هر {freq_text}\n"
        f"{day_info}"
        f"💰 مبلغ: {amount:,} تومان\n"
        f"🕐 ساعت یادآوری: ۱۹:۰۰\n\n"
        f"از خداوند پاداش نصیب شما باد 🤲",
        parse_mode="Markdown",
        reply_markup=main_menu_keyboard()
    )
    return ConversationHandler.END


async def sadaqah_foori(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db_user = db.get_user(user.id)

    amount = db_user["amount"] if db_user else None
    card = db.get_card_number()
    link = db.get_payment_link()

    msg = "🤲 *صدقه فوری*\n\n"
    if amount:
        msg += f"💰 مبلغ پیشنهادی شما: *{amount:,} تومان*\n\n"
    msg += (
        f"💳 شماره کارت:\n`{card}`\n\n"
        f"🔗 لینک پرداخت:\n{link}\n\n"
        f"⚠️ پس از پرداخت، دکمه «پرداخت کردم» را بزنید."
    )

    await update.message.reply_text(
        msg,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ پرداخت کردم", callback_data="paid_now")]
        ])
    )


async def payment_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db_user = db.get_user(user.id)

    if not db_user:
        await update.message.reply_text(
            "⚠️ شما هنوز ثبت‌نام نکرده‌اید.\n"
            "برای ثبت‌نام روی /start بزنید."
        )
        return

    db.mark_paid(user.id)
    await update.message.reply_text(
        "🌹 *خدا قوت!*\n\n"
        "پرداخت شما ثبت شد. از خداوند پاداش خیر نصیب شما باد. 🤲",
        parse_mode="Markdown"
    )


async def paid_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    db_user = db.get_user(user.id)

    if not db_user:
        await query.edit_message_text("⚠️ شما هنوز ثبت‌نام نکرده‌اید.")
        return

    db.mark_paid(user.id)
    await query.edit_message_text(
        "🌹 *خدا قوت!*\n\n"
        "پرداخت شما ثبت شد. از خداوند پاداش خیر نصیب شما باد. 🤲",
        parse_mode="Markdown"
    )


async def my_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db_user = db.get_user(user.id)

    if not db_user:
        await update.message.reply_text("⚠️ شما هنوز ثبت‌نام نکرده‌اید.")
        return

    freq_text = "ماهانه" if db_user["frequency"] == "monthly" else "هر ۱۰ روز"
    day_text = f"روز {db_user['day']} ام" if db_user["frequency"] == "monthly" else "بر اساس تاریخ ثبت‌نام"

    msg = (
        f"📊 *وضعیت شما*\n\n"
        f"👤 نام: {db_user['first_name']}\n"
        f"💰 مبلغ: {db_user['amount']:,} تومان\n"
        f"📅 نوع یادآوری: {freq_text}\n"
        f"📆 زمان: {day_text}\n"
        f"🕐 ساعت: ۱۹:۰۰\n"
        f"✅ آخرین پرداخت: {db_user.get("last_paid_month") or "هنوز پرداختی ثبت نشده"}"
    )

    await update.message.reply_text(msg, parse_mode="Markdown")


async def my_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db_user = db.get_user(user.id)

    if not db_user:
        await update.message.reply_text("⚠️ شما هنوز ثبت‌نام نکرده‌اید.")
        return

    await update.message.reply_text(
        "⚙️ *تنظیمات*\n\nچه چیزی را می‌خواهید تغییر دهید؟",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("💰 تغییر مبلغ", callback_data="edit_amount")],
            [InlineKeyboardButton("📅 تغییر روز/فرکانس", callback_data="edit_freq")]
        ])
    )


async def edit_amount_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    return await show_amount_buttons(query, context)


async def edit_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "amt_custom":
        await query.edit_message_text(
            "✏️ مبلغ دلخواه جدید را به تومان وارد کنید:"
        )
        return EDIT_AMOUNT

    amount = int(query.data.split("_")[1])
    db.update_user_amount(query.from_user.id, amount)
    await query.edit_message_text(
        f"✅ مبلغ شما به {amount:,} تومان تغییر کرد.",
        parse_mode="Markdown"
    )
    return ConversationHandler.END


async def edit_custom_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = int(update.message.text.replace(",", "").replace("،", ""))
        if amount < 1000 or amount > 100000000:
            await update.message.reply_text("❌ مبلغ نامعتبر است.")
            return EDIT_AMOUNT
        db.update_user_amount(update.effective_user.id, amount)
        await update.message.reply_text(
            f"✅ مبلغ شما به {amount:,} تومان تغییر کرد.",
            parse_mode="Markdown"
        )
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("❌ لطفاً فقط عدد وارد کنید.")
        return EDIT_AMOUNT


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "ℹ️ *راهنما*\n\n"
        "🤖 *این ربات چه کار می‌کند؟*\n"
        "• یادآوری ماهانه/۱۰ روزه برای پرداخت صدقه\n"
        "• ارسال لینک پرداخت و شماره کارت\n"
        "• ثبت پرداخت شما\n\n"
        "📌 *دستورات:*\n"
        "/start - شروع و ثبت‌نام\n"
        "/admin - پنل مدیریت (فقط ادمین)\n"
        "/cancel - لغو عملیات\n\n"
        "از دکمه‌های منو استفاده کنید.",
        parse_mode="Markdown"
    )


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "❌ عملیات لغو شد.",
        reply_markup=main_menu_keyboard()
    )
    return ConversationHandler.END


# ============== پنل ادمین ==============

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != config.ADMIN_ID:
        return

    await update.message.reply_text(
        "🔐 *پنل مدیریت*\n\nگزینه مورد نظر را انتخاب کنید:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("💳 تغییر شماره کارت", callback_data="adm_card")],
            [InlineKeyboardButton("🔗 تغییر لینک پرداخت", callback_data="adm_link")],
            [InlineKeyboardButton("📊 آمار کاربران", callback_data="adm_stats")],
            [InlineKeyboardButton("📢 ارسال پیام سراسری", callback_data="adm_broadcast")]
        ])
    )


async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.from_user.id != config.ADMIN_ID:
        return

    if query.data == "adm_card":
        await query.edit_message_text(
            f"💳 شماره کارت فعلی:\n`{db.get_card_number()}`\n\n"
            "شماره کارت جدید را بفرستید:",
            parse_mode="Markdown"
        )
        context.user_data["admin_action"] = "card"
    elif query.data == "adm_link":
        await query.edit_message_text(
            f"🔗 لینک فعلی:\n{db.get_payment_link()}\n\n"
            "لینک جدید را بفرستید:",
            parse_mode="Markdown"
        )
        context.user_data["admin_action"] = "link"
    elif query.data == "adm_stats":
        users = db.get_all_active_users()
        total = sum(u["amount"] for u in users)
        await query.edit_message_text(
            f"📊 *آمار*\n\n"
            f"👥 کاربران فعال: {len(users)}\n"
            f"💰 مجموع صدقه ماهانه: {total:,} تومان",
            parse_mode="Markdown"
        )
    elif query.data == "adm_broadcast":
        await query.edit_message_text("📢 پیام سراسری خود را بنویسید:")
        context.user_data["admin_action"] = "broadcast"


async def admin_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != config.ADMIN_ID:
        return

    action = context.user_data.get("admin_action")
    if not action:
        return

    text = update.message.text

    if action == "card":
        if text.isdigit() and len(text) >= 13:
            db.set_setting("card_number", text)
            await update.message.reply_text(f"✅ شماره کارت به `{text}` تغییر کرد.", parse_mode="Markdown")
        else:
            await update.message.reply_text("❌ شماره کارت نامعتبر است (باید حداقل ۱۳ رقم باشد).")
    elif action == "link":
        if text.startswith("http"):
            db.set_setting("payment_link", text)
            await update.message.reply_text(f"✅ لینک به {text} تغییر کرد.")
        else:
            await update.message.reply_text("❌ لینک باید با http شروع شود.")
    elif action == "broadcast":
        users = db.get_all_active_users()
        success = 0
        failed = 0
        for user in users:
            try:
                await context.bot.send_message(user["user_id"], text)
                success += 1
            except Exception:
                failed += 1
        await update.message.reply_text(f"✅ پیام به {success} کاربر ارسال شد. ({failed} ناموفق)")

    context.user_data.pop("admin_action", None)


# ============== ارسال یادآوری ==============

async def send_reminders(context: ContextTypes.DEFAULT_TYPE):
    tz = pytz.timezone("Asia/Tehran")
    now = datetime.now(tz)

    users = db.get_all_active_users()
    card = db.get_card_number()
    link = db.get_payment_link()
    global_msg = db.get_global_message()
    current_month = now.strftime("%Y-%m")

    for user in users:
        try:
            should_send = False
            if user["frequency"] == "monthly":
                if now.day == user["day"]:
                    if user.get("last_paid_month") != current_month:
                        should_send = True
            elif user["frequency"] == "10days":
                created_str = user.get("created_at")
                if created_str:
                    try:
                        created = datetime.fromisoformat(created_str)
                        if created.tzinfo is None:
                            created = pytz.timezone("Asia/Tehran").localize(created)
                        days_diff = (now - created).days
                        if days_diff > 0 and days_diff % 10 == 0:
                            if user.get("last_paid_month") != current_month:
                                should_send = True
                    except Exception as e:
                        logger.error(f"Date parse error: {e}")

            if should_send:
                msg = (
                    f"🌷 *یادآوری صدقه*\n\n"
                    f"سلام {user['first_name']} عزیز 🤲\n\n"
                    f"💰 مبلغ شما: *{user['amount']:,} تومان*\n\n"
                    f"💳 شماره کارت:\n`{card}`\n\n"
                    f"🔗 لینک پرداخت:\n{link}\n\n"
                    f"پس از پرداخت دکمه «پرداخت کردم» را بزنید."
                )
                if global_msg:
                    msg += f"\n\n📌 {global_msg}"

                await context.bot.send_message(
                    user["user_id"],
                    msg,
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("✅ پرداخت کردم", callback_data="paid_now")]
                    ])
                )
        except Exception as e:
            logger.error(f"Error sending to {user['user_id']}: {e}")


# ============== راه‌اندازی ==============

def main():
    if not config.BOT_TOKEN or not config.ADMIN_ID:
        print("❌ BOT_TOKEN و ADMIN_ID را در متغیرهای محیطی تنظیم کنید.")
        return

    db.init_db()

    app = Application.builder().token(config.BOT_TOKEN).build()

    register_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(register_start, pattern="^register$")],
        states={
            CHOOSE_FREQUENCY: [CallbackQueryHandler(choose_frequency, pattern="^freq_")],
            CHOOSE_DAY: [CallbackQueryHandler(choose_day, pattern="^day_")],
            CHOOSE_AMOUNT: [CallbackQueryHandler(choose_amount, pattern="^amt_")],
            ENTER_CUSTOM_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_custom_amount)]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )

    edit_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(edit_amount_start, pattern="^edit_amount$")],
        states={
            CHOOSE_AMOUNT: [CallbackQueryHandler(edit_amount, pattern="^amt_")],
            EDIT_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_custom_amount)]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(register_handler)
    app.add_handler(edit_handler)

    app.add_handler(MessageHandler(filters.Regex("^💰 صدقه فوری$"), sadaqah_foori))
    app.add_handler(MessageHandler(filters.Regex("^✅ پرداخت کردم$"), payment_done))
    app.add_handler(MessageHandler(filters.Regex("^📊 وضعیت من$"), my_status))
    app.add_handler(MessageHandler(filters.Regex("^⚙️ تنظیمات من$"), my_settings))
    app.add_handler(MessageHandler(filters.Regex("^ℹ️ راهنما$"), help_command))

    app.add_handler(CallbackQueryHandler(paid_callback, pattern="^paid_now$"))
    app.add_handler(CallbackQueryHandler(admin_callback, pattern="^adm_"))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, admin_message), group=1)

    scheduler = AsyncIOScheduler(timezone=pytz.timezone("Asia/Tehran"))
    scheduler.add_job(
        send_reminders,
        CronTrigger(hour=19, minute=0),
        args=[app]
    )
    scheduler.start()

    print("✅ ربات راه‌اندازی شد.")
    app.run_polling()


if __name__ == "__main__":
    main()
