import json
from typing import Dict, Optional, List

class TimetableService:
    def __init__(self):
        # The Core Store: { "date": { "time": { "member_id": str, "task": str } } }
        self._grid: Dict[str, Dict[str, Optional[dict]]] = {}
        self._pending_requests: List[dict] = []
        self._request_id_counter = 1

    # --- CORE DATA OPERATIONS ---

    def initialize_day(self, date: str, slots: list):
        if date not in self._grid:
            self._grid[date] = {slot: None for slot in slots}

    def get_full_state(self) -> dict:
        """Returns the current state for syncing new clients."""
        return self._grid

    # --- TRANSACTION LOGIC (The "Engine") ---

    def process_command(self, command: dict) -> dict:
        """
        The entry point for all incoming JSON/Dictionary commands.
        Example command: {"action": "ADD", "member_id": "123", "date": "...", "time": "..."}
        """
        action = command.get("action")
        member_id = command.get("member_id")
        
        # 1. Admin bypass (ID 000)
        if member_id == "000":
            return self._execute_admin_command(command)
        
        # 2. Member logic (Must go to queue)
        return self._queue_request(command)

    def _execute_admin_command(self, cmd: dict) -> dict:
        """Internal: Admin executes changes immediately."""
        action = cmd.get("action")
        date, time = cmd.get("date"), cmd.get("time")

        if action == "ADD":
            # Admin forces the update (overwrites if necessary)
            self._grid[date][time] = {"member_id": cmd["target_member"], "task": cmd["task"]}
            return {"status": "success", "msg": "Admin applied change"}
        
        elif action == "REMOVE":
            self._grid[date][time] = None
            return {"status": "success", "msg": "Admin cleared slot"}
        
        elif action == "APPROVE_PENDING":
            return self._resolve_pending(cmd.get("request_id"), approved=True)
            
        return {"status": "error", "msg": "Unknown admin action"}

    def _queue_request(self, cmd: dict) -> dict:
        """Internal: Non-admin requests are stored for review."""
        cmd["request_id"] = self._request_id_counter
        self._pending_requests.append(cmd)
        self._request_id_counter += 1
        return {"status": "pending", "request_id": cmd["request_id"]}

    def _resolve_pending(self, req_id: int, approved: bool) -> dict:
        """Executes a queued request if admin approves."""
        req = next((r for r in self._pending_requests if r["request_id"] == req_id), None)
        if not req:
            return {"status": "error", "msg": "Request not found"}

        self._pending_requests.remove(req)
        if approved:
            # Force the move into the grid
            self._grid[req["date"]][req["time"]] = {
                "member_id": req["member_id"], 
                "task": req.get("task", "Task")
            }
            return {"status": "success", "applied_req": req_id}
        
        return {"status": "rejected", "applied_req": req_id}

    def get_pending(self) -> list:
        return self._pending_requests