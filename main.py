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

# Default setting (စိတ်ကြိုက်ပြန်ပြင်နိုင်သည်)
DEFAULT_DELAY = 10.0

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

target_users = {} 
active_tasks = {} 
current_index = {} 
chat_delays = {} # Chat တစ်ခုချင်းစီရဲ့ delay သိမ်းရန်

async def mention_loop(chat_id):
    current_delay = chat_delays.get(chat_id, DEFAULT_DELAY)
    print(f"[{chat_id}] MT စတင်ပတ်နေပါပြီ (Delay: {current_delay}s)...")
    
    while chat_id in active_tasks:
        try:
            all_data = db.get_all_replies()
            replies = [r[1] for r in all_data]
            
            if not replies: 
                print(f"[{chat_id}] အမှား - Database ထဲတွင် စာသားမရှိပါ။")
                try:
                    await app.send_message("me", "❌ **MT ရပ်သွားပါပြီ။ Database ထဲတွင် စာမရှိတော့ပါ။**")
                except Exception:
                    pass
                break
            
            if chat_id not in current_index:
                current_index[chat_id] = 0
            
            targets = target_users.get(chat_id, [])
            if not targets: 
                print(f"[{chat_id}] အမှား - Target list အလွတ်ဖြစ်နေသည်။")
                break
            
            # 💡 Username ရှိရင် Username၊ မရှိရင် Name ဖြင့် Mention ခေါ်မည့်စနစ်
            mentions_list = []
            for user in list(targets):
                if user.username:
                    mentions_list.append(f"@{user.username}")
                else:
                    mentions_list.append(f"[{user.first_name}](tg://user?id={user.id})")
            
            all_mentions_text = " ".join(mentions_list)
            
            idx = current_index[chat_id] % len(replies)
            reply = replies[idx]
            
            # Typing စနစ်ပြသခြင်း (Delay တန်ဖိုးပေါ်မူတည်၍ ချိန်ညှိသည်)
            try:
                if current_delay >= 2:
                    await app.send_chat_action(chat_id, ChatAction.TYPING)
                    await asyncio.sleep(1.5)
                else:
                    await app.send_chat_action(chat_id, ChatAction.TYPING)
                    await asyncio.sleep(0.1)
            except Exception:
                pass
            
            if chat_id not in active_tasks: break 
            
            # စာလှမ်းပို့ခြင်း 🚀
            await app.send_message(chat_id, f"{all_mentions_text} {reply}")
            print(f"[{chat_id}] စာသားပို့ပြီးပြီ - Index {idx}")
            
            current_index[chat_id] = idx + 1
            
            # ကျန်ရှိသော Delay အတိုင်း စောင့်ဆိုင်းခြင်း
            sleep_time = max(0.01, current_delay - 1.5 if current_delay >= 2 else current_delay - 0.1)
            await asyncio.sleep(sleep_time)
                
        except FloodWait as e:
            print(f"⚠️ FloodWait မိသွားသည်။ {e.value} စက္ကန့် စောင့်ဆိုင်းနေပါသည်...")
            await asyncio.sleep(e.value)
        except (RPCError, Exception) as e:
            print(f"🌐 ⚠️ ကွန်ရက်ချိတ်ဆက်မှု ပြဿနာ- {e}")
            await asyncio.sleep(2)

@app.on_message(filters.me & filters.text)
async def handle_commands(client, message):
    chat_id = message.chat.id
    text = message.text.strip()

    try:
        # 1. Help Menu 📖
        if text == "/help":
            delay_val = chat_delays.get(chat_id, DEFAULT_DELAY)
            help_msg = (
                f"📌 **MT Bot Advanced V5.0**\n\n"
                f"🔹 `ဟာဘရို` - Target စုထည့်ပြီး MT စတင်ရန် (Max {MAX_TARGETS})\n"
                f"🔹 `အိုကေဘရို` - Target အကုန်ရပ်ရန်\n"
                f"🔹 `/delay [0.1-10]` - စက္ကန့်အနှေးအမြန်ချိန်ရန်\n"
                f"🔹 `/add_reply [စာ]` - စာတစ်ကြောင်းချင်းထည့်\n"
                f"🔹 `/add_multi [စာသားများ]` - စာအများကြီးတစ်ခါတည်းထည့်\n"
                f"🔹 `/del_reply [ID]` - စာဖျက်\n"
                f"🔹 `/list_reply` - စာရင်းကြည့်\n\n"
                f"⏱ **လက်ရှိ Delay:** {delay_val} စက္ကန့်"
            )
            await client.send_message("me", help_msg)
            try: await message.delete() 
            except Exception: pass
            return

        # 2. Delay ချိန်ညှိခြင်း စနစ် ⏱ (0.1 မှ 10 စက္ကန့်အထိ)
        elif text.startswith("/delay"):
            parts = text.split(None, 1)
            if len(parts) >= 2:
                try:
                    val = float(parts[1])
                    if 0.1 <= val <= 10.0:
                        chat_delays[chat_id] = val
                        await client.send_message("me", f"⏱ **Delay ကို `{val}` စက္ကန့်သို့ ပြောင်းလဲလိုက်ပါပြီ။**")
                        # Loop မောင်းနေလျှင် Delay အသစ်ချက်ချင်းသက်ရောက်စေရန် Update လုပ်ပေးခြင်း
                        if chat_id in active_tasks:
                            active_tasks[chat_id].cancel()
                            active_tasks[chat_id] = asyncio.create_task(mention_loop(chat_id))
                    else:
                        await client.send_message("me", "⚠️ **ကျေးဇူးပြု၍ 0.1 မှ 10 စက္ကန့်အတွင်းသာ ချိန်ပေးပါ။**")
                except ValueError:
                    await client.send_message("me", "⚠️ **နံပါတ် အမှန်ကန်ဆုံး ထည့်သွင်းပေးပါ။ (ဥပမာ- `/delay 0.5`)**")
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
                    start_id = None
                    end_id = None
                    for line in lines:
                        last_id = db.add_reply(line)
                        if start_id is None: start_id = last_id
                        end_id = last_id
                    await client.send_message(
                        "me", 
                        f"🚀 **စာသား สုစုပေါင်း {len(lines)} ခုကို ID `{start_id}` မှ `{end_id}` အထိ တစ်ခါတည်း အစဉ်လိုက် သိမ်းဆည်းပေးလိုက်ပါပြီ။**"
                    )
            try: await message.delete()
            except Exception: pass
            return

        # 5. List Reply 📑
        elif text == "/list_reply":
            replies = db.get_all_replies()
            if not replies:
                await client.send_message("me", "❌ Database ထဲတွင် စာမရှိသေးပါ")
            else:
                total = len(replies)
                await client.send_message("me", f"📑 **စုစုပေါင်း စာသား {total} ခု ရှိသည်:**")
                for i in range(0, total, 8):
                    chunk = replies[i:i+8]
                    msg = ""
                    for r_id, r_text in chunk:
                        msg += f"🆔 `{r_id}`: {r_text}\n\n"
                    await client.send_message("me", msg)
                    await asyncio.sleep(0.5)
            try: await message.delete()
            except Exception: pass
            return

        # 6. Start MT & Target Adding (`ဟာဘရို`) 🎯
        elif text == "ဟာဘရို" and message.reply_to_message:
            target = message.reply_to_message.from_user
            if chat_id not in target_users: 
                target_users[chat_id] = []
                
            if len(target_users[chat_id]) >= MAX_TARGETS:
                if target.id not in [u.id for u in target_users[chat_id]]:
                    await client.send_message("me", f"⚠️ **Target ပြည့်သွားပါပြီ။ အများဆုံး {MAX_TARGETS} ယောက်အထိပဲ ခေါ်လို့ရပါတယ်။**")
                    try: await message.delete()
                    except Exception: pass
                    return

            if target.id not in [u.id for u in target_users[chat_id]]:
                target_users[chat_id].append(target)
                current_count = len(target_users[chat_id])
                await client.send_message("me", f"🎯 **Target added: {target.first_name} ({current_count}/{MAX_TARGETS})**")
                
            try: await message.delete() 
            except Exception: pass
            
            if chat_id in active_tasks:
                active_tasks[chat_id].cancel()
                
            active_tasks[chat_id] = asyncio.create_task(mention_loop(chat_id))

        # 7. Stop All (`အိုကေဘရို`) 🛑
        elif text == "အိုကေဘရို":
            if chat_id in active_tasks:
                active_tasks[chat_id].cancel()
                del active_tasks[chat_id]
            if chat_id in target_users:
                target_users[chat_id] = []
            if chat_id in current_index:
                current_index[chat_id] = 0
                
            await client.send_message("me", "🔔 **MT အကုန်ရပ်လိုက်ပါပြီ**")
            try: await message.delete() 
            except Exception: pass
            
    except Exception as e:
        print(f"Command Error: {e}")

if __name__ == "__main__":
    print("Bot ကို စတင်မောင်းနှင်နေပါပြီ...")
    app.run()
