import os
import asyncio
import httpx
from dotenv import load_dotenv

async def diag_telegram():
    load_dotenv()
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    
    print(f"--- Telegram Diagnostics ---")
    print(f"Token: {token[:10]}...{token[-5:] if token else 'None'}")
    print(f"Chat ID: {chat_id}")
    
    if not token or not chat_id:
        print("ERROR: Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID in .env")
        return

    async with httpx.AsyncClient() as client:
        # 1. Test getMe
        print("\n1. Testing bot token (getMe)...")
        me_resp = await client.get(f"https://api.telegram.org/bot{token}/getMe")
        print(f"Response: {me_resp.status_code} {me_resp.text}")
        
        if me_resp.status_code != 200:
            print("ERROR: Invalid bot token.")
            return
            
        bot_username = me_resp.json().get("result", {}).get("username")
        print(f"SUCCESS: Bot is @{bot_username}")

        # 2. Test getUpdates (Check if user has started bot)
        print("\n2. Checking for recent messages to bot (getUpdates)...")
        upd_resp = await client.get(f"https://api.telegram.org/bot{token}/getUpdates")
        updates = upd_resp.json().get("result", [])
        print(f"Found {len(updates)} recent updates.")
        
        found_user = False
        for u in updates:
            msg = u.get("message", {}) or u.get("edited_message", {})
            from_info = msg.get("from", {})
            from_id = from_info.get("id")
            username = from_info.get("username", "no_username")
            if from_id:
                print(f" - Found interaction from User ID: {from_id} (@{username})")
                if str(from_id) == str(chat_id):
                    found_user = True
                    print(f"   >>> MATCH: This matches your target Chat ID!")
        
        if not found_user:
            print(f"\nWARNING: User {chat_id} has NOT started a chat with @{bot_username} yet.")
            print(f"ACTION REQUIRED: Go to Telegram, search for @{bot_username}, and click 'START'.")

        # 3. Test sendMessage
        print(f"\n3. Testing sendMessage to {chat_id}...")
        sm_resp = await client.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": "Diagnostic test from SecureIntent"}
        )
        print(f"Response: {sm_resp.status_code} {sm_resp.text}")
        
        if sm_resp.status_code == 200:
            print("SUCCESS: Message sent!")
        else:
            print(f"FAILED: Telegram rejected the message. Most likely you haven't started a chat with this specific bot.")

if __name__ == "__main__":
    asyncio.run(diag_telegram())
