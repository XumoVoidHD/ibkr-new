import aiohttp
import asyncio

# Replace this with your webhook URL
WEBHOOK_URL = "https://discord.com/api/webhooks/1335254176690602064/Re9xYddwThA3evUD0YNCft_jO6S2q5UYY1o1aGoxgPjYNeGKkp_WUyWSavbQCnrQlSta"


async def send_discord_message(content: str) -> bool:
    """
    Send a message to Discord webhook asynchronously.

    Args:
        content (str): The message to send

    Returns:
        bool: True if message was sent successfully, False otherwise
    """
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(WEBHOOK_URL, json={"content": content}) as response:
                if response.status == 204:
                    print(f"Message sent successfully: {content}")
                    return True
                else:
                    print(f"Failed to send message. Status code: {response.status}")
                    return False

    except Exception as e:
        print(f"Error sending message: {str(e)}")
        return False
