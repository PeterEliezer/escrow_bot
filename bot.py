import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters
)

# ================= CONFIG =================

TOKEN = "8427219716:AAF00XbhQvmXOo4-Oodg-myspPH6N8pb13w"
ESCROW_ADMIN_ID = 8597839295  # CHANGE THIS

WALLETS = {
    "BTC": "bc1qzctfgc6z8a943nlg9u8lmpeymsrmpuysmxq5ml",
    "USDT": "THj9aRdBvi8hX1ru3po7dqBdbtqaPk5Nxm",
    "ETH": "0xae8b8c621daa7bedcafc2a2e2f4a11b05efdb7ef"
}

# ================= DATABASE =================

conn = sqlite3.connect("escrow.db", check_same_thread=False)
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS escrow_groups (
    group_id INTEGER PRIMARY KEY,
    creator_id INTEGER,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS escrows (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id INTEGER,
    buyer_id INTEGER,
    seller_id INTEGER,
    amount REAL,
    currency TEXT,
    status TEXT
)
""")
conn.commit()

# ================= START =================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type != "private":
        return

    keyboard = [
        [InlineKeyboardButton("➕ Create Escrow Group", callback_data="create_group")],
        [InlineKeyboardButton("📂 Use Existing Group", callback_data="use_group")],
        [InlineKeyboardButton("❓ How it Works", callback_data="how")]
    ]

    await update.message.reply_text(
        "🤝 *Welcome to Secure Escrow*\n\n"
        "To begin, you must first create or select an escrow group.",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

# ================= BUTTONS =================

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "create_group":
        await query.message.reply_text(
            "📌 Create a Telegram group and add:\n\n"
            "✅ This bot\n"
            "✅ The other party\n\n"
            "Then type in the group:\n"
            "`/register_group`",
            parse_mode="Markdown"
        )

    elif query.data == "use_group":
        await query.message.reply_text(
            "👉 Go to your group and type:\n"
            "`/register_group`",
            parse_mode="Markdown"
        )

    elif query.data == "how":
        await query.message.reply_text(
            "ℹ️ *How It Works*\n\n"
            "1️⃣ Create & register group\n"
            "2️⃣ Create escrow in group\n"
            "3️⃣ Buyer deposits\n"
            "4️⃣ Admin releases funds",
            parse_mode="Markdown"
        )

# ================= REGISTER GROUP =================

async def register_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat

    if chat.type not in ["group", "supergroup"]:
        await update.message.reply_text("❌ This command must be used in a group.")
        return

    member = await context.bot.get_chat_member(chat.id, update.effective_user.id)
    if member.status not in ["administrator", "creator"]:
        await update.message.reply_text("❌ Only admins can register the group.")
        return

    bot_member = await context.bot.get_chat_member(chat.id, context.bot.id)
    if bot_member.status != "administrator":
        await update.message.reply_text("❌ Please make the bot an admin.")
        return

    cur.execute(
        "INSERT OR IGNORE INTO escrow_groups (group_id, creator_id) VALUES (?, ?)",
        (chat.id, update.effective_user.id)
    )
    conn.commit()

    await update.message.reply_text("✅ Group registered successfully!")

# ================= CREATE ESCROW =================

async def create_escrow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat

    if chat.type not in ["group", "supergroup"]:
        await update.message.reply_text("❌ Use this command in a group.")
        return

    cur.execute("SELECT * FROM escrow_groups WHERE group_id = ?", (chat.id,))
    if not cur.fetchone():
        await update.message.reply_text("❌ This group is not registered.")
        return

    context.user_data.clear()
    context.user_data["step"] = "buyer"

    await update.message.reply_text("👤 Enter BUYER user ID:")

# ================= ESCROW FLOW =================

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "step" not in context.user_data:
        return

    try:
        step = context.user_data["step"]

        if step == "buyer":
            context.user_data["buyer"] = int(update.message.text)
            context.user_data["step"] = "seller"
            await update.message.reply_text("👤 Enter SELLER user ID:")

        elif step == "seller":
            context.user_data["seller"] = int(update.message.text)
            context.user_data["step"] = "amount"
            await update.message.reply_text("💰 Enter AMOUNT:")

        elif step == "amount":
            context.user_data["amount"] = float(update.message.text)
            context.user_data["step"] = "currency"
            await update.message.reply_text("💱 Enter CURRENCY (BTC / USDT / ETH):")

        elif step == "currency":
            currency = update.message.text.upper()

            if currency not in WALLETS:
                await update.message.reply_text("❌ Choose BTC, USDT, or ETH only.")
                return

            wallet = WALLETS[currency]

            cur.execute("""
                INSERT INTO escrows (group_id, buyer_id, seller_id, amount, currency, status)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                update.effective_chat.id,
                context.user_data["buyer"],
                context.user_data["seller"],
                context.user_data["amount"],
                currency,
                "awaiting_deposit"
            ))
            conn.commit()

            amount = context.user_data["amount"]
            context.user_data.clear()

            await update.message.reply_text(
                f"🔐 *Escrow Deposit Instructions*\n\n"
                f"💱 Currency: *{currency}*\n"
                f"💰 Amount: *{amount}*\n\n"
                f"📥 Send funds to:\n"
                f"`{wallet}`\n\n"
                f"⚠️ Send exactly *{amount} {currency}*\n"
                f"⏳ Waiting for deposit confirmation.",
                parse_mode="Markdown"
            )

    except ValueError:
        await update.message.reply_text("❌ Invalid input. Please try again.")

# ================= ADMIN CONFIRM =================

async def confirm_deposit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ESCROW_ADMIN_ID:
        return

    cur.execute("""
        UPDATE escrows
        SET status = 'active'
        WHERE status = 'awaiting_deposit'
    """)
    conn.commit()

    await update.message.reply_text("✅ Deposit confirmed. Escrow is now ACTIVE.")

# ================= ADMIN RELEASE =================

async def release(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ESCROW_ADMIN_ID:
        return

    await update.message.reply_text("🔓 Funds released (demo).")

# ================= MAIN =================

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(CommandHandler("register_group", register_group))
    app.add_handler(CommandHandler("create_escrow", create_escrow))
    app.add_handler(CommandHandler("confirm_deposit", confirm_deposit))
    app.add_handler(CommandHandler("release", release))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    print("🤖 Escrow Bot Running...")
    app.run_polling()

if __name__ == "__main__":
    main()

