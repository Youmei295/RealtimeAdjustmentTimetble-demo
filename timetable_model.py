import json
from typing import Dict, Optional, List

class TimetableService:
    def __init__(self):
        # The Core Store: { "date": { "time": { "member_id": str, "task": str } } }
        self._grid: Dict[str, Dict[str, Optional[dict]]] = {}
        self._pending_requests: List[dict] = []
        self._request_id_counter = 1
        
        # --- NEW: Account Role Registry (RBAC) ---
        self._accounts = {
            "admin_1": {"role": "ADMIN", "name": "System Admin"},
            "user_alice": {"role": "MEMBER", "name": "Alice"},
            "user_bob": {"role": "MEMBER", "name": "Bob"}
        }

    # --- CORE DATA OPERATIONS ---

    def get_user_info(self, user_id: str) -> Optional[dict]:
        """Fetch user identity from the database."""
        return self._accounts.get(user_id)

    def initialize_day(self, date: str, slots: list):
        if date not in self._grid:
            self._grid[date] = {slot: None for slot in slots}

    def get_full_state(self) -> dict:
        return self._grid

    def get_pending(self) -> list:
        return self._pending_requests

    # --- TRANSACTION LOGIC (The JSON Router) ---

    def process_command(self, command: dict) -> dict:
        """
        The entry point for all incoming JSON payloads.
        Verifies account existence and role before routing.
        """
        user_id = command.get("member_id")
        user_info = self.get_user_info(user_id)
        
        # 1. Reject unknown users immediately
        if not user_info:
            print(f"[SECURITY] Blocked unknown user ID: {user_id}")
            return {"status": "error", "msg": "Access Denied: Invalid Account"}
            
        role = user_info["role"]
        
        # 2. Route based on verified Role
        if role == "ADMIN":
            return self._execute_admin_command(command)
        else:
            return self._queue_request(command)

    def _execute_admin_command(self, cmd: dict) -> dict:
        """Internal: Admin executes changes immediately."""
        action = cmd.get("action")
        date, time = cmd.get("date"), cmd.get("time")
        reason = cmd.get("reason", "No reason provided")
        admin_id = cmd.get("member_id")

        if action in ["ADD", "OVERWRITE"]:
            self._grid[date][time] = {"member_id": cmd.get("target_member", admin_id), "task": cmd.get("task", "Task")}
            print(f"[AUDIT LOG] ADMIN {admin_id} executed {action} at {time}. Reason: {reason}")
            return {"status": "success", "msg": f"Admin applied {action}"}
        
        elif action in ["REMOVE", "ADMIN_REMOVE"]:
            self._grid[date][time] = None
            print(f"[AUDIT LOG] ADMIN {admin_id} deleted {time} slot. Reason: {reason}")
            return {"status": "success", "msg": "Admin cleared slot"}
        
        elif action == "APPROVE_PENDING":
            return self._resolve_pending(cmd.get("request_id"), cmd.get("approved", False), admin_id)
            
        return {"status": "error", "msg": "Unknown admin action"}

    def _queue_request(self, cmd: dict) -> dict:
        """Internal: Non-admin requests are stored for review."""
        cmd["request_id"] = self._request_id_counter
        self._pending_requests.append(cmd)
        self._request_id_counter += 1
        return {"status": "pending", "request_id": cmd["request_id"]}

    def _resolve_pending(self, req_id: int, approved: bool, admin_id: str) -> dict:
        """Executes a queued request if admin approves."""
        req = next((r for r in self._pending_requests if r["request_id"] == req_id), None)
        if not req:
            return {"status": "error", "msg": "Request not found"}

        self._pending_requests.remove(req)
        
        if approved:
            action = req.get("action")
            reason = req.get("reason", "No reason provided")
            
            if action in ["ADD", "OVERWRITE"]:
                self._grid[req["date"]][req["time"]] = {
                    "member_id": req["member_id"], 
                    "task": req.get("task", "Task")
                }
                print(f"[AUDIT LOG] ADMIN {admin_id} Approved Request {req_id} ({action}) at {req['time']}. Reason: {reason}")
                
            elif action in ["REMOVE", "ADMIN_REMOVE"]:
                self._grid[req["date"]][req["time"]] = None
                print(f"[AUDIT LOG] ADMIN {admin_id} Approved Request {req_id} removed {req['time']}. Reason: {reason}")
                
            return {"status": "success", "applied_req": req_id}
        
        return {"status": "rejected", "applied_req": req_id}