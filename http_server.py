import os
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
import uvicorn

app = FastAPI()

# --- FRONTEND HOSTING (Microservice 1) ---
@app.get("/")
async def serve_frontend():
    """Serves the index.html file to the client's browser."""
    try:
        with open("index.html", "r") as f:
            html_content = f.read()
        return HTMLResponse(content=html_content, status_code=200)
    except FileNotFoundError:
        return HTMLResponse(content="<h1>Frontend not found! Ensure index.html is in the same folder.</h1>", status_code=404)

if __name__ == "__main__":
    print("Starting HTTP Web Server on http://0.0.0.0:8000")
    # Runs on Port 8000
    uvicorn.run(app, host="0.0.0.0", port=8000)