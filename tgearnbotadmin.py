import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InlineQueryResultArticle, InputTextMessageContent
from telegram.ext import (
    Updater,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    Filters,
    CallbackContext,
    InlineQueryHandler
)
import datetime
import sqlite3
from uuid import uuid4
import json
from flask import Flask, request, render_template_string

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot configuration
TOKEN = "8055336106:AAEQE68sNvaYQass4JlaE-RkxPqSwfK_oGY"
ADMIN_ID = 7886784906  # Your admin ID
BOT_NAME = "EARNINGBY02_BOT"
BOT_USERNAME = "@EARNINGBY02_BOT"

# Required channels
REQUIRED_CHANNELS = [
    {"id": "@BoterGodown", "url": "https://t.me/BoterGodown"},
    {"id": "@Boter_Godown", "url": "https://t.me/Boter_Godown"}
]

# Web app for withdrawal
app = Flask(__name__)

# Database setup
def init_db():
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    
    # Users table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        first_name TEXT,
        last_name TEXT,
        balance REAL DEFAULT 0,
        bonus_claimed_date TEXT,
        referral_code TEXT UNIQUE,
        referred_by INTEGER,
        join_date TEXT
    )
    ''')
    
    # Referrals table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS referrals (
        referral_id INTEGER PRIMARY KEY AUTOINCREMENT,
        referrer_id INTEGER,
        referred_id INTEGER,
        date TEXT,
        FOREIGN KEY (referrer_id) REFERENCES users (user_id),
        FOREIGN KEY (referred_id) REFERENCES users (user_id)
    )
    ''')
    
    # Withdrawals table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS withdrawals (
        withdrawal_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        amount REAL,
        status TEXT DEFAULT 'pending',
        date TEXT,
        FOREIGN KEY (user_id) REFERENCES users (user_id)
    )
    ''')
    
    # Admin settings table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS admin_settings (
        setting_id INTEGER PRIMARY KEY AUTOINCREMENT,
        min_withdraw REAL DEFAULT 15,
        bonus_amount REAL DEFAULT 0.5,
        referral_income REAL DEFAULT 0.5,
        bot_status INTEGER DEFAULT 1,
        currency_name TEXT DEFAULT '★',
        currency_code TEXT DEFAULT 'STAR'
    )
    ''')
    
    # Initialize admin settings if not exists
    cursor.execute('SELECT * FROM admin_settings')
    if not cursor.fetchone():
        cursor.execute('''
        INSERT INTO admin_settings (min_withdraw, bonus_amount, referral_income, bot_status, currency_name, currency_code)
        VALUES (?, ?, ?, ?, ?, ?)
        ''', (15, 0.5, 0.5, 1, '★', 'STAR'))
    
    conn.commit()
    conn.close()

init_db()

# Helper functions
def get_user(user_id):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    columns = [column[0] for column in cursor.description]
    user = dict(zip(columns, cursor.fetchone())) if cursor.fetchone() else None
    conn.close()
    return user

def get_currency_settings():
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT currency_name, currency_code FROM admin_settings')
    result = cursor.fetchone()
    conn.close()
    return {'name': result[0], 'code': result[1]} if result else {'name': '★', 'code': 'STAR'}

def create_user(user_id, username, first_name, last_name, referred_by=None):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    
    # Generate unique referral code
    referral_code = str(uuid4())[:8]
    
    cursor.execute('''
    INSERT INTO users (user_id, username, first_name, last_name, referral_code, referred_by, join_date)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (user_id, username, first_name, last_name, referral_code, referred_by, datetime.datetime.now().isoformat()))
    
    conn.commit()
    conn.close()
    
    # If referred by someone, add referral income
    if referred_by:
        add_referral_income(referred_by, user_id)

def add_referral_income(referrer_id, referred_id):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    settings = get_admin_settings()
    
    # Add referral record
    cursor.execute('''
    INSERT INTO referrals (referrer_id, referred_id, date)
    VALUES (?, ?, ?)
    ''', (referrer_id, referred_id, datetime.datetime.now().isoformat()))
    
    # Update referrer's balance
    cursor.execute('''
    UPDATE users 
    SET balance = balance + ?
    WHERE user_id = ?
    ''', (settings['referral_income'], referrer_id))
    
    conn.commit()
    conn.close()

def update_balance(user_id, amount):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('''
    UPDATE users 
    SET balance = balance + ?
    WHERE user_id = ?
    ''', (amount, user_id))
    conn.commit()
    conn.close()

def can_claim_bonus(user_id):
    user = get_user(user_id)
    if not user or not user['bonus_claimed_date']:
        return True
    
    last_claimed = datetime.datetime.fromisoformat(user['bonus_claimed_date'])
    now = datetime.datetime.now()
    return (now - last_claimed).days >= 1

def claim_bonus(user_id):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    settings = get_admin_settings()
    
    cursor.execute('''
    UPDATE users 
    SET balance = balance + ?, bonus_claimed_date = ?
    WHERE user_id = ?
    ''', (settings['bonus_amount'], datetime.datetime.now().isoformat(), user_id))
    conn.commit()
    conn.close()

def get_admin_settings():
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM admin_settings')
    columns = [column[0] for column in cursor.description]
    settings = dict(zip(columns, cursor.fetchone())) if cursor.fetchone() else None
    conn.close()
    return settings

def update_admin_settings(setting, value):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    
    if setting in ['min_withdraw', 'bonus_amount', 'referral_income']:
        cursor.execute(f'UPDATE admin_settings SET {setting} = ?', (float(value),))
    elif setting == 'bot_status':
        cursor.execute('UPDATE admin_settings SET bot_status = ?', (1 if value else 0,))
    elif setting in ['currency_name', 'currency_code']:
        cursor.execute(f'UPDATE admin_settings SET {setting} = ?', (value,))
    
    conn.commit()
    conn.close()

def create_withdrawal(user_id, amount):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    
    # Deduct from user balance
    cursor.execute('''
    UPDATE users 
    SET balance = balance - ?
    WHERE user_id = ?
    ''', (amount, user_id))
    
    # Create withdrawal record
    cursor.execute('''
    INSERT INTO withdrawals (user_id, amount, date)
    VALUES (?, ?, ?)
    ''', (user_id, amount, datetime.datetime.now().isoformat()))
    
    withdrawal_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return withdrawal_id

def get_pending_withdrawals():
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('''
    SELECT w.withdrawal_id, u.user_id, u.username, w.amount, w.date 
    FROM withdrawals w
    JOIN users u ON w.user_id = u.user_id
    WHERE w.status = 'pending'
    ''')
    columns = [column[0] for column in cursor.description]
    withdrawals = [dict(zip(columns, row)) for row in cursor.fetchall()]
    conn.close()
    return withdrawals

def update_withdrawal_status(withdrawal_id, status):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('''
    UPDATE withdrawals 
    SET status = ?
    WHERE withdrawal_id = ?
    ''', (status, withdrawal_id))
    conn.commit()
    conn.close()

def get_all_users():
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT user_id, username, first_name, balance FROM users')
    columns = [column[0] for column in cursor.description]
    users = [dict(zip(columns, row)) for row in cursor.fetchall()]
    conn.close()
    return users

def get_user_referrals(user_id):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('''
    SELECT u.user_id, u.username, u.first_name, r.date 
    FROM referrals r
    JOIN users u ON r.referred_id = u.user_id
    WHERE r.referrer_id = ?
    ''', (user_id,))
    columns = [column[0] for column in cursor.description]
    referrals = [dict(zip(columns, row)) for row in cursor.fetchall()]
    conn.close()
    return referrals

def get_top_users(limit=10):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('''
    SELECT user_id, username, first_name, balance 
    FROM users 
    ORDER BY balance DESC 
    LIMIT ?
    ''', (limit,))
    columns = [column[0] for column in cursor.description]
    top_users = [dict(zip(columns, row)) for row in cursor.fetchall()]
    conn.close()
    return top_users

def broadcast_message(context: CallbackContext, message):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT user_id FROM users')
    users = cursor.fetchall()
    conn.close()
    
    for user in users:
        try:
            context.bot.send_message(chat_id=user[0], text=message)
        except Exception as e:
            logger.error(f"Failed to send message to {user[0]}: {e}")

# Web App for Withdrawal
@app.route('/withdraw/<int:user_id>', methods=['GET', 'POST'])
def withdraw_web(user_id):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    
    # Get user data
    cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    user = cursor.fetchone()
    
    # Get currency settings
    cursor.execute('SELECT currency_name, currency_code FROM admin_settings')
    currency = cursor.fetchone()
    
    if not user or not currency:
        return "Invalid request", 400
    
    user_balance = user[4]
    currency_name = currency[0]
    currency_code = currency[1]
    
    if request.method == 'POST':
        amount = float(request.form.get('amount', 0))
        
        if amount <= 0 or amount > user_balance:
            return "Invalid amount", 400
        
        # Create withdrawal
        withdrawal_id = create_withdrawal(user_id, amount)
        
        # Notify admin
        try:
            from telegram import Bot
            bot = Bot(token=TOKEN)
            bot.send_message(
                chat_id=ADMIN_ID,
                text=f"⚠️ New Withdrawal Request\n\n"
                     f"User: @{user[1]}\n"
                     f"Amount: {amount} {currency_name}\n"
                     f"Withdrawal ID: {withdrawal_id}\n\n"
                     f"Approve or reject this request from /adminpanel"
            )
            
            # Post to payout channel
            keyboard = [[InlineKeyboardButton("⭐Join Bot", url=f"https://t.me/{BOT_USERNAME}")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            bot.send_message(
                chat_id="@payout_k_Channel",
                text=f"💰 New Withdrawal\n\n"
                     f"User: @{user[1]}\n"
                     f"Amount: {amount} {currency_name}\n"
                     f"Status: Pending\n\n"
                     f"#Withdrawal #{currency_code}",
                reply_markup=reply_markup
            )
        except Exception as e:
            logger.error(f"Failed to send notification: {e}")
        
        return render_template_string('''
            <!DOCTYPE html>
            <html>
            <head>
                <title>Withdrawal Successful</title>
                <style>
                    body { font-family: Arial, sans-serif; text-align: center; padding: 20px; }
                    .success { color: #4CAF50; font-size: 24px; }
                    .info { margin: 20px 0; }
                </style>
            </head>
            <body>
                <div class="success">✅ Withdrawal Request Submitted!</div>
                <div class="info">Amount: {{ amount }} {{ currency }}</div>
                <div class="info">Request ID: {{ withdrawal_id }}</div>
                <p>Your request will be processed soon. You'll be notified when approved.</p>
                <script>
                    setTimeout(function() {
                        Telegram.WebApp.close();
                    }, 3000);
                </script>
            </body>
            </html>
        ''', amount=amount, currency=currency_name, withdrawal_id=withdrawal_id)
    
    # GET request - show withdrawal form
    return render_template_string('''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Withdraw {{ currency_name }}</title>
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <style>
                body {
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    margin: 0;
                    padding: 0;
                    background-color: #f5f5f5;
                    color: #333;
                }
                .container {
                    max-width: 500px;
                    margin: 0 auto;
                    padding: 20px;
                }
                .header {
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    margin-bottom: 20px;
                    padding-bottom: 10px;
                    border-bottom: 1px solid #ddd;
                }
                .bot-name {
                    font-weight: bold;
                    color: #2c3e50;
                }
                .balance {
                    font-weight: bold;
                    color: #27ae60;
                }
                .form-group {
                    margin-bottom: 15px;
                }
                label {
                    display: block;
                    margin-bottom: 5px;
                    font-weight: bold;
                }
                input[type="number"] {
                    width: 100%;
                    padding: 10px;
                    border: 1px solid #ddd;
                    border-radius: 4px;
                    font-size: 16px;
                }
                .btn {
                    background-color: #3498db;
                    color: white;
                    border: none;
                    padding: 12px 20px;
                    border-radius: 4px;
                    cursor: pointer;
                    font-size: 16px;
                    width: 100%;
                    transition: background-color 0.3s;
                }
                .btn:hover {
                    background-color: #2980b9;
                }
                .amount-options {
                    display: grid;
                    grid-template-columns: repeat(3, 1fr);
                    gap: 10px;
                    margin-bottom: 20px;
                }
                .amount-btn {
                    padding: 10px;
                    border: 1px solid #ddd;
                    border-radius: 4px;
                    text-align: center;
                    cursor: pointer;
                    transition: all 0.3s;
                }
                .amount-btn:hover {
                    background-color: #f0f0f0;
                }
                .amount-btn.active {
                    background-color: #3498db;
                    color: white;
                    border-color: #3498db;
                }
            </style>
            <script>
                document.addEventListener('DOMContentLoaded', function() {
                    // Handle amount button clicks
                    const amountBtns = document.querySelectorAll('.amount-btn');
                    const amountInput = document.getElementById('amount');
                    
                    amountBtns.forEach(btn => {
                        btn.addEventListener('click', function() {
                            amountBtns.forEach(b => b.classList.remove('active'));
                            this.classList.add('active');
                            amountInput.value = this.getAttribute('data-amount');
                        });
                    });
                    
                    // Handle form submission
                    const form = document.getElementById('withdraw-form');
                    form.addEventListener('submit', function(e) {
                        e.preventDefault();
                        const amount = parseFloat(amountInput.value);
                        const balance = parseFloat('{{ user_balance }}');
                        
                        if (isNaN(amount) || amount <= 0) {
                            alert('Please enter a valid amount');
                            return;
                        }
                        
                        if (amount > balance) {
                            alert('You don\'t have enough balance');
                            return;
                        }
                        
                        this.submit();
                    });
                });
            </script>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <div class="bot-name">{{ bot_name }}</div>
                    <div class="balance">Balance: {{ user_balance }} {{ currency_name }}</div>
                </div>
                
                <h2>Withdraw {{ currency_name }}</h2>
                <p>Enter the amount you want to withdraw:</p>
                
                <form id="withdraw-form" method="POST">
                    <div class="amount-options">
                        <div class="amount-btn" data-amount="15">15 {{ currency_name }}</div>
                        <div class="amount-btn" data-amount="25">25 {{ currency_name }}</div>
                        <div class="amount-btn" data-amount="50">50 {{ currency_name }}</div>
                    </div>
                    
                    <div class="form-group">
                        <label for="amount">Amount ({{ currency_name }})</label>
                        <input type="number" id="amount" name="amount" step="0.01" min="0" max="{{ user_balance }}" required>
                    </div>
                    
                    <button type="submit" class="btn">Withdraw Now</button>
                </form>
            </div>
        </body>
        </html>
    ''', bot_name=BOT_NAME, user_balance=user_balance, currency_name=currency_name)

# Telegram bot handlers
def start(update: Update, context: CallbackContext):
    user = update.effective_user
    user_id = user.id
    username = user.username
    first_name = user.first_name
    last_name = user.last_name
    
    # Check if bot is ON
    settings = get_admin_settings()
    if not settings['bot_status']:
        update.message.reply_text("⚠️ Bot is currently OFF. Please try again later.")
        return
    
    # Check if user exists, if not create
    if not get_user(user_id):
        # Check for referral
        referred_by = None
        if context.args and context.args[0]:
            referred_by = int(context.args[0]) if context.args[0].isdigit() else None
        
        create_user(user_id, username, first_name, last_name, referred_by)
        
        # Notify admin
        context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"📢 New user joined:\n\n"
                 f"👤 Username: @{username}\n"
                 f"📛 Name: {first_name} {last_name}\n"
                 f"🆔 ID: {user_id}\n\n"
                 f"#NewUser #Join",
            parse_mode='HTML'
        )
    
    # Check channel subscription
    keyboard = []
    for channel in REQUIRED_CHANNELS:
        keyboard.append([InlineKeyboardButton(f"Join {channel['id']}", url=channel['url'])])
    
    keyboard.append([InlineKeyboardButton("✅ I've Joined All Channels", callback_data='check_subscription')])
    
    update.message.reply_text(
        "📢 <b>Please join our channels to use this bot:</b>",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )

def check_subscription(update: Update, context: CallbackContext):
    query = update.callback_query
    user_id = query.from_user.id
    
    # Check if user is subscribed to all channels
    # Note: In reality, you need to use Telegram's API to check subscription status
    # This is a placeholder implementation
    all_joined = True  # Assume they joined for demo purposes
    
    if all_joined:
        # Show main menu
        keyboard = [
            [InlineKeyboardButton("💰 Balance", callback_data='balance'),
             InlineKeyboardButton("🎁 Bonus", callback_data='bonus')],
            [InlineKeyboardButton("👥 Referrals", callback_data='referrals'),
             InlineKeyboardButton("💸 Withdraw", callback_data='withdraw')],
            [InlineKeyboardButton("🏆 Leaderboard", callback_data='leaderboard'),
             InlineKeyboardButton("ℹ️ Help", callback_data='help')]
        ]
        
        query.edit_message_text(
            "🎉 <b>Welcome to EARNINGBY02_BOT!</b>\n\n"
            "💰 Earn stars by completing tasks and referring friends\n"
            "💸 Withdraw your stars when you reach the minimum amount\n\n"
            "👇 <b>Choose an option below:</b>",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )
    else:
        query.answer("Please join all required channels first!", show_alert=True)

def balance(update: Update, context: CallbackContext):
    query = update.callback_query
    user_id = query.from_user.id
    user = get_user(user_id)
    currency = get_currency_settings()
    
    keyboard = [
        [InlineKeyboardButton("🔙 Back", callback_data='main_menu')]
    ]
    
    query.edit_message_text(
        f"💰 <b>Your Balance:</b> {user['balance']} {currency['name']}\n\n"
        f"🔗 <b>Your Referral Link:</b>\n"
        f"https://t.me/{BOT_USERNAME}?start={user_id}\n\n"
        f"Invite friends and earn {get_admin_settings()['referral_income']} {currency['name']} per referral!",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )

def bonus(update: Update, context: CallbackContext):
    query = update.callback_query
    user_id = query.from_user.id
    settings = get_admin_settings()
    currency = get_currency_settings()
    
    if can_claim_bonus(user_id):
        claim_bonus(user_id)
        user = get_user(user_id)
        
        keyboard = [
            [InlineKeyboardButton("🔙 Back", callback_data='main_menu')]
        ]
        
        query.edit_message_text(
            f"🎉 <b>You claimed your daily bonus of {settings['bonus_amount']} {currency['name']}!</b>\n\n"
            f"💰 <b>Your new balance:</b> {user['balance']} {currency['name']}\n\n"
            f"Come back in 24 hours to claim again!",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )
    else:
        user = get_user(user_id)
        last_claimed = datetime.datetime.fromisoformat(user['bonus_claimed_date'])
        next_claim = last_claimed + datetime.timedelta(days=1)
        time_left = next_claim - datetime.datetime.now()
        
        hours, remainder = divmod(time_left.seconds, 3600)
        minutes, _ = divmod(remainder, 60)
        
        keyboard = [
            [InlineKeyboardButton("🔙 Back", callback_data='main_menu')]
        ]
        
        query.edit_message_text(
            f"⏳ <b>You already claimed your bonus today!</b>\n\n"
            f"⏰ <b>Next bonus available in:</b> {hours}h {minutes}m\n\n"
            f"💰 <b>Your current balance:</b> {user['balance']} {currency['name']}",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )

def referrals(update: Update, context: CallbackContext):
    query = update.callback_query
    user_id = query.from_user.id
    user = get_user(user_id)
    referrals = get_user_referrals(user_id)
    currency = get_currency_settings()
    
    ref_text = "\n".join(
        [f"{i+1}. @{ref['username']} ({ref['first_name']}) - {datetime.datetime.fromisoformat(ref['date']).strftime('%Y-%m-%d')}"
         for i, ref in enumerate(referrals)]
    ) if referrals else "No referrals yet."
    
    keyboard = [
        [InlineKeyboardButton("🔙 Back", callback_data='main_menu')]
    ]
    
    query.edit_message_text(
        f"👥 <b>Your Referrals:</b> {len(referrals)}\n\n"
        f"{ref_text}\n\n"
        f"🔗 <b>Your Referral Link:</b>\n"
        f"https://t.me/{BOT_USERNAME}?start={user_id}\n\n"
        f"Earn {get_admin_settings()['referral_income']} {currency['name']} for each friend who joins!",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )

def withdraw(update: Update, context: CallbackContext):
    query = update.callback_query
    user_id = query.from_user.id
    user = get_user(user_id)
    settings = get_admin_settings()
    currency = get_currency_settings()
    
    if user['balance'] < settings['min_withdraw']:
        keyboard = [
            [InlineKeyboardButton("🔙 Back", callback_data='main_menu')]
        ]
        
        query.edit_message_text(
            f"⚠️ <b>Minimum withdrawal amount is {settings['min_withdraw']} {currency['name']}</b>\n\n"
            f"💰 <b>Your current balance:</b> {user['balance']} {currency['name']}\n\n"
            f"Keep earning to reach the minimum!",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )
        return
    
    # Open web app for withdrawal
    web_app_url = f"https://your-web-app-url.com/withdraw/{user_id}"  # Replace with your actual web app URL
    keyboard = [
        [InlineKeyboardButton("💸 Open Withdrawal", web_app=WebAppInfo(url=web_app_url))],
        [InlineKeyboardButton("🔙 Back", callback_data='main_menu')]
    ]
    
    query.edit_message_text(
        f"💸 <b>Withdrawal Request</b>\n\n"
        f"💰 <b>Your balance:</b> {user['balance']} {currency['name']}\n"
        f"📌 <b>Minimum withdrawal:</b> {settings['min_withdraw']} {currency['name']}\n\n"
        f"Click the button below to open withdrawal form:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )

def leaderboard(update: Update, context: CallbackContext):
    query = update.callback_query
    top_users = get_top_users()
    currency = get_currency_settings()
    
    leaderboard_text = "\n".join(
        [f"{i+1}. @{user['username']} ({user['first_name']}) - {user['balance']} {currency['name']}"
         for i, user in enumerate(top_users)]
    )
    
    keyboard = [
        [InlineKeyboardButton("🔙 Back", callback_data='main_menu')]
    ]
    
    query.edit_message_text(
        f"🏆 <b>Top Users Leaderboard</b>\n\n"
        f"{leaderboard_text}\n\n"
        f"Keep earning to climb the ranks!",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )

def help(update: Update, context: CallbackContext):
    query = update.callback_query
    currency = get_currency_settings()
    
    keyboard = [
        [InlineKeyboardButton("🔙 Back", callback_data='main_menu')]
    ]
    
    query.edit_message_text(
        "ℹ️ <b>Help Center</b>\n\n"
        "💰 <b>Earn {currency['name']} by:</b>\n"
        "- Claiming daily bonus (/bonus)\n"
        "- Referring friends (/referrals)\n\n"
        "💸 <b>Withdraw {currency['name']} when you reach the minimum amount (/withdraw)</b>\n\n"
        "📢 <b>Stay updated by joining our channels:</b>\n"
        "- https://t.me/KHF_Exclusive_Promoter\n"
        "- https://t.me/payout_k_Channel\n\n"
        "For any issues, contact @AdminUsername",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )

def main_menu(update: Update, context: CallbackContext):
    query = update.callback_query
    
    keyboard = [
        [InlineKeyboardButton("💰 Balance", callback_data='balance'),
         InlineKeyboardButton("🎁 Bonus", callback_data='bonus')],
        [InlineKeyboardButton("👥 Referrals", callback_data='referrals'),
         InlineKeyboardButton("💸 Withdraw", callback_data='withdraw')],
        [InlineKeyboardButton("🏆 Leaderboard", callback_data='leaderboard'),
         InlineKeyboardButton("ℹ️ Help", callback_data='help')]
    ]
    
    query.edit_message_text(
        "🎉 <b>Welcome to EARNINGBY02_BOT!</b>\n\n"
        "💰 Earn stars by completing tasks and referring friends\n"
        "💸 Withdraw your stars when you reach the minimum amount\n\n"
        "👇 <b>Choose an option below:</b>",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )

def admin_panel(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        update.message.reply_text("⚠️ You are not authorized to access this!")
        return
    
    settings = get_admin_settings()
    currency = get_currency_settings()
    
    keyboard = [
        [InlineKeyboardButton("➕ Add Balance", callback_data='admin_add_balance'),
         InlineKeyboardButton("➖ Remove Balance", callback_data='admin_remove_balance')],
        [InlineKeyboardButton("📢 Add Channel", callback_data='admin_add_channel'),
         InlineKeyboardButton("🗑 Remove Channel", callback_data='admin_remove_channel')],
        [InlineKeyboardButton("💵 Set Min Withdraw", callback_data='admin_set_min_withdraw'),
         InlineKeyboardButton("🎁 Set Bonus Amount", callback_data='admin_set_bonus')],
        [InlineKeyboardButton("👥 Set Referral Income", callback_data='admin_set_referral'),
         InlineKeyboardButton("🔄 Set Currency", callback_data='admin_set_currency')],
        [InlineKeyboardButton("👤 Manage Users", callback_data='admin_manage_users'),
         InlineKeyboardButton("📊 View Payouts", callback_data='admin_view_payouts')],
        [InlineKeyboardButton("📢 Broadcast", callback_data='admin_broadcast'),
         InlineKeyboardButton("✅ Approve Withdrawals", callback_data='admin_withdrawals')],
        [InlineKeyboardButton(f"🔴 Bot Status: {'ON' if settings['bot_status'] else 'OFF'}", 
         callback_data='admin_toggle_bot')],
        [InlineKeyboardButton("📊 Stats", callback_data='admin_stats')]
    ]
    
    update.message.reply_text(
        f"👑 <b>Admin Panel</b> 👑\n\n"
        f"📊 <b>Current Settings:</b>\n"
        f"- Min Withdraw: {settings['min_withdraw']} {currency['name']}\n"
        f"- Bonus Amount: {settings['bonus_amount']} {currency['name']}\n"
        f"- Referral Income: {settings['referral_income']} {currency['name']}\n"
        f"- Currency: {currency['name']} ({currency['code']})\n"
        f"- Bot Status: {'🟢 ON' if settings['bot_status'] else '🔴 OFF'}\n\n"
        "🔧 <b>Select an option:</b>",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )

def admin_set_currency(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    
    keyboard = [
        [InlineKeyboardButton("★ Star", callback_data='set_currency_star'),
         InlineKeyboardButton("💰 Coin", callback_data='set_currency_coin')],
        [InlineKeyboardButton("💎 Diamond", callback_data='set_currency_diamond'),
         InlineKeyboardButton("✨ Sparkle", callback_data='set_currency_sparkle')],
        [InlineKeyboardButton("🔙 Back", callback_data='admin_panel')]
    ]
    
    query.edit_message_text(
        "💱 <b>Set Currency Symbol</b>\n\n"
        "Select a currency symbol or enter a custom one:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )

def admin_toggle_bot(update: Update, context: CallbackContext):
    query = update.callback_query
    settings = get_admin_settings()
    new_status = not settings['bot_status']
    update_admin_settings('bot_status', new_status)
    
    query.edit_message_text(
        f"✅ <b>Bot status changed to {'ON' if new_status else 'OFF'}</b>\n\n"
        f"Users will {'now' if new_status else 'not'} be able to use the bot.",
        parse_mode='HTML'
    )
    context.bot.send_message(
        chat_id=ADMIN_ID,
        text=f"🔔 Bot status changed to {'ON' if new_status else 'OFF'}"
    )

def error_handler(update: Update, context: CallbackContext):
    logger.error(msg="Exception while handling an update:", exc_info=context.error)
    
    if update.callback_query:
        update.callback_query.answer("An error occurred. Please try again.", show_alert=True)
    elif update.message:
        update.message.reply_text("An error occurred. Please try again.")

def run_web_app():
    app.run(port=5000)

def main():
    # Start web app in a separate thread
    from threading import Thread
    web_thread = Thread(target=run_web_app)
    web_thread.daemon = True
    web_thread.start()
    
    # Start the bot
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher
    
    # Command handlers
    dp.add_handler(CommandHandler('start', start))
    dp.add_handler(CommandHandler('balance', balance))
    dp.add_handler(CommandHandler('bonus', bonus))
    dp.add_handler(CommandHandler('withdraw', withdraw))
    dp.add_handler(CommandHandler('referrals', referrals))
    dp.add_handler(CommandHandler('leaderboard', leaderboard))
    dp.add_handler(CommandHandler('help', help))
    dp.add_handler(CommandHandler('adminpanel', admin_panel))
    
    # Callback query handlers
    dp.add_handler(CallbackQueryHandler(check_subscription, pattern='^check_subscription$'))
    dp.add_handler(CallbackQueryHandler(balance, pattern='^balance$'))
    dp.add_handler(CallbackQueryHandler(bonus, pattern='^bonus$'))
    dp.add_handler(CallbackQueryHandler(withdraw, pattern='^withdraw$'))
    dp.add_handler(CallbackQueryHandler(referrals, pattern='^referrals$'))
    dp.add_handler(CallbackQueryHandler(leaderboard, pattern='^leaderboard$'))
    dp.add_handler(CallbackQueryHandler(help, pattern='^help$'))
    dp.add_handler(CallbackQueryHandler(main_menu, pattern='^main_menu$'))
    dp.add_handler(CallbackQueryHandler(admin_toggle_bot, pattern='^admin_toggle_bot$'))
    dp.add_handler(CallbackQueryHandler(admin_set_currency, pattern='^admin_set_currency$'))
    dp.add_handler(CallbackQueryHandler(admin_panel, pattern='^admin_panel$'))
    
    # Error handler
    dp.add_error_handler(error_handler)
    
    # Start the Bot
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
