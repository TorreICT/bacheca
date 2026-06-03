import os
import re
from datetime import timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

from app.services import bar_widget, soccer


FLOW_KEY = "bar_widget_flow"
DURATION_RE = re.compile(r"^\s*(\d+)\s*([a-zA-Z]+)?\s*$")
DAY_NAMES = ["lun", "mar", "mer", "gio", "ven", "sab", "dom"]


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
        await update.callback_query.answer("Chat non autorizzata", show_alert=True)
        return
    if update.message:
        await update.message.reply_text("Questa chat non e autorizzata a controllare la bacheca. Usa /my_id per vedere l'ID.")


def chat_id_text(update):
    chat = update.effective_chat
    if not chat:
        return "unknown"
    return str(chat.id)


def main_keyboard():
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("👁️ Mostra", callback_data="show"),
                InlineKeyboardButton("🙈 Nascondi", callback_data="hide"),
            ],
            [
                InlineKeyboardButton("📢 Avvisi", callback_data="announce_menu"),
                InlineKeyboardButton("⏳ Countdown", callback_data="countdown_menu"),
            ],
            [
                InlineKeyboardButton("🎨 Colore", callback_data="color_menu"),
                InlineKeyboardButton("⚽ Calcio", callback_data="soccer_menu"),
            ],
            [
                InlineKeyboardButton("📊 Stato", callback_data="status"),
                InlineKeyboardButton("❓ Aiuto", callback_data="help"),
            ],
        ]
    )


def announcement_keyboard():
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("➕ Avviso temporaneo", callback_data="ann_one")],
            [InlineKeyboardButton("🔁 Avviso giornaliero", callback_data="ann_daily")],
            [InlineKeyboardButton("📅 Avviso settimanale", callback_data="ann_weekly")],
            [
                InlineKeyboardButton("📋 Vedi avvisi", callback_data="ann_list"),
                InlineKeyboardButton("🗑️ Elimina", callback_data="ann_delete_menu"),
            ],
            [InlineKeyboardButton("🧹 Cancella tutti", callback_data="ann_clear_confirm")],
            [InlineKeyboardButton("⬅️ Indietro", callback_data="panel")],
        ]
    )


def countdown_keyboard():
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("⏱️ Imposta countdown", callback_data="countdown_set")],
            [InlineKeyboardButton("🧹 Cancella countdown", callback_data="countdown_clear_confirm")],
            [InlineKeyboardButton("⬅️ Indietro", callback_data="panel")],
        ]
    )


def color_keyboard():
    rows = [
        [
            InlineKeyboardButton("Blu", callback_data="color:blue"),
            InlineKeyboardButton("Verde", callback_data="color:green"),
        ],
        [
            InlineKeyboardButton("Rosso", callback_data="color:red"),
            InlineKeyboardButton("Arancione", callback_data="color:orange"),
        ],
        [
            InlineKeyboardButton("Viola", callback_data="color:purple"),
            InlineKeyboardButton("Petrolio", callback_data="color:teal"),
        ],
        [
            InlineKeyboardButton("Grigio", callback_data="color:gray"),
            InlineKeyboardButton("Scuro", callback_data="color:dark"),
        ],
        [InlineKeyboardButton("🎯 Personalizzato #RRGGBB", callback_data="color_custom")],
        [InlineKeyboardButton("⬅️ Indietro", callback_data="panel")],
    ]
    return InlineKeyboardMarkup(rows)


def soccer_keyboard():
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Attiva", callback_data="soccer_on"),
                InlineKeyboardButton("⛔ Disattiva", callback_data="soccer_off"),
            ],
            [InlineKeyboardButton("🏆 Scegli competizione", callback_data="soccer_comp_menu")],
            [InlineKeyboardButton("⬅️ Indietro", callback_data="panel")],
        ]
    )


async def soccer_competition_keyboard():
    rows = []
    row = []
    choices = await soccer.load_competition_choices()
    for choice in choices:
        row.append(InlineKeyboardButton(competition_button_label(choice), callback_data="soccer_comp:" + choice["code"]))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton("⬅️ Indietro", callback_data="soccer_menu")])
    return InlineKeyboardMarkup(rows)


def competition_button_label(choice):
    code = str(choice.get("code") or "").strip()
    label = str(choice.get("label") or code).strip()
    text = code + " - " + label if code and code not in label else label
    if len(text) > 56:
        text = text[:53] + "..."
    return text


def confirm_keyboard(yes_data, no_data):
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Conferma", callback_data=yes_data),
                InlineKeyboardButton("↩️ Annulla", callback_data=no_data),
            ]
        ]
    )


def announcement_delete_keyboard():
    records = bar_widget.announcement_records()
    rows = []
    for index, record in enumerate(records):
        rows.append(
            [
                InlineKeyboardButton(
                    announcement_button_label(record, index),
                    callback_data="ann_del:" + record["id"],
                )
            ]
        )
    if not rows:
        rows.append([InlineKeyboardButton("Nessun avviso da eliminare", callback_data="announce_menu")])
    rows.append([InlineKeyboardButton("⬅️ Indietro", callback_data="announce_menu")])
    return InlineKeyboardMarkup(rows)


def announcement_management_keyboard():
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("➕ Nuovo", callback_data="ann_one"),
                InlineKeyboardButton("🗑️ Elimina", callback_data="ann_delete_menu"),
            ],
            [InlineKeyboardButton("⬅️ Indietro", callback_data="announce_menu")],
        ]
    )


def announcement_button_label(record, index):
    prefix = "✅" if record.get("active") else "⏳"
    text = truncate(record.get("text") or "", 28)
    return prefix + " " + str(index + 1) + ". " + text


def announcements_text():
    records = bar_widget.announcement_records()
    if not records:
        return "📭 Non ci sono avvisi salvati."
    lines = ["📋 Avvisi salvati", "Gli avvisi attivi ruotano nella barra, dal piu recente al meno recente.", ""]
    for index, record in enumerate(records):
        lines.extend(format_announcement_record(record, index))
        lines.append("")
    return "\n".join(lines).strip()


def format_announcement_record(record, index):
    status = "✅ attivo" if record.get("active") else "⏳ non attivo ora"
    kind = "temporaneo" if record.get("kind") != "periodic" else "periodico"
    lines = [
        str(index + 1) + ". " + status + " - " + kind,
        "📝 " + truncate(record.get("text") or "", 180),
    ]
    if record.get("kind") == "periodic":
        lines.append("🔁 " + periodic_settings_text(record))
    else:
        lines.append("🕒 " + format_datetime(record.get("startsAt")) + " → " + format_datetime(record.get("endsAt")))
        lines.append("⏱️ Durata: " + duration_between(record.get("startsAt"), record.get("endsAt")))
    if record.get("active"):
        lines.append("👁️ In onda fino a: " + format_datetime(record.get("activeEndsAt")))
    return lines


def periodic_settings_text(record):
    frequency = "ogni giorno" if record.get("frequency") == "daily" else "settimanale"
    days = record.get("daysOfWeek") or []
    days_text = "tutti i giorni" if record.get("frequency") == "daily" else ", ".join([DAY_NAMES[item] for item in days if 0 <= item < len(DAY_NAMES)])
    ending = ""
    if record.get("endTime"):
        ending = "fino alle " + record.get("endTime")
    elif record.get("durationMinutes"):
        ending = "per " + format_minutes(record.get("durationMinutes"))
    return frequency + " (" + days_text + "), dalle " + str(record.get("startTime") or "--") + " " + ending + ", fino al " + format_datetime(record.get("recurrenceEndsAt"))


def find_announcement_record(announcement_id):
    for record in bar_widget.announcement_records():
        if record.get("id") == announcement_id:
            return record
    return None


def status_text():
    state = bar_widget.load_state()
    soccer_state = state.get("soccer") or {}
    countdown = state.get("countdown")
    announcements = bar_widget.announcement_records()
    active_count = len([item for item in announcements if item.get("active")])
    parts = [
        "📟 Pannello barra Bacheca",
        "👁️ Visibile: " + ("si" if state.get("visible") else "no"),
        "🎨 Colore: " + str(state.get("color")),
        "📢 Avvisi: " + str(active_count) + " attivi / " + str(len(announcements)) + " salvati",
        "⏳ Countdown: " + (countdown.get("to") if countdown else "nessuno"),
        "⚽ Calcio: " + ("attivo" if soccer_state.get("enabled") else "spento") + " " + str(soccer_state.get("competition") or "SA"),
    ]
    return "\n".join(parts)


def help_text():
    return "\n".join(
        [
            "🧭 Comandi disponibili:",
            "/start - introduzione e pannello",
            "/panel - apre il pannello con i pulsanti",
            "/my_id - mostra l'ID di questa chat",
            "/show e /hide - mostra/nasconde la barra",
            "/announce Testo | 2h - avviso temporaneo da ora",
            "/announce Testo | 2026-06-03T18:00:00+02:00 | 2h - avviso temporaneo con inizio scelto",
            "/countdown Etichetta | 2026-06-03T20:00:00+02:00 - imposta un countdown",
            "/color blue oppure /color #1565C0 - cambia colore",
            "/soccer SA - sceglie la competizione",
            "/soccer_on e /soccer_off - attiva/disattiva il calcio",
            "/cancel - interrompe una procedura guidata",
        ]
    )


def start_text(update):
    return "\n".join(
        [
            "👋 Benvenuto nel controller della barra Bacheca Torrescalla.",
            "Da qui puoi gestire avvisi, countdown, colore, visibilita e calcio.",
            "ID di questa chat: " + chat_id_text(update),
            "",
            status_text(),
            "",
            help_text(),
        ]
    )


def unauthorized_start_text(update):
    return "\n".join(
        [
            "👋 Benvenuto nel controller della barra Bacheca Torrescalla.",
            "Questa chat non e ancora autorizzata a controllare la dashboard.",
            "ID di questa chat: " + chat_id_text(update),
            "Chiedi a un amministratore di aggiungere questo ID a TELEGRAM_ALLOWED_CHAT_IDS.",
            "",
            "Comandi disponibili:",
            "/my_id - mostra l'ID di questa chat",
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
    authorized = "si" if is_authorized(update) else "no"
    await update.message.reply_text("🪪 ID chat: " + chat_id + "\nAutorizzata: " + authorized)


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
    await update.message.reply_text("↩️ Operazione annullata.", reply_markup=main_keyboard())


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
        await query.edit_message_text("✅ Barra mostrata.", reply_markup=main_keyboard())
    elif data == "hide":
        bar_widget.set_visible(False)
        await query.edit_message_text("🙈 Barra nascosta.", reply_markup=main_keyboard())
    elif data == "announce_menu":
        await query.edit_message_text("📢 Gestione avvisi. Gli avvisi attivi ruotano automaticamente nella barra.", reply_markup=announcement_keyboard())
    elif data == "ann_one":
        start_flow(context, "one_shot", "text", {})
        await query.edit_message_text("📝 Scrivi il testo dell'avviso. Le emoji vanno benissimo. Usa /cancel per fermarti.")
    elif data == "ann_daily":
        start_flow(context, "periodic", "text", {"frequency": "daily", "days": [0, 1, 2, 3, 4, 5, 6]})
        await query.edit_message_text("📝 Scrivi il testo dell'avviso giornaliero. Sara valido tutti i giorni. Usa /cancel per fermarti.")
    elif data == "ann_weekly":
        start_flow(context, "periodic", "text", {"frequency": "weekly"})
        await query.edit_message_text("📝 Scrivi il testo dell'avviso settimanale. Le emoji vanno benissimo. Usa /cancel per fermarti.")
    elif data == "ann_list":
        await query.edit_message_text(announcements_text(), reply_markup=announcement_management_keyboard())
    elif data == "ann_delete_menu":
        await query.edit_message_text("🗑️ Scegli l'avviso da eliminare.", reply_markup=announcement_delete_keyboard())
    elif data.startswith("ann_del:"):
        announcement_id = data.split(":", 1)[1]
        record = find_announcement_record(announcement_id)
        if not record:
            await query.edit_message_text("Non trovo piu questo avviso.", reply_markup=announcement_keyboard())
        else:
            await query.edit_message_text(
                "Eliminare questo avviso?\n\n" + "\n".join(format_announcement_record(record, 0)),
                reply_markup=confirm_keyboard("ann_del_yes:" + announcement_id, "ann_delete_menu"),
            )
    elif data.startswith("ann_del_yes:"):
        announcement_id = data.split(":", 1)[1]
        if bar_widget.delete_announcement(announcement_id):
            await query.edit_message_text("🗑️ Avviso eliminato.", reply_markup=announcement_keyboard())
        else:
            await query.edit_message_text("Non trovo piu questo avviso.", reply_markup=announcement_keyboard())
    elif data == "ann_clear_confirm":
        await query.edit_message_text("🧹 Cancellare tutti gli avvisi?", reply_markup=confirm_keyboard("ann_clear_yes", "announce_menu"))
    elif data == "ann_clear_yes":
        bar_widget.clear_announcements()
        await query.edit_message_text("🧹 Avvisi cancellati.", reply_markup=main_keyboard())
    elif data == "countdown_menu":
        await query.edit_message_text("⏳ Gestione countdown.", reply_markup=countdown_keyboard())
    elif data == "countdown_set":
        start_flow(context, "countdown", "label", {})
        await query.edit_message_text("🏷️ Scrivi l'etichetta del countdown, per esempio: Manca. Usa /cancel per fermarti.")
    elif data == "countdown_clear_confirm":
        await query.edit_message_text("🧹 Cancellare il countdown?", reply_markup=confirm_keyboard("countdown_clear_yes", "countdown_menu"))
    elif data == "countdown_clear_yes":
        bar_widget.clear_countdown()
        await query.edit_message_text("🧹 Countdown cancellato.", reply_markup=main_keyboard())
    elif data == "color_menu":
        await query.edit_message_text("🎨 Scegli un colore sicuro per la barra.", reply_markup=color_keyboard())
    elif data.startswith("color:"):
        apply_color(data.split(":", 1)[1])
        await query.edit_message_text("🎨 Colore aggiornato.", reply_markup=main_keyboard())
    elif data == "color_custom":
        start_flow(context, "color", "value", {})
        await query.edit_message_text("🎯 Scrivi un colore come #RRGGBB oppure un preset.")
    elif data == "soccer_menu":
        await query.edit_message_text("⚽ Gestione calcio.", reply_markup=soccer_keyboard())
    elif data == "soccer_on":
        bar_widget.set_soccer_enabled(True)
        await query.edit_message_text("⚽ Calcio attivato.", reply_markup=main_keyboard())
    elif data == "soccer_off":
        bar_widget.set_soccer_enabled(False)
        await query.edit_message_text("⛔ Calcio disattivato.", reply_markup=main_keyboard())
    elif data == "soccer_comp_menu":
        await query.edit_message_text("🏆 Scegli la competizione. La lista arriva da football-data quando disponibile.", reply_markup=await soccer_competition_keyboard())
    elif data.startswith("soccer_comp:"):
        code = data.split(":", 1)[1]
        bar_widget.set_soccer_competition(code)
        await query.edit_message_text("🏆 Competizione impostata: " + soccer.competition_label(code) + ".", reply_markup=main_keyboard())


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
        await update.message.reply_text("Usa /panel per aprire i controlli.", reply_markup=main_keyboard())
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
        await update.message.reply_text("Non ha funzionato: " + str(error) + "\nUsa /cancel per fermarti oppure invia un altro valore.")


async def handle_one_shot_flow(update, context, flow):
    text = clean_message(update)
    data = flow["data"]
    if flow["step"] == "text":
        data["text"] = text
        flow["step"] = "starts"
        await update.message.reply_text("🕒 Quando deve iniziare? Scrivi ora oppure una data ISO, per esempio 2026-06-03T18:00:00+02:00.")
    elif flow["step"] == "starts":
        data["startsAt"] = bar_widget.now() if text.lower() in ("now", "ora", "adesso") else bar_widget.parse_datetime(text)
        flow["step"] = "duration"
        await update.message.reply_text("⏱️ Per quanto tempo deve restare visibile? Esempi: 30m, 2h, 1d.")
    elif flow["step"] == "duration":
        duration = parse_duration(text)
        data["endsAt"] = data["startsAt"] + duration
        bar_widget.add_one_shot_announcement(data["text"], data["startsAt"], data["endsAt"])
        context.user_data.pop(FLOW_KEY, None)
        await update.message.reply_text("✅ Avviso salvato fino a " + format_datetime(data["endsAt"]) + ".", reply_markup=main_keyboard())


async def handle_periodic_flow(update, context, flow):
    text = clean_message(update)
    data = flow["data"]
    if flow["step"] == "text":
        data["text"] = text
        if data.get("frequency") == "weekly":
            flow["step"] = "days"
            await update.message.reply_text("📅 Scrivi i giorni come numeri: 0=lun ... 6=dom, separati da virgole. Esempio: 0,2,4")
        else:
            flow["step"] = "start_time"
            await update.message.reply_text("🕒 Scrivi l'orario di inizio, per esempio 19:30.")
    elif flow["step"] == "days":
        data["days"] = parse_days(text)
        flow["step"] = "start_time"
        await update.message.reply_text("🕒 Scrivi l'orario di inizio, per esempio 19:30.")
    elif flow["step"] == "start_time":
        data["startTime"] = bar_widget.format_time(text)
        flow["step"] = "duration"
        await update.message.reply_text("⏱️ Quanto dura ogni occorrenza? Esempi: 90m, 2h.")
    elif flow["step"] == "duration":
        data["durationMinutes"] = duration_minutes(parse_duration(text))
        if data["durationMinutes"] <= 0:
            raise ValueError("La durata deve essere positiva")
        flow["step"] = "recurrence_ends"
        await update.message.reply_text("📆 Fino a quando si ripete? Scrivi una data ISO.")
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
        await update.message.reply_text("✅ Avviso periodico salvato.", reply_markup=main_keyboard())


async def handle_countdown_flow(update, context, flow):
    text = clean_message(update)
    data = flow["data"]
    if flow["step"] == "label":
        data["label"] = text
        flow["step"] = "target"
        await update.message.reply_text("🎯 Scrivi la data/ora di arrivo in formato ISO.")
    elif flow["step"] == "target":
        target = bar_widget.parse_datetime(text)
        bar_widget.set_countdown(data["label"], target)
        context.user_data.pop(FLOW_KEY, None)
        await update.message.reply_text("✅ Countdown salvato.", reply_markup=main_keyboard())


async def handle_color_flow(update, context, flow):
    text = clean_message(update)
    apply_color(text)
    context.user_data.pop(FLOW_KEY, None)
    await update.message.reply_text("🎨 Colore aggiornato.", reply_markup=main_keyboard())


def clean_message(update):
    return str(update.message.text or "").strip()


def parse_duration(text):
    match = DURATION_RE.match(str(text or "").strip().lower())
    if not match:
        raise ValueError("Durata non valida. Esempi: 30m, 2h, 1d")
    amount = int(match.group(1))
    unit = match.group(2) or "m"
    if amount <= 0:
        raise ValueError("La durata deve essere positiva")
    if unit in ("m", "min", "mins", "minuto", "minuti", "minute", "minutes"):
        return timedelta(minutes=amount)
    if unit in ("h", "ora", "ore", "hour", "hours"):
        return timedelta(hours=amount)
    if unit in ("d", "g", "giorno", "giorni", "day", "days"):
        return timedelta(days=amount)
    raise ValueError("Unita non valida. Usa minuti, ore o giorni: 30m, 2h, 1d")


def duration_minutes(value):
    return int(value.total_seconds() / 60)


def parse_days(text):
    days = []
    for part in text.replace(";", ",").split(","):
        cleaned = part.strip()
        if not cleaned:
            continue
        day = int(cleaned)
        if day < 0 or day > 6:
            raise ValueError("I giorni devono essere numeri da 0 a 6")
        if day not in days:
            days.append(day)
    if not days:
        raise ValueError("Serve almeno un giorno")
    return sorted(days)


def truncate(value, max_length):
    text = str(value or "").replace("\n", " ").strip()
    if len(text) <= max_length:
        return text
    return text[: max_length - 3] + "..."


def format_datetime(value):
    if not value:
        return "--"
    try:
        parsed = bar_widget.parse_datetime(value)
    except Exception:
        return str(value)
    return parsed.strftime("%d/%m %H:%M")


def duration_between(start_value, end_value):
    try:
        delta = bar_widget.parse_datetime(end_value) - bar_widget.parse_datetime(start_value)
    except Exception:
        return "--"
    return format_minutes(duration_minutes(delta))


def format_minutes(value):
    try:
        minutes = int(value)
    except (TypeError, ValueError):
        return "--"
    if minutes % 1440 == 0:
        days = int(minutes / 1440)
        return str(days) + (" giorno" if days == 1 else " giorni")
    if minutes % 60 == 0:
        hours = int(minutes / 60)
        return str(hours) + (" ora" if hours == 1 else " ore")
    return str(minutes) + " minuti"


def apply_color(value):
    bar_widget.set_color(value)


async def show_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        await deny(update)
        return
    bar_widget.set_visible(True)
    await update.message.reply_text("✅ Barra mostrata.", reply_markup=main_keyboard())


async def hide_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        await deny(update)
        return
    bar_widget.set_visible(False)
    await update.message.reply_text("🙈 Barra nascosta.", reply_markup=main_keyboard())


async def color_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        await deny(update)
        return
    value = " ".join(context.args).strip()
    if not value:
        await update.message.reply_text("Uso: /color blue oppure /color #1565C0")
        return
    try:
        apply_color(value)
    except ValueError as error:
        await update.message.reply_text(str(error))
        return
    await update.message.reply_text("🎨 Colore aggiornato.", reply_markup=main_keyboard())


async def announce_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        await deny(update)
        return
    raw = " ".join(context.args).strip()
    if "|" not in raw:
        await update.message.reply_text("Uso: /announce Testo | 2h\nOppure: /announce Testo | 2026-06-03T18:00:00+02:00 | 2h")
        return
    parts = [part.strip() for part in raw.split("|")]
    try:
        if len(parts) == 2:
            text = parts[0]
            starts_at = bar_widget.now()
            duration = parse_duration(parts[1])
        elif len(parts) == 3:
            text = parts[0]
            starts_at = bar_widget.now() if parts[1].lower() in ("now", "ora", "adesso") else bar_widget.parse_datetime(parts[1])
            duration = parse_duration(parts[2])
        else:
            raise ValueError("Formato non valido")
        ends_at = starts_at + duration
        bar_widget.add_one_shot_announcement(text, starts_at, ends_at)
    except Exception as error:
        await update.message.reply_text(str(error))
        return
    await update.message.reply_text("✅ Avviso salvato fino a " + format_datetime(ends_at) + ".", reply_markup=main_keyboard())


async def countdown_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        await deny(update)
        return
    raw = " ".join(context.args).strip()
    if not raw:
        await update.message.reply_text("Uso: /countdown Etichetta | 2026-06-03T20:00:00+02:00")
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
    await update.message.reply_text("✅ Countdown salvato.", reply_markup=main_keyboard())


async def soccer_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        await deny(update)
        return
    code = " ".join(context.args).strip()
    if not code:
        await update.message.reply_text("Uso: /soccer SA", reply_markup=await soccer_competition_keyboard())
        return
    bar_widget.set_soccer_competition(code)
    await update.message.reply_text("🏆 Competizione impostata: " + soccer.competition_label(code) + ".", reply_markup=main_keyboard())


async def soccer_on_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        await deny(update)
        return
    bar_widget.set_soccer_enabled(True)
    await update.message.reply_text("⚽ Calcio attivato.", reply_markup=main_keyboard())


async def soccer_off_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        await deny(update)
        return
    bar_widget.set_soccer_enabled(False)
    await update.message.reply_text("⛔ Calcio disattivato.", reply_markup=main_keyboard())


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
