import json
import sqlite3
import os
from typing import Dict, Optional, List

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, "timetable.db")

class TimetableService:
    def __init__(self):
        self._db_path = DB_PATH
        self._init_db()
        
        # Account Role Registry (RBAC)
        self._accounts = {
            "admin_1": {"role": "ADMIN", "name": "System Admin"},
            "user_alice": {"role": "MEMBER", "name": "Alice"},
            "user_bob": {"role": "MEMBER", "name": "Bob"}
        }

    # --- DATABASE SETUP ---
    def _init_db(self):
        """Creates tables for both the active grid AND the pending requests."""
        with sqlite3.connect(self._db_path) as conn:
            cursor = conn.cursor()
            
            # The Active Timetable
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS slots (
                    date TEXT, time TEXT, member_id TEXT, task TEXT,
                    PRIMARY KEY (date, time)
                )
            ''')
            
            # NEW: The Pending Queue (Shared across all Microservices)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS pending_requests (
                    request_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    action TEXT, date TEXT, time TEXT, member_id TEXT, 
                    target_member TEXT, task TEXT, reason TEXT
                )
            ''')
            conn.commit()

    def get_user_info(self, user_id: str) -> Optional[dict]:
        return self._accounts.get(user_id)

    # --- READ OPERATIONS ---
    def initialize_day(self, date: str, slots: list):
        pass 

    def get_full_state(self) -> dict:
        grid = {}
        target_date = "2026-04-07"
        time_slots = ["09:00", "10:00", "11:00", "12:00", "13:00", "14:00"]
        grid[target_date] = {t: None for t in time_slots}

        with sqlite3.connect(self._db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT date, time, member_id, task FROM slots WHERE date=?", (target_date,))
            for date, time, member_id, task in cursor.fetchall():
                if time in grid[target_date]:
                    grid[target_date][time] = {"member_id": member_id, "task": task}
        return grid

    def get_pending(self) -> list:
        """Fetches pending requests directly from SQLite."""
        pending = []
        with sqlite3.connect(self._db_path) as conn:
            # row_factory lets us easily convert SQL rows into Python dictionaries
            conn.row_factory = sqlite3.Row 
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM pending_requests")
            
            for row in cursor.fetchall():
                pending.append(dict(row))
        return pending

    # --- WRITE OPERATIONS ---
    def process_command(self, command: dict) -> dict:
        user_id = command.get("member_id")
        user_info = self.get_user_info(user_id)
        
        if not user_info:
            print(f"[SECURITY] Blocked unknown user ID: {user_id}")
            return {"status": "error", "msg": "Access Denied"}
            
        if user_info["role"] == "ADMIN":
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
                cursor.execute(
                    "REPLACE INTO slots (date, time, member_id, task) VALUES (?, ?, ?, ?)",
                    (date, time, cmd.get("target_member", admin_id), cmd.get("task", "Task"))
                )
                print(f"[AUDIT LOG] ADMIN {admin_id} executed {action} at {time}. Reason: {reason}")
            
            elif action in ["REMOVE", "ADMIN_REMOVE"]:
                cursor.execute("DELETE FROM slots WHERE date=? AND time=?", (date, time))
                print(f"[AUDIT LOG] ADMIN {admin_id} deleted {time} slot. Reason: {reason}")
                
            conn.commit()

        if action == "APPROVE_PENDING":
            return self._resolve_pending(cmd.get("request_id"), cmd.get("approved", False), admin_id)
            
        return {"status": "success"}

    def _queue_request(self, cmd: dict) -> dict:
        """Writes the pending request to the database instead of memory."""
        with sqlite3.connect(self._db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO pending_requests (action, date, time, member_id, target_member, task, reason)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                cmd.get("action"), cmd.get("date"), cmd.get("time"), 
                cmd.get("member_id"), cmd.get("target_member", cmd["member_id"]), 
                cmd.get("task", "Task"), cmd.get("reason", "")
            ))
            request_id = cursor.lastrowid
            conn.commit()
            
        return {"status": "pending", "request_id": request_id}

    def _resolve_pending(self, req_id: int, approved: bool, admin_id: str) -> dict:
        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # 1. Find the request in the DB
            cursor.execute("SELECT * FROM pending_requests WHERE request_id=?", (req_id,))
            req_row = cursor.fetchone()
            
            if not req_row: 
                return {"status": "error", "msg": "Request not found"}
            
            req = dict(req_row)
            
            # 2. Delete it from the pending queue
            cursor.execute("DELETE FROM pending_requests WHERE request_id=?", (req_id,))
            
            # 3. Apply it to the slots if approved
            if approved:
                action = req.get("action")
                if action in ["ADD", "OVERWRITE"]:
                    cursor.execute(
                        "REPLACE INTO slots (date, time, member_id, task) VALUES (?, ?, ?, ?)",
                        (req["date"], req["time"], req["member_id"], req.get("task", "Task"))
                    )
                elif action in ["REMOVE", "ADMIN_REMOVE"]:
                    cursor.execute("DELETE FROM slots WHERE date=? AND time=?", (req["date"], req["time"]))
                
                print(f"[AUDIT LOG] ADMIN {admin_id} Approved Req {req_id} ({action}) at {req['time']}. Reason: {req.get('reason')}")
            
            conn.commit()
            
        return {"status": "success"}