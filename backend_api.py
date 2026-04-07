# backend_api.py
from fastapi import FastAPI, Body
from fastapi.middleware.cors import CORSMiddleware
from timetable_model import TimetableService

app = FastAPI()

# Allow the Web App to talk to this API (CORS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize our pure data service
service = TimetableService()
service.initialize_day("2026-04-07", ["09:00", "10:00", "11:00", "12:00", "13:00"])

@app.get("/state")
def get_state():
    return {"grid": service.get_full_state(), "pending": service.get_pending()}

@app.post("/command")
def handle_command(payload: dict = Body(...)):
    # This passes the JSON from the Web App directly to our model
    response = service.process_command(payload)
    return response

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)