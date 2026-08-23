import asyncio
import json
import os
from pyrogram import Client, filters
from pyrogram.enums import ChatAction
from pyrogram.errors import FloodWait, RPCError
from pyrogram import idle

# --- Configuration (Environment Variables မှ ယူခြင်း) ---
API_ID = int(os.environ.get("API_ID", 32593259))
API_HASH = os.environ.get("API_HASH", "248f3abd799b6e88bbfe44332e3f09b2")
SESSION_STRING = os.environ.get("SESSION_STRING")

MAX_TARGETS = 10    
DEFAULT_DELAY = 1.0 

# JSON Database
DB_FILE = "replies_db.json"

class JSONDatabase:
    def __init__(self, filename=DB_FILE):
        self.filename = filename
        if not os.path.exists(self.filename):
            with open(self.filename, 'w', encoding='utf-8') as f:
                json.dump([], f)

    def _read_data(self):
        try:
            with open(self.filename, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return []

    def _write_data(self, data):
        with open(self.filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def add_reply(self, text):
        data = self._read_data()
        new_id = (data[-1]['id'] + 1) if data else 1
        data.append({"id": new_id, "text": text})
        self._write_data(data)
        return new_id

    def del_reply(self, reply_id):
        data = self._read_data()
        initial_len = len(data)
        data = [r for r in data if r['id'] != reply_id]
        if len(data) < initial_len:
            self._write_data(data)
            return True
        return False

    def get_all_replies(self):
        data = self._read_data()
        return [(r['id'], r['text']) for r in data]

db = JSONDatabase()

app = Client(
    "my_userbot",
    api_id=API_ID,
    api_hash=API_HASH,
    session_string=SESSION_STRING
)

target_users = {}         
active_spam_tasks = {}    
auto_reply_chats = set()  
chat_delays = {}          
current_index = {}        

# 🚀 1. "ဟာဘရို" Spam Loop
async def spam_loop(chat_id):
    current_delay = chat_delays.get(chat_id, DEFAULT_DELAY)
    
    while chat_id in active_spam_tasks:
        try:
            all_data = db.get_all_replies()
            replies = [r[1] for r in all_data]
            
            if not replies:
                try: await app.send_message("me", "❌ **Spam ရပ်သွားပါပြီ။ Database ထဲတွင် စာမရှိတော့ပါ။**")
                except Exception: pass
                break
            
            if chat_id not in current_index:
                current_index[chat_id] = 0
            
            targets = target_users.get(chat_id, [])
            if not targets:
                break
            
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
            
            await app.send_message(chat_id, final_text)
            current_index[chat_id] = idx + 1
            await asyncio.sleep(current_delay)
                
        except FloodWait as e:
            await asyncio.sleep(e.value)
        except (RPCError, Exception):
            await asyncio.sleep(1)

# 🔄 2. "လီးလား" Auto Reply Handler
@app.on_message(filters.group & ~filters.me)
async def auto_reply_handler(client, message):
    chat_id = message.chat.id
    if chat_id in auto_reply_chats and chat_id in target_users:
        target_ids = [u.id for u in target_users[chat_id]]
        if message.from_user and message.from_user.id in target_ids:
            try:
                all_data = db.get_all_replies()
                replies = [r[1] for r in all_data]
                if not replies: return

                if chat_id not in current_index:
                    current_index[chat_id] = 0

                idx = current_index[chat_id] % len(replies)
                reply = replies[idx]
                current_index[chat_id] = idx + 1

                await message.reply_text(reply)
            except FloodWait as e:
                await asyncio.sleep(e.value)
            except Exception as e:
                print(f"Auto Reply Error: {e}")

# 🎮 Command Handler
@app.on_message(filters.me & filters.text)
async def handle_commands(client, message):
    chat_id = message.chat.id
    text = message.text.strip()

    try:
        if text == "/help":
            delay_val = chat_delays.get(chat_id, DEFAULT_DELAY)
            help_msg = (
                f"📌 **Ultimate Bot Menu**\n\n"
                f"🔹 `ဟာဘရို` - Auto Spam Loop 🚀\n"
                f"🔹 `လီးလား` - Auto Reply 🔄\n"
                f"🔹 `အိုကေဘရို` - ရပ်ရန် 🛑\n"
                f"🔹 `/delay [0.1-10]` - အမြန်နှုန်းချိန်ရန်\n"
                f"🔹 `/add_reply [စာ]` - စာတစ်ကြောင်းချင်းထည့်\n"
                f"🔹 `/add_multi [စာသားများ]` - စာအများကြီးတစ်ခါတည်းထည့်\n"
                f"🔹 `/del_reply [ID]` - စာဖျက်\n"
                f"🔹 `/list_reply` - စာရင်းကြည့်\n\n"
                f"⏱ **Spam Delay:** {delay_val}s"
            )
            await client.send_message("me", help_msg)
            try: await message.delete() 
            except Exception: pass

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
                except ValueError: pass
            try: await message.delete()
            except Exception: pass

        elif text.startswith("/add_reply"):
            parts = text.split(None, 1)
            if len(parts) >= 2:
                new_id = db.add_reply(parts[1])
                await client.send_message("me", f"✅ **ID {new_id} အဖြစ် သိမ်းဆည်းပြီးပါပြီ**")
            try: await message.delete()
            except Exception: pass

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

        elif text in ["list_reply", "/list_reply"]:
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

        elif text == "ဟာဘရို" and message.reply_to_message:
            target = message.reply_to_message.from_user
            if chat_id not in target_users: target_users[chat_id] = []
            if len(target_users[chat_id]) >= MAX_TARGETS and target.id not in [u.id for u in target_users[chat_id]]:
                await client.send_message("me", "⚠️ **Target ပြည့်သွားပါပြီ။**")
                try: await message.delete()
                except Exception: pass
                return

            if target.id not in [u.id for u in target_users[chat_id]]:
                target_users[chat_id].append(target)
                current_count = len(target_users[chat_id])
                await client.send_message("me", f"🚀 **Target added (Auto MT Spam Loop): {target.first_name} ({current_count}/{MAX_TARGETS})**")
                
            try: await message.delete() 
            except Exception: pass
            
            if chat_id in auto_reply_chats: auto_reply_chats.remove(chat_id)
            if chat_id in active_spam_tasks: active_spam_tasks[chat_id].cancel()
            active_spam_tasks[chat_id] = asyncio.create_task(spam_loop(chat_id))

        elif text == "လီးလား" and message.reply_to_message:
            target = message.reply_to_message.from_user
            if chat_id not in target_users: target_users[chat_id] = []
            if len(target_users[chat_id]) >= MAX_TARGETS and target.id not in [u.id for u in target_users[chat_id]]:
                await client.send_message("me", "⚠️ **Target ပြည့်သွားပါပြီ။**")
                try: await message.delete()
                except Exception: pass
                return

            if target.id not in [u.id for u in target_users[chat_id]]:
                target_users[chat_id].append(target)
                current_count = len(target_users[chat_id])
                await client.send_message("me", f"🔄 **Target added (No-MT Auto Reply): {target.first_name} ({current_count}/{MAX_TARGETS})**")
                
            try: await message.delete() 
            except Exception: pass
            
            if chat_id in active_spam_tasks:
                active_spam_tasks[chat_id].cancel()
                del active_spam_tasks[chat_id]
            auto_reply_chats.add(chat_id)

        elif text == "အိုကေဘရို":
            if chat_id in active_spam_tasks:
                active_spam_tasks[chat_id].cancel()
                del active_spam_tasks[chat_id]
            if chat_id in auto_reply_chats: auto_reply_chats.remove(chat_id)
            if chat_id in target_users: target_users[chat_id] = []
            if chat_id in current_index: del current_index[chat_id]
                
            await client.send_message("me", "🔔 **စနစ်အားလုံးကို ရပ်လိုက်ပါပြီ**")
            try: await message.delete() 
            except Exception: pass

    except Exception as e:
        print(f"Command Error: {e}")

# Cloud မဂ်လာ မရပ်သွားစေရန် Asyncio Loop စနစ်ဖြင့် မောင်းနှင်ခြင်း
async def start_main():
    await app.start()
    print("Bot 🚀 Render Cloud ပေါ်တွင် စတင်အလုပ်လုပ်နေပါပြီ...")
    await idle()
    await app.stop()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(start_main())
    
