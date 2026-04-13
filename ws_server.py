import json
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from timetable_model import TimetableService
import uvicorn

app = FastAPI()

# Security: Allow the HTTP server (Port 8000) to talk to this WS server (Port 8001)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize the shared Data Model
service = TimetableService()
TARGET_DATE = "2026-04-07"
TIME_SLOTS = ["09:00", "10:00", "11:00", "12:00", "13:00", "14:00"]
service.initialize_day(TARGET_DATE, TIME_SLOTS)

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

# --- THE WEBSOCKET GATEWAY (Microservice 2) ---
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
    print("Starting WebSocket Gateway on ws://0.0.0.0:8001")
    # Runs on Port 8001!
    uvicorn.run(app, host="0.0.0.0", port=8001)