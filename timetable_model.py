import json
import sqlite3
import os
from typing import Dict, Optional, List

# Define an absolute path for the database file
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, "timetable.db")

class TimetableService:
    def __init__(self):
        self._db_path = DB_PATH
        self._init_db()
        
        self._pending_requests: List[dict] = []
        self._request_id_counter = 1
        
        # Account Role Registry (RBAC)
        self._accounts = {
            "admin_1": {"role": "ADMIN", "name": "System Admin"},
            "user_alice": {"role": "MEMBER", "name": "Alice"},
            "user_bob": {"role": "MEMBER", "name": "Bob"}
        }

    # --- DATABASE SETUP ---

    def _init_db(self):
        """Creates the database table if it doesn't exist."""
        with sqlite3.connect(self._db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS slots (
                    date TEXT,
                    time TEXT,
                    member_id TEXT,
                    task TEXT,
                    PRIMARY KEY (date, time)
                )
            ''')
            conn.commit()

    def get_user_info(self, user_id: str) -> Optional[dict]:
        return self._accounts.get(user_id)

    # --- READ OPERATIONS (Translating SQL back to JSON) ---

    def initialize_day(self, date: str, slots: list):
        """We no longer need to build an empty dict, but we keep this for API compatibility."""
        pass 

    def get_full_state(self) -> dict:
        """Reads from the Database and builds the JSON grid your frontend expects."""
        grid = {}
        target_date = "2026-04-07"
        time_slots = ["09:00", "10:00", "11:00", "12:00", "13:00", "14:00"]
        
        # 1. Setup the empty structure
        grid[target_date] = {t: None for t in time_slots}

        # 2. Fetch saved data from SQLite
        with sqlite3.connect(self._db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT date, time, member_id, task FROM slots WHERE date=?", (target_date,))
            rows = cursor.fetchall()
            
            # 3. Populate the JSON grid with database records
            for date, time, member_id, task in rows:
                if time in grid[target_date]:
                    grid[target_date][time] = {"member_id": member_id, "task": task}
                    
        return grid

    def get_pending(self) -> list:
        return self._pending_requests

    # --- WRITE OPERATIONS (Transaction Logic) ---

    def process_command(self, command: dict) -> dict:
        user_id = command.get("member_id")
        user_info = self.get_user_info(user_id)
        
        if not user_info:
            print(f"[SECURITY] Blocked unknown user ID: {user_id}")
            return {"status": "error", "msg": "Access Denied"}
            
        role = user_info["role"]
        
        if role == "ADMIN":
            return self._execute_admin_command(command)
        else:
            return self._queue_request(command)

    def _execute_admin_command(self, cmd: dict) -> dict:
        action = cmd.get("action")
        date, time = cmd.get("date"), cmd.get("time")
        reason = cmd.get("reason", "No reason provided")
        admin_id = cmd.get("member_id")

        with sqlite3.connect(self._db_path) as conn:
            cursor = conn.cursor()
            
            if action in ["ADD", "OVERWRITE"]:
                # REPLACE INTO overwrites if the primary key (date, time) already exists
                cursor.execute(
                    "REPLACE INTO slots (date, time, member_id, task) VALUES (?, ?, ?, ?)",
                    (date, time, cmd.get("target_member", admin_id), cmd.get("task", "Task"))
                )
                print(f"[AUDIT LOG] ADMIN {admin_id} executed {action} at {time}. Reason: {reason}")
                msg = f"Admin applied {action}"
            
            elif action in ["REMOVE", "ADMIN_REMOVE"]:
                cursor.execute("DELETE FROM slots WHERE date=? AND time=?", (date, time))
                print(f"[AUDIT LOG] ADMIN {admin_id} deleted {time} slot. Reason: {reason}")
                msg = "Admin cleared slot"
            
            elif action == "APPROVE_PENDING":
                # Handle approvals without blocking the DB connection
                pass 
                
            conn.commit()

        if action == "APPROVE_PENDING":
            return self._resolve_pending(cmd.get("request_id"), cmd.get("approved", False), admin_id)
            
        return {"status": "success", "msg": msg}

    def _queue_request(self, cmd: dict) -> dict:
        cmd["request_id"] = self._request_id_counter
        self._pending_requests.append(cmd)
        self._request_id_counter += 1
        return {"status": "pending", "request_id": cmd["request_id"]}

    def _resolve_pending(self, req_id: int, approved: bool, admin_id: str) -> dict:
        req = next((r for r in self._pending_requests if r["request_id"] == req_id), None)
        if not req: return {"status": "error"}

        self._pending_requests.remove(req)
        
        if approved:
            action, reason = req.get("action"), req.get("reason", "No reason provided")
            
            with sqlite3.connect(self._db_path) as conn:
                cursor = conn.cursor()
                if action in ["ADD", "OVERWRITE"]:
                    cursor.execute(
                        "REPLACE INTO slots (date, time, member_id, task) VALUES (?, ?, ?, ?)",
                        (req["date"], req["time"], req["member_id"], req.get("task", "Task"))
                    )
                elif action in ["REMOVE", "ADMIN_REMOVE"]:
                    cursor.execute("DELETE FROM slots WHERE date=? AND time=?", (req["date"], req["time"]))
                conn.commit()
                
            print(f"[AUDIT LOG] ADMIN {admin_id} Approved Request {req_id} ({action}) at {req['time']}. Reason: {reason}")
            return {"status": "success"}
        
        return {"status": "rejected"}