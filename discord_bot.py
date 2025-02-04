import aiohttp
import asyncio
import credentials

# Replace this with your webhook URL
WEBHOOK_URL = credentials.WEBHOOK_URL


async def send_discord_message(content: str) -> bool:
    """
    Send a message to Discord webhook asynchronously, first sending a separator message.

    Args:
        content (str): The message to send

    Returns:
        bool: True if message was sent successfully, False otherwise
    """
    try:
        async with aiohttp.ClientSession() as session:
            # Send separator message
            async with session.post(WEBHOOK_URL, json={"content": "." * 100}) as response:
                if response.status != 204:
                    print(f"Failed to send separator. Status code: {response.status}")
                    return False

            # Send actual message
            async with session.post(WEBHOOK_URL, json={"content": content}) as response:
                if response.status == 204:
                    return True
                else:
                    print(f"Failed to send message. Status code: {response.status}")
                    return False

    except Exception as e:
        print(f"Error sending message: {str(e)}")
        return False
