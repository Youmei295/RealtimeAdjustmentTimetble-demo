import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from timetable_model import TimetableService
import uvicorn

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

service = TimetableService()

@app.post("/api/command")
async def handle_command(command: dict):
    """
    1. Receive command from Frontend via HTTP POST
    2. Write to SQLite Database
    3. Tell the WS Server to broadcast via Webhook
    """
    # Write to database
    result = service.process_command(command)
    
    # Hit the Webhook on the WebSocket Server
    try:
        async with httpx.AsyncClient() as client:
            await client.post("http://localhost:8001/internal/broadcast")
    except Exception as e:
        print(f"[WARNING] Could not reach WebSocket Gateway: {e}")
        
    return result

if __name__ == "__main__":
    print("Starting REST API Server on http://0.0.0.0:8002")
    uvicorn.run(app, host="0.0.0.0", port=8002)