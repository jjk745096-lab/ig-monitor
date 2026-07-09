import os
import json
import requests
import instaloader

# ===================== تنظیمات از GitHub Secrets =====================
MANAGEMENT_BOT_TOKEN = os.environ["MANAGEMENT_BOT_TOKEN"]
OWNER_CHAT_ID = str(os.environ["OWNER_CHAT_ID"])

ACCOUNTS_FILE = "accounts.json"
STATE_FILE = "state.json"


def load_json(path, default):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def send_message(bot_token, chat_id, text):
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    requests.post(url, data={"chat_id": chat_id, "text": text})


def get_updates(bot_token, offset):
    url = f"https://api.telegram.org/bot{bot_token}/getUpdates"
    params = {"offset": offset, "timeout": 0}
    r = requests.get(url, params=params, timeout=15)
    return r.json().get("result", [])


def process_commands(accounts, state):
    offset = state.get("telegram_offset", 0)
    updates = get_updates(MANAGEMENT_BOT_TOKEN, offset)

    for update in updates:
        state["telegram_offset"] = update["update_id"] + 1
        message = update.get("message", {})
        chat_id = str(message.get("chat", {}).get("id", ""))
        text = message.get("text", "").strip()

        if chat_id != OWNER_CHAT_ID:
            continue

        if not text:
            continue

        parts = text.split()
        cmd = parts[0].lower()

        if cmd == "/add" and len(parts) >= 4:
            username = parts[1].lstrip("@")
            bot_token = parts[2]
            target_chat_id = parts[3]
            ig_login_user = parts[4] if len(parts) > 4 else ""
            ig_login_pass = parts[5] if len(parts) > 5 else ""

            accounts = [a for a in accounts if a["username"] != username]
            accounts.append({
                "username": username,
                "bot_token": bot_token,
                "chat_id": target_chat_id,
                "ig_login_user": ig_login_user,
                "ig_login_pass": ig_login_pass,
            })
            send_message(MANAGEMENT_BOT_TOKEN, chat_id,
                          f"✅ پیج {username} اضافه شد و لینک‌هاش به chat_id {target_chat_id} فرستاده می‌شه.")

        elif cmd == "/remove" and len(parts) >= 2:
            username = parts[1].lstrip("@")
            before = len(accounts)
            accounts = [a for a in accounts if a["username"] != username]
            if len(accounts) < before:
                send_message(MANAGEMENT_BOT_TOKEN, chat_id, f"🗑️ پیج {username} حذف شد.")
            else:
                send_message(MANAGEMENT_BOT_TOKEN, chat_id, f"⚠️ پیجی به اسم {username} پیدا نشد.")

        elif cmd == "/list":
            if not accounts:
                send_message(MANAGEMENT_BOT_TOKEN, chat_id, "لیست خالیه، هنوز پیجی اضافه نکردی.")
            else:
                lines = [f"- {a['username']} → chat_id: {a['chat_id']}" for a in accounts]
                send_message(MANAGEMENT_BOT_TOKEN, chat_id, "📋 پیج‌های مانیتور شده:\n" + "\n".join(lines))

        elif cmd == "/help":
            help_text = (
                "دستورات:\n"
                "/add یوزرنیم توکن_ربات چت_آیدی [یوزر_لاگین] [پسورد_لاگین]\n"
                "/remove یوزرنیم\n"
                "/list\n"
            )
            send_message(MANAGEMENT_BOT_TOKEN, chat_id, help_text)

    return accounts, state


def check_account(account, page_state):
    username = account["username"]
    bot_token = account["bot_token"]
    chat_id = account["chat_id"]
    ig_login_user = account.get("ig_login_user") or ""
    ig_login_pass = account.get("ig_login_pass") or ""

    L = instaloader.Instaloader()
    if ig_login_user and ig_login_pass:
        try:
            L.login(ig_login_user, ig_login_pass)
        except Exception as e:
            print(f"[{username}] لاگین ناموفق: {e}")

    try:
        profile = instaloader.Profile.from_username(L.context, username)
    except Exception as e:
        print(f"[{username}] خطا در گرفتن پروفایل: {e}")
        return page_state

    try:
        latest_post = next(profile.get_posts(), None)
        if latest_post:
            post_id = str(latest_post.mediaid)
            if post_id != page_state.get("last_post_id"):
                link = f"https://www.instagram.com/p/{latest_post.shortcode}/"
                send_message(bot_token, chat_id, f"📸 پست جدید از {username}:\n{link}")
                page_state["last_post_id"] = post_id
    except Exception as e:
        print(f"[{username}] خطا در چک پست: {e}")

    if ig_login_user and ig_login_pass:
        try:
            seen_stories = page_state.get("seen_stories", [])
            stories = L.get_stories(userids=[profile.userid])
            for story in stories:
                for item in story.get_items():
                    story_id = str(item.mediaid)
                    if story_id not in seen_stories:
                        send_message(
                            bot_token, chat_id,
                            f"⭐ استوری جدید از {username}:\n"
                            f"https://www.instagram.com/stories/{username}/{item.mediaid}/"
                        )
                        seen_stories.append(story_id)
            page_state["seen_stories"] = seen_stories[-50:]
        except Exception as e:
            print(f"[{username}] خطا در چک استوری: {e}")

    return page_state


def main():
    accounts = load_json(ACCOUNTS_FILE, [])
    state = load_json(STATE_FILE, {"telegram_offset": 0, "pages": {}})

    accounts, state = process_commands(accounts, state)
    save_json(ACCOUNTS_FILE, accounts)

    for account in accounts:
        username = account["username"]
        page_state = state["pages"].get(username, {})
        page_state = check_account(account, page_state)
        state["pages"][username] = page_state

    save_json(STATE_FILE, state)


if __name__ == "__main__":
    main()
