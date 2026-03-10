import asyncio
import httpx
import websockets
import json
import subprocess
import time

async def verify_app():
    # Start the server
    p = subprocess.Popen(['uvicorn', 'main:app', '--port', '8080'])
    time.sleep(5)  # wait for startup

    try:
        # 1. Test Static files
        async with httpx.AsyncClient() as client:
            resp = await client.get('http://127.0.0.1:8080/')
            assert resp.status_code == 200, "Failed to load index.html"
            assert "Polymarket Scalper" in resp.text, "index.html missing title"

            resp = await client.get('http://127.0.0.1:8080/app.js')
            assert resp.status_code == 200, "Failed to load app.js"

            resp = await client.get('http://127.0.0.1:8080/style.css')
            assert resp.status_code == 200, "Failed to load style.css"

        # 2. Test REST API /api/markets
        async with httpx.AsyncClient() as client:
            resp = await client.get('http://127.0.0.1:8080/api/markets')
            assert resp.status_code == 200, "Failed to fetch markets"
            markets = resp.json()
            assert isinstance(markets, list), "Markets should be a list"
            if markets:
                assert "title" in markets[0], "Market missing title"
                assert "yes_price" in markets[0], "Market missing yes_price"
                print(f"Verified {len(markets)} active markets.")

        # 3. Test REST API /api/order
        async with httpx.AsyncClient() as client:
            payload = {
                "token_id": "test_token",
                "side": "BUY",
                "outcome": "YES",
                "size": 1.0
            }
            resp = await client.post('http://127.0.0.1:8080/api/order', json=payload)
            assert resp.status_code == 200, "Failed to post order"
            order_res = resp.json()
            assert "status" in order_res, "Order response missing status"
            assert order_res["status"] == "error", "Order with dummy creds should fail"
            print("Verified order failure works as expected with dummy config.")

        # 4. Test WebSocket /ws/price
        async with websockets.connect('ws://127.0.0.1:8080/ws/price') as ws:
            for i in range(2):
                msg = await ws.recv()
                data = json.loads(msg)
                assert "price" in data, "WebSocket missing price key"
                print(f"Verified WebSocket price: {data['price']}")

        print("\nAll integration tests passed successfully.")

    finally:
        p.terminate()
        p.wait()

if __name__ == "__main__":
    asyncio.run(verify_app())
