
import httpx
import asyncio

async def test():
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post("http://localhost:8765", json={"action": "version", "version": 6})
            print(f"Status: {resp.status_code}")
            print(f"Body: {resp.text}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test())
