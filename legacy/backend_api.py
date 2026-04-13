import json
import os
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from timetable_model import TimetableService

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

service = TimetableService()
TARGET_DATE = "2026-04-07"
TIME_SLOTS = ["09:00", "10:00", "11:00", "12:00", "13:00", "14:00"]
service.initialize_day(TARGET_DATE, TIME_SLOTS)

# --- FRONTEND HOSTING ---
@app.get("/")
async def serve_frontend():
    """Serves the index.html file to the client's browser."""
    try:
        with open("index.html", "r") as f:
            html_content = f.read()
        return HTMLResponse(content=html_content, status_code=200)
    except FileNotFoundError:
        return HTMLResponse(content="<h1>Frontend not found! Ensure index.html is in the same folder.</h1>", status_code=404)

# --- WEBSOCKET CONNECTION MANAGER ---
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        print(f"[NETWORK] New client connected. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        print(f"[NETWORK] Client disconnected. Total: {len(self.active_connections)}")

    async def broadcast_state(self):
        message = {
            "grid": service.get_full_state(),
            "pending": service.get_pending()
        }
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                print(f"[ERROR] Failed to send to a client: {e}")

manager = ConnectionManager()

# --- THE WEBSOCKET GATEWAY ---
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    await manager.broadcast_state()

    try:
        while True:
            data = await websocket.receive_json()
            service.process_command(data)
            await manager.broadcast_state()
            
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        print(f"[CRITICAL ERROR] {e}")
        manager.disconnect(websocket)

if __name__ == "__main__":
    import uvicorn
    print("Starting Real-Time Backend Service on http://0.0.0.0:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)