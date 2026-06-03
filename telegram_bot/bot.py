import os

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

from app.services import bar_widget, soccer


FLOW_KEY = "bar_widget_flow"


def allowed_chat_ids():
    raw = os.getenv("TELEGRAM_ALLOWED_CHAT_IDS", "")
    ids = set()
    for part in raw.replace(";", ",").split(","):
        text = part.strip()
        if not text:
            continue
        try:
            ids.add(int(text))
        except ValueError:
            continue
    return ids


def is_authorized(update):
    chat = update.effective_chat
    allowed = allowed_chat_ids()
    return bool(chat and allowed and chat.id in allowed)


async def deny(update):
    if update.callback_query:
        await update.callback_query.answer("Not authorized", show_alert=True)
        return
    if update.message:
        await update.message.reply_text("This chat is not authorized to control the bacheca. Use /my_id to see the chat ID.")


def chat_id_text(update):
    chat = update.effective_chat
    if not chat:
        return "unknown"
    return str(chat.id)


def main_keyboard():
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Show", callback_data="show"),
                InlineKeyboardButton("Hide", callback_data="hide"),
            ],
            [
                InlineKeyboardButton("Announcement", callback_data="announce_menu"),
                InlineKeyboardButton("Countdown", callback_data="countdown_menu"),
            ],
            [
                InlineKeyboardButton("Color", callback_data="color_menu"),
                InlineKeyboardButton("Soccer", callback_data="soccer_menu"),
            ],
            [
                InlineKeyboardButton("Status", callback_data="status"),
                InlineKeyboardButton("Help", callback_data="help"),
            ],
        ]
    )


def announcement_keyboard():
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("One-shot", callback_data="ann_one")],
            [InlineKeyboardButton("Periodic daily", callback_data="ann_daily")],
            [InlineKeyboardButton("Periodic weekly", callback_data="ann_weekly")],
            [InlineKeyboardButton("Clear announcements", callback_data="ann_clear_confirm")],
            [InlineKeyboardButton("Back", callback_data="panel")],
        ]
    )


def countdown_keyboard():
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Set countdown", callback_data="countdown_set")],
            [InlineKeyboardButton("Clear countdown", callback_data="countdown_clear_confirm")],
            [InlineKeyboardButton("Back", callback_data="panel")],
        ]
    )


def color_keyboard():
    rows = [
        [
            InlineKeyboardButton("Blue", callback_data="color:blue"),
            InlineKeyboardButton("Green", callback_data="color:green"),
        ],
        [
            InlineKeyboardButton("Red", callback_data="color:red"),
            InlineKeyboardButton("Orange", callback_data="color:orange"),
        ],
        [
            InlineKeyboardButton("Purple", callback_data="color:purple"),
            InlineKeyboardButton("Teal", callback_data="color:teal"),
        ],
        [
            InlineKeyboardButton("Gray", callback_data="color:gray"),
            InlineKeyboardButton("Dark", callback_data="color:dark"),
        ],
        [InlineKeyboardButton("Custom #RRGGBB", callback_data="color_custom")],
        [InlineKeyboardButton("Back", callback_data="panel")],
    ]
    return InlineKeyboardMarkup(rows)


def soccer_keyboard():
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Enable", callback_data="soccer_on"),
                InlineKeyboardButton("Disable", callback_data="soccer_off"),
            ],
            [InlineKeyboardButton("Choose competition", callback_data="soccer_comp_menu")],
            [InlineKeyboardButton("Back", callback_data="panel")],
        ]
    )


def soccer_competition_keyboard():
    rows = []
    row = []
    for choice in soccer.competition_choices():
        row.append(InlineKeyboardButton(choice["label"], callback_data="soccer_comp:" + choice["code"]))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton("Back", callback_data="soccer_menu")])
    return InlineKeyboardMarkup(rows)


def confirm_keyboard(yes_data, no_data):
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Confirm", callback_data=yes_data),
                InlineKeyboardButton("Cancel", callback_data=no_data),
            ]
        ]
    )


def status_text():
    state = bar_widget.load_state()
    soccer_state = state.get("soccer") or {}
    countdown = state.get("countdown")
    parts = [
        "Bacheca bar panel",
        "Visible: " + ("yes" if state.get("visible") else "no"),
        "Color: " + str(state.get("color")),
        "Announcements: " + str(len(state.get("announcements") or [])) + " (" + bar_widget.ANNOUNCEMENT_POLICY + ")",
        "Countdown: " + (countdown.get("to") if countdown else "none"),
        "Soccer: " + ("on" if soccer_state.get("enabled") else "off") + " " + str(soccer_state.get("competition") or "SA"),
    ]
    return "\n".join(parts)


def help_text():
    return "\n".join(
        [
            "Available commands:",
            "/start - show this introduction",
            "/panel - open the button panel",
            "/my_id - show this chat ID",
            "/show and /hide - toggle the bar",
            "/announce Text | 2026-06-03T22:00:00+02:00 - one-shot announcement starting now",
            "/countdown Label | 2026-06-03T20:00:00+02:00 - set a countdown",
            "/color blue or /color #1565C0 - change the bar color",
            "/soccer SA - select a competition",
            "/soccer_on and /soccer_off - toggle soccer",
            "/cancel - stop a guided flow",
        ]
    )


def start_text(update):
    return "\n".join(
        [
            "Welcome to the Torrescalla Bacheca bar controller.",
            "This bot controls the compact dashboard bar: announcements, countdowns, colors, visibility, and soccer snippets.",
            "Your chat ID: " + chat_id_text(update),
            "",
            status_text(),
            "",
            help_text(),
        ]
    )


def unauthorized_start_text(update):
    return "\n".join(
        [
            "Welcome to the Torrescalla Bacheca bar controller.",
            "This chat is not authorized to control the dashboard yet.",
            "Your chat ID: " + chat_id_text(update),
            "Ask an administrator to add this ID to TELEGRAM_ALLOWED_CHAT_IDS.",
            "",
            "Available commands:",
            "/my_id - show this chat ID",
        ]
    )


async def send_panel(update, text=None):
    message = text or status_text()
    if update.callback_query:
        await update.callback_query.edit_message_text(message, reply_markup=main_keyboard())
    elif update.message:
        await update.message.reply_text(message, reply_markup=main_keyboard())


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        await update.message.reply_text(unauthorized_start_text(update))
        return
    context.user_data.pop(FLOW_KEY, None)
    await update.message.reply_text(start_text(update), reply_markup=main_keyboard())


async def panel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        await deny(update)
        return
    context.user_data.pop(FLOW_KEY, None)
    await send_panel(update)


async def my_id_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = chat_id_text(update)
    authorized = "yes" if is_authorized(update) else "no"
    await update.message.reply_text("Chat ID: " + chat_id + "\nAuthorized: " + authorized)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        await deny(update)
        return
    await update.message.reply_text(help_text(), reply_markup=main_keyboard())


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        await deny(update)
        return
    context.user_data.pop(FLOW_KEY, None)
    await update.message.reply_text("Cancelled.", reply_markup=main_keyboard())


async def callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        await deny(update)
        return

    query = update.callback_query
    data = query.data or ""
    await query.answer()

    if data == "panel":
        context.user_data.pop(FLOW_KEY, None)
        await send_panel(update)
    elif data == "status":
        await query.edit_message_text(status_text(), reply_markup=main_keyboard())
    elif data == "help":
        await query.edit_message_text(help_text(), reply_markup=main_keyboard())
    elif data == "show":
        bar_widget.set_visible(True)
        await query.edit_message_text("Bar shown.", reply_markup=main_keyboard())
    elif data == "hide":
        bar_widget.set_visible(False)
        await query.edit_message_text("Bar hidden.", reply_markup=main_keyboard())
    elif data == "announce_menu":
        await query.edit_message_text("Choose announcement type.", reply_markup=announcement_keyboard())
    elif data == "ann_one":
        start_flow(context, "one_shot", "text", {})
        await query.edit_message_text("Send announcement text. Emojis are OK. Use /cancel to stop.")
    elif data == "ann_daily":
        start_flow(context, "periodic", "text", {"frequency": "daily", "days": [0, 1, 2, 3, 4, 5, 6]})
        await query.edit_message_text("Send daily announcement text. It will use every day. Use /cancel to stop.")
    elif data == "ann_weekly":
        start_flow(context, "periodic", "text", {"frequency": "weekly"})
        await query.edit_message_text("Send weekly announcement text. Emojis are OK. Use /cancel to stop.")
    elif data == "ann_clear_confirm":
        await query.edit_message_text("Clear all announcements?", reply_markup=confirm_keyboard("ann_clear_yes", "announce_menu"))
    elif data == "ann_clear_yes":
        bar_widget.clear_announcements()
        await query.edit_message_text("Announcements cleared.", reply_markup=main_keyboard())
    elif data == "countdown_menu":
        await query.edit_message_text("Countdown controls.", reply_markup=countdown_keyboard())
    elif data == "countdown_set":
        start_flow(context, "countdown", "label", {})
        await query.edit_message_text("Send countdown label, for example: Manca. Use /cancel to stop.")
    elif data == "countdown_clear_confirm":
        await query.edit_message_text("Clear countdown?", reply_markup=confirm_keyboard("countdown_clear_yes", "countdown_menu"))
    elif data == "countdown_clear_yes":
        bar_widget.clear_countdown()
        await query.edit_message_text("Countdown cleared.", reply_markup=main_keyboard())
    elif data == "color_menu":
        await query.edit_message_text("Choose a safe bar color.", reply_markup=color_keyboard())
    elif data.startswith("color:"):
        apply_color(data.split(":", 1)[1])
        await query.edit_message_text("Color updated.", reply_markup=main_keyboard())
    elif data == "color_custom":
        start_flow(context, "color", "value", {})
        await query.edit_message_text("Send a color as #RRGGBB or a preset name.")
    elif data == "soccer_menu":
        await query.edit_message_text("Soccer controls.", reply_markup=soccer_keyboard())
    elif data == "soccer_on":
        bar_widget.set_soccer_enabled(True)
        await query.edit_message_text("Soccer enabled.", reply_markup=main_keyboard())
    elif data == "soccer_off":
        bar_widget.set_soccer_enabled(False)
        await query.edit_message_text("Soccer disabled.", reply_markup=main_keyboard())
    elif data == "soccer_comp_menu":
        await query.edit_message_text("Choose competition.", reply_markup=soccer_competition_keyboard())
    elif data.startswith("soccer_comp:"):
        code = data.split(":", 1)[1]
        bar_widget.set_soccer_competition(code)
        await query.edit_message_text("Competition set to " + soccer.competition_label(code) + ".", reply_markup=main_keyboard())


def start_flow(context, name, step, data):
    context.user_data[FLOW_KEY] = {
        "name": name,
        "step": step,
        "data": data,
    }


async def flow_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        await deny(update)
        return

    flow = context.user_data.get(FLOW_KEY)
    if not flow:
        await update.message.reply_text("Use /panel to open the controls.", reply_markup=main_keyboard())
        return

    try:
        if flow["name"] == "one_shot":
            await handle_one_shot_flow(update, context, flow)
        elif flow["name"] == "periodic":
            await handle_periodic_flow(update, context, flow)
        elif flow["name"] == "countdown":
            await handle_countdown_flow(update, context, flow)
        elif flow["name"] == "color":
            await handle_color_flow(update, context, flow)
    except Exception as error:
        await update.message.reply_text("That did not work: " + str(error) + "\nUse /cancel to stop or send another value.")


async def handle_one_shot_flow(update, context, flow):
    text = clean_message(update)
    data = flow["data"]
    if flow["step"] == "text":
        data["text"] = text
        flow["step"] = "starts"
        await update.message.reply_text("Send start datetime as ISO, or send now.")
    elif flow["step"] == "starts":
        data["startsAt"] = bar_widget.now() if text.lower() == "now" else bar_widget.parse_datetime(text)
        flow["step"] = "ends"
        await update.message.reply_text("Send end datetime as ISO. Every announcement must end.")
    elif flow["step"] == "ends":
        data["endsAt"] = bar_widget.parse_datetime(text)
        bar_widget.add_one_shot_announcement(data["text"], data["startsAt"], data["endsAt"])
        context.user_data.pop(FLOW_KEY, None)
        await update.message.reply_text("Announcement saved.", reply_markup=main_keyboard())


async def handle_periodic_flow(update, context, flow):
    text = clean_message(update)
    data = flow["data"]
    if flow["step"] == "text":
        data["text"] = text
        if data.get("frequency") == "weekly":
            flow["step"] = "days"
            await update.message.reply_text("Send days as numbers: 0=Mon ... 6=Sun, comma separated. Example: 0,2,4")
        else:
            flow["step"] = "start_time"
            await update.message.reply_text("Send occurrence start time, for example 19:30.")
    elif flow["step"] == "days":
        data["days"] = parse_days(text)
        flow["step"] = "start_time"
        await update.message.reply_text("Send occurrence start time, for example 19:30.")
    elif flow["step"] == "start_time":
        data["startTime"] = bar_widget.format_time(text)
        flow["step"] = "duration"
        await update.message.reply_text("Send occurrence duration in minutes, for example 90.")
    elif flow["step"] == "duration":
        data["durationMinutes"] = int(text)
        if data["durationMinutes"] <= 0:
            raise ValueError("Duration must be positive")
        flow["step"] = "recurrence_ends"
        await update.message.reply_text("Send recurrence end datetime as ISO.")
    elif flow["step"] == "recurrence_ends":
        data["recurrenceEndsAt"] = bar_widget.parse_datetime(text)
        bar_widget.add_periodic_announcement(
            data["text"],
            data["frequency"],
            data["days"],
            data["startTime"],
            data["recurrenceEndsAt"],
            duration_minutes=data["durationMinutes"],
        )
        context.user_data.pop(FLOW_KEY, None)
        await update.message.reply_text("Periodic announcement saved.", reply_markup=main_keyboard())


async def handle_countdown_flow(update, context, flow):
    text = clean_message(update)
    data = flow["data"]
    if flow["step"] == "label":
        data["label"] = text
        flow["step"] = "target"
        await update.message.reply_text("Send countdown target datetime as ISO.")
    elif flow["step"] == "target":
        target = bar_widget.parse_datetime(text)
        bar_widget.set_countdown(data["label"], target)
        context.user_data.pop(FLOW_KEY, None)
        await update.message.reply_text("Countdown saved.", reply_markup=main_keyboard())


async def handle_color_flow(update, context, flow):
    text = clean_message(update)
    apply_color(text)
    context.user_data.pop(FLOW_KEY, None)
    await update.message.reply_text("Color updated.", reply_markup=main_keyboard())


def clean_message(update):
    return str(update.message.text or "").strip()


def parse_days(text):
    days = []
    for part in text.replace(";", ",").split(","):
        cleaned = part.strip()
        if not cleaned:
            continue
        day = int(cleaned)
        if day < 0 or day > 6:
            raise ValueError("Days must be 0-6")
        if day not in days:
            days.append(day)
    if not days:
        raise ValueError("At least one day is required")
    return sorted(days)


def apply_color(value):
    bar_widget.set_color(value)


async def show_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        await deny(update)
        return
    bar_widget.set_visible(True)
    await update.message.reply_text("Bar shown.", reply_markup=main_keyboard())


async def hide_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        await deny(update)
        return
    bar_widget.set_visible(False)
    await update.message.reply_text("Bar hidden.", reply_markup=main_keyboard())


async def color_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        await deny(update)
        return
    value = " ".join(context.args).strip()
    if not value:
        await update.message.reply_text("Usage: /color blue or /color #1565C0")
        return
    try:
        apply_color(value)
    except ValueError as error:
        await update.message.reply_text(str(error))
        return
    await update.message.reply_text("Color updated.", reply_markup=main_keyboard())


async def announce_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        await deny(update)
        return
    raw = " ".join(context.args).strip()
    if "|" not in raw:
        await update.message.reply_text("Usage: /announce Text | 2026-06-03T22:00:00+02:00")
        return
    text, end_text = [part.strip() for part in raw.split("|", 1)]
    try:
        bar_widget.add_one_shot_announcement(text, bar_widget.now(), bar_widget.parse_datetime(end_text))
    except Exception as error:
        await update.message.reply_text(str(error))
        return
    await update.message.reply_text("Announcement saved.", reply_markup=main_keyboard())


async def countdown_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        await deny(update)
        return
    raw = " ".join(context.args).strip()
    if not raw:
        await update.message.reply_text("Usage: /countdown Label | 2026-06-03T20:00:00+02:00")
        return
    if "|" in raw:
        label, target_text = [part.strip() for part in raw.split("|", 1)]
    else:
        label = "Manca"
        target_text = raw
    try:
        bar_widget.set_countdown(label, bar_widget.parse_datetime(target_text))
    except Exception as error:
        await update.message.reply_text(str(error))
        return
    await update.message.reply_text("Countdown saved.", reply_markup=main_keyboard())


async def soccer_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        await deny(update)
        return
    code = " ".join(context.args).strip()
    if not code:
        await update.message.reply_text("Usage: /soccer SA", reply_markup=soccer_competition_keyboard())
        return
    bar_widget.set_soccer_competition(code)
    await update.message.reply_text("Competition set to " + soccer.competition_label(code) + ".", reply_markup=main_keyboard())


async def soccer_on_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        await deny(update)
        return
    bar_widget.set_soccer_enabled(True)
    await update.message.reply_text("Soccer enabled.", reply_markup=main_keyboard())


async def soccer_off_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        await deny(update)
        return
    bar_widget.set_soccer_enabled(False)
    await update.message.reply_text("Soccer disabled.", reply_markup=main_keyboard())


def build_application():
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required")
    if not allowed_chat_ids():
        raise RuntimeError("TELEGRAM_ALLOWED_CHAT_IDS is required and must not be empty")

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("panel", panel_command))
    app.add_handler(CommandHandler("my_id", my_id_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CommandHandler("show", show_command))
    app.add_handler(CommandHandler("hide", hide_command))
    app.add_handler(CommandHandler("color", color_command))
    app.add_handler(CommandHandler("announce", announce_command))
    app.add_handler(CommandHandler("countdown", countdown_command))
    app.add_handler(CommandHandler("soccer", soccer_command))
    app.add_handler(CommandHandler("soccer_on", soccer_on_command))
    app.add_handler(CommandHandler("soccer_off", soccer_off_command))
    app.add_handler(CallbackQueryHandler(callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, flow_message))
    return app


def main():
    application = build_application()
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
