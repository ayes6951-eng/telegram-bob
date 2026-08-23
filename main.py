import asyncio
import sqlite3
from pyrogram import Client, filters
from pyrogram.enums import ChatAction
from pyrogram.errors import FloodWait, RPCError

# --- Configuration ---
API_ID = 32593259
API_HASH = "248f3abd799b6e88bbfe44332e3f09b2"
SESSION_NAME = "okgy"
MAX_TARGETS = 10    # လူအများဆုံး ၁၀ ယောက်အထိ
DEFAULT_DELAY = 1.0 # Spam Loop လုပ်မည့် အမြန်နှုန်း (စက္ကန့်)

class Database:
    def __init__(self):
        self.conn = sqlite3.connect('userbot_data.db', check_same_thread=False)
        self.cursor = self.conn.cursor()
        self.init_tables()
    
    def init_tables(self):
        self.cursor.execute('CREATE TABLE IF NOT EXISTS replies_list (id INTEGER PRIMARY KEY AUTOINCREMENT, reply_text TEXT)')
        self.conn.commit()

    def add_reply(self, text):
        self.cursor.execute("INSERT INTO replies_list (reply_text) VALUES (?)", (text,))
        self.conn.commit()
        return self.cursor.lastrowid

    def del_reply(self, reply_id):
        self.cursor.execute("DELETE FROM replies_list WHERE id = ?", (reply_id,))
        self.conn.commit()
        return self.cursor.rowcount > 0

    def get_all_replies(self):
        self.cursor.execute("SELECT id, reply_text FROM replies_list ORDER BY id ASC")
        return self.cursor.fetchall()

db = Database()
app = Client(SESSION_NAME, api_id=API_ID, api_hash=API_HASH)

target_users = {}         # Target တွေ သိမ်းရန်
active_spam_tasks = {}    # "ဟာဘရို" Spam Loop အတွက် Task များ
auto_reply_chats = set()  # "လီးလား" Auto Reply အတွက် Chat များ
chat_delays = {}          # Spam Delay သိမ်းရန်
current_index = {}        # စာစဉ်လိုက် ပို့ရန် Index

# 🚀 1. "ဟာဘရို" အတွက် Target ဘက်က စာမပို့လည်း MT ခေါ်ပြီး ဆက်တိုက် Spam မည့် Loop Function
async def spam_loop(chat_id):
    current_delay = chat_delays.get(chat_id, DEFAULT_DELAY)
    print(f"[{chat_id}] Spam Loop စတင်နေပါပြီ (Delay: {current_delay}s)...")
    
    while chat_id in active_spam_tasks:
        try:
            all_data = db.get_all_replies()
            replies = [r[1] for r in all_data]
            
            if not replies:
                try:
                    await app.send_message("me", "❌ **Spam ရပ်သွားပါပြီ။ Database ထဲတွင် စာမရှိတော့ပါ။**")
                except Exception:
                    pass
                break
            
            if chat_id not in current_index:
                current_index[chat_id] = 0
            
            targets = target_users.get(chat_id, [])
            if not targets:
                break
            
            # Username ရှိ/မရှိ စစ်ဆေးပြီး Mention (MT) တည်ဆောက်ခြင်း
            mentions_list = []
            for user in list(targets):
                if user.username:
                    mentions_list.append(f"@{user.username}")
                else:
                    mentions_list.append(f"[{user.first_name}](tg://user?id={user.id})")
            
            all_mentions_text = " ".join(mentions_list)
            
            idx = current_index[chat_id] % len(replies)
            reply = replies[idx]
            final_text = f"{all_mentions_text} {reply}"
            
            # Target ဘက်က စာပို့စရာမလိုဘဲ MT နဲ့ စာကို ပုံမှန် ပို့မည် (Spamming)
            await app.send_message(chat_id, final_text)
            
            current_index[chat_id] = idx + 1
            await asyncio.sleep(current_delay)
                
        except FloodWait as e:
            await asyncio.sleep(e.value)
        except (RPCError, Exception):
            await asyncio.sleep(1)

# 🔄 2. "လီးလား" အတွက် Target စာပို့မှ MT မပါဘဲ Reply ပြန်မည့် Handler
@app.on_message(filters.group & ~filters.me)
async def auto_reply_handler(client, message):
    chat_id = message.chat.id
    
    if chat_id in auto_reply_chats and chat_id in target_users:
        target_ids = [u.id for u in target_users[chat_id]]
        
        if message.from_user and message.from_user.id in target_ids:
            try:
                all_data = db.get_all_replies()
                replies = [r[1] for r in all_data]
                
                if not replies:
                    return

                if chat_id not in current_index:
                    current_index[chat_id] = 0

                idx = current_index[chat_id] % len(replies)
                reply = replies[idx]
                current_index[chat_id] = idx + 1

                # MT လုံးဝမပါဘဲ Target စာကို တိုက်ရိုက် Reply ပြန်ခြင်း
                await message.reply_text(reply)

            except FloodWait as e:
                await asyncio.sleep(e.value)
            except (RPCError, Exception) as e:
                print(f"Auto Reply Error: {e}")

# 🎮 Command များ ထိန်းချုပ်သည့် စနစ်
@app.on_message(filters.me & filters.text)
async def handle_commands(client, message):
    chat_id = message.chat.id
    text = message.text.strip()

    try:
        # 1. Help Menu 📖
        if text == "/help":
            delay_val = chat_delays.get(chat_id, DEFAULT_DELAY)
            help_msg = (
                f"📌 **Ultimate Bot Menu**\n\n"
                f"🔹 `ဟာဘရို` - Target ကို Reply ပြန်ပြီး **MT ခေါ်ကာ သူ့ဟာသူ Auto Spam Loop** စတင်ရန် 🚀\n"
                f"🔹 `လီးလား` - Target ကို Reply ပြန်ပြီး **MT မပါဘဲ Target စာပို့မှ Reply** ပြန်ရန် 🔄\n"
                f"🔹 `အိုကေဘရို` - အလုပ်လုပ်နေတာတွေ အကုန်ရပ်ရန် 🛑\n"
                f"🔹 `/delay [0.1-10]` - Spam ရဲ့ အမြန်နှုန်းချိန်ရန်\n"
                f"🔹 `/add_reply [စာ]` - စာတစ်ကြောင်းချင်းထည့်\n"
                f"🔹 `/add_multi [စာသားများ]` - စာအများကြီးတစ်ခါတည်းထည့်\n"
                f"🔹 `/del_reply [ID]` - စာဖျက်\n"
                f"🔹 `/list_reply` - စာရင်းကြည့်\n\n"
                f"⏱ **Spam Delay:** {delay_val}s"
            )
            await client.send_message("me", help_msg)
            try: await message.delete() 
            except Exception: pass
            return

        # 2. Delay ချိန်ညှိခြင်း ⏱
        elif text.startswith("/delay"):
            parts = text.split(None, 1)
            if len(parts) >= 2:
                try:
                    val = float(parts[1])
                    if 0.1 <= val <= 10.0:
                        chat_delays[chat_id] = val
                        await client.send_message("me", f"⏱ **Spam Delay ကို `{val}` စက္ကန့်သို့ ပြောင်းလိုက်ပါပြီ။**")
                        if chat_id in active_spam_tasks:
                            active_spam_tasks[chat_id].cancel()
                            active_spam_tasks[chat_id] = asyncio.create_task(spam_loop(chat_id))
                    else:
                        await client.send_message("me", "⚠️ **0.1 မှ 10 စက္ကန့်အတွင်းသာ ချိန်ပါ။**")
                except ValueError:
                    pass
            try: await message.delete()
            except Exception: pass
            return

        # 3. Add Reply 🛠️
        elif text.startswith("/add_reply"):
            parts = text.split(None, 1)
            if len(parts) >= 2:
                new_id = db.add_reply(parts[1])
                await client.send_message("me", f"✅ **ID {new_id} အဖြစ် သိမ်းဆည်းပြီးပါပြီ**")
            try: await message.delete()
            except Exception: pass
            return

        # 4. Add Multi Reply 🚀
        elif text.startswith("/add_multi"):
            parts = text.split(None, 1)
            if len(parts) >= 2:
                lines = [line.strip() for line in parts[1].split('\n') if line.strip()]
                if lines:
                    start_id, end_id = None, None
                    for line in lines:
                        last_id = db.add_reply(line)
                        if start_id is None: start_id = last_id
                        end_id = last_id
                    await client.send_message("me", f"🚀 **စာသား {len(lines)} ခု (ID {start_id} မှ {end_id}) သိမ်းပြီးပါပြီ။**")
            try: await message.delete()
            except Exception: pass
            return

        # 5. Delete Reply 🗑️
        elif text.startswith("/del_reply"):
            parts = text.split(None, 1)
            if len(parts) >= 2:
                try:
                    r_id = int(parts[1])
                    success = db.del_reply(r_id)
                    if success:
                        await client.send_message("me", f"🗑️ **ID {r_id} ကို ဖျက်လိုက်ပါပြီ။**")
                    else:
                        await client.send_message("me", f"❌ **ID {r_id} ကို မတွေ့ရှိပါ။**")
                except ValueError:
                    await client.send_message("me", "⚠️ **မှန်ကန်သော ID ထည့်ပါ။**")
            try: await message.delete()
            except Exception: pass
            return

        # 6. List Reply 📑
        elif text == "list_reply" or text == "/list_reply":
            replies = db.get_all_replies()
            if not replies:
                await client.send_message("me", "❌ Database ထဲတွင် စာမရှိသေးပါ")
            else:
                total = len(replies)
                await client.send_message("me", f"📑 **စုစုပေါင်း စာသား {total} ခု ရှိသည်:**")
                for i in range(0, total, 8):
                    chunk = replies[i:i+8]
                    msg = "".join([f"🆔 `{r_id}`: {r_text}\n\n" for r_id, r_text in chunk])
                    await client.send_message("me", msg)
                    await asyncio.sleep(0.3)
            try: await message.delete()
            except Exception: pass
            return

        # 7. Start Spam Loop (`ဟာဘရို`) 🚀
        elif text == "ဟာဘရို" and message.reply_to_message:
            target = message.reply_to_message.from_user
            if chat_id not in target_users: 
                target_users[chat_id] = []
                
            if len(target_users[chat_id]) >= MAX_TARGETS:
                if target.id not in [u.id for u in target_users[chat_id]]:
                    await client.send_message("me", f"⚠️ **Target ပြည့်သွားပါပြီ။**")
                    try: await message.delete()
                    except Exception: pass
                    return

            if target.id not in [u.id for u in target_users[chat_id]]:
                target_users[chat_id].append(target)
                current_count = len(target_users[chat_id])
                await client.send_message("me", f"🚀 **Target added (Auto MT Spam Loop): {target.first_name} ({current_count}/{MAX_TARGETS})**")
                
            try: await message.delete() 
            except Exception: pass
            
            # "လီးလား" mode ကို ပိတ်ပြီး Spam loop ကို စတင်မည်
            if chat_id in auto_reply_chats:
                auto_reply_chats.remove(chat_id)

            if chat_id in active_spam_tasks:
                active_spam_tasks[chat_id].cancel()
                
            active_spam_tasks[chat_id] = asyncio.create_task(spam_loop(chat_id))

        # 8. Start Auto Reply (`လီးလား`) 🔄
        elif text == "လီးလား" and message.reply_to_message:
            target = message.reply_to_message.from_user
            if chat_id not in target_users: 
                target_users[chat_id] = []
                
            if len(target_users[chat_id]) >= MAX_TARGETS:
                if target.id not in [u.id for u in target_users[chat_id]]:
                    await client.send_message("me", f"⚠️ **Target ပြည့်သွားပါပြီ။**")
                    try: await message.delete()
                    except Exception: pass
                    return

            if target.id not in [u.id for u in target_users[chat_id]]:
                target_users[chat_id].append(target)
                current_count = len(target_users[chat_id])
                await client.send_message("me", f"🔄 **Target added (No-MT Auto Reply): {target.first_name} ({current_count}/{MAX_TARGETS})**")
                
            try: await message.delete() 
            except Exception: pass
            
            # "ဟာဘရို" Spam loop ကို ရပ်မည်
            if chat_id in active_spam_tasks:
                active_spam_tasks[chat_id].cancel()
                del active_spam_tasks[chat_id]

            auto_reply_chats.add(chat_id)

        # 9. Stop All (`အိုကေဘရို`) 🛑
        elif text == "အိုကေဘရို":
            if chat_id in active_spam_tasks:
                active_spam_tasks[chat_id].cancel()
                del active_spam_tasks[chat_id]
            if chat_id in auto_reply_chats:
                auto_reply_chats.remove(chat_id)
            if chat_id in target_users:
                target_users[chat_id] = []
            if chat_id in current_index:
                del current_index[chat_id]
                
            await client.send_message("me", "🔔 **စနစ်အားလုံးကို ရပ်လိုက်ပါပြီ**")
            try: await message.delete() 
            except Exception: pass
            
    except Exception as e:
        print(f"Command Error: {e}")

if __name__ == "__main__":
    print("Bot ကို စတင်မောင်းနှင်နေပါပြီ...")
    app.run()
        
