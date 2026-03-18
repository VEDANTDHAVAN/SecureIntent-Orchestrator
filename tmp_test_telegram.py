import asyncio
import os
from unittest.mock import patch, MagicMock
from tools.telegram_tool.tool import send_message

async def test_telegram_send_success():
    print("Testing Telegram send_message success...")
    with patch("httpx.AsyncClient.post") as mock_post:
        # Mock successful response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response
        
        os.environ["TELEGRAM_BOT_TOKEN"] = "mock_token"
        result = await send_message(chat_id="12345", text="Hello from SecureIntent")
        
        assert result["success"] is True
        assert result["status_code"] == 200
        print("✅ Success test passed!")

async def test_telegram_send_fail():
    print("Testing Telegram send_message failure...")
    with patch("httpx.AsyncClient.post") as mock_post:
        # Mock failure response
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {"description": "Bad Request"}
        mock_post.return_value = mock_response
        
        result = await send_message(chat_id="12345", text="Error test", token="mock_token")
        
        assert result["success"] is False
        assert "Bad Request" in result["error"]
        print("✅ Failure test passed!")

async def main():
    try:
        await test_telegram_send_success()
        await test_telegram_send_fail()
        print("\nAll tests passed!")
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")

if __name__ == "__main__":
    asyncio.run(main())