import asyncio
import httpx
import json

async def test():
    url = "http://127.0.0.1:8765"
    payload = {"action": "version", "version": 6}
    print(f"Testing connection to {url}...")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(url, json=payload)
            print(f"Status: {resp.status_code}")
            print(f"Response: {resp.text}")
            if resp.status_code == 200:
                print("SUCCESS: AnkiConnect is reachable from Python.")
            else:
                print("FAILURE: AnkiConnect returned non-200 status.")
    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}")

if __name__ == "__main__":
    asyncio.run(test())
