import json
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from timetable_model import TimetableService
import uvicorn

app = FastAPI()

# Security: Allow the HTTP server and API server to talk to this WS server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize the shared Data Model (reads from SQLite)
service = TimetableService()

# --- WEBSOCKET CONNECTION MANAGER ---
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        print(f"[NETWORK] Client connected. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        print(f"[NETWORK] Client disconnected.")

    async def broadcast_state(self):
        # Fetch fresh data from SQLite and broadcast
        message = {"grid": service.get_full_state(), "pending": service.get_pending()}
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                print(f"[ERROR] Failed to send to a client: {e}")

manager = ConnectionManager()

# --- INTERNAL WEBHOOK (Replaces Redis) ---
@app.post("/internal/broadcast")
async def trigger_broadcast():
    """
    An internal webhook called by the api_server (Port 8002).
    When the API updates the database, it hits this endpoint to tell 
    the WebSocket Gateway to push the new data to all connected browsers.
    """
    print("[WEBHOOK] Signal received from API! Broadcasting to WebSockets...")
    await manager.broadcast_state()
    return {"status": "broadcast_triggered"}

# --- THE WEBSOCKET GATEWAY ---
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    await manager.broadcast_state() # Send initial data on connect

    try:
        while True:
            # We just wait here to keep the connection alive. 
            # The client no longer sends commands through the WebSocket!
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        print(f"[CRITICAL ERROR] {e}")
        manager.disconnect(websocket)

if __name__ == "__main__":
    print("Starting WebSocket Gateway on ws://0.0.0.0:8001")
    uvicorn.run(app, host="0.0.0.0", port=8001)