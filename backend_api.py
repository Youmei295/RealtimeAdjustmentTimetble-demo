import json
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Body
from fastapi.middleware.cors import CORSMiddleware
from timetable_model import TimetableService

app = FastAPI()

# --- SECURITY: CORS Middleware ---
# This allows your index.html file to communicate with this server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- INITIALIZATION ---
service = TimetableService()
# Matches the date used in your index.html
TARGET_DATE = "2026-04-07"
TIME_SLOTS = ["09:00", "10:00", "11:00", "12:00", "13:00", "14:00"]
service.initialize_day(TARGET_DATE, TIME_SLOTS)

# --- WEBSOCKET CONNECTION MANAGER ---
class ConnectionManager:
    def __init__(self):
        # List to store all active WebSocket objects
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        print(f"[NETWORK] New client connected. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        print(f"[NETWORK] Client disconnected. Total: {len(self.active_connections)}")

    async def broadcast_state(self):
        """
        Sends the current 'Source of Truth' to every connected user.
        This is called whenever the grid or pending queue changes.
        """
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
    
    # Send current state immediately so the new user isn't looking at an empty screen
    await manager.broadcast_state()

    try:
        while True:
            # Wait for a JSON command from a client (Member or Admin)
            data = await websocket.receive_json()
            
            # Process the command through our Timetable Logic
            # This handles ADD, REMOVE, OVERWRITE, and APPROVALS
            service.process_command(data)
            
            # After any command is processed, sync EVERYONE
            await manager.broadcast_state()
            
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        print(f"[CRITICAL ERROR] {e}")
        manager.disconnect(websocket)

# --- EXECUTION BLOCK ---
if __name__ == "__main__":
    import uvicorn
    # host="0.0.0.0" makes the server accessible on your local network
    # port=8000 must match the port in your index.html
    print("Starting Real-Time Backend Service...")
    uvicorn.run(app, host="0.0.0.0", port=8000)