// --- 1. CONFIGURATION ---
const HOST = window.location.hostname;
const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
const WS_URL = `${wsProtocol}//${HOST}:8001/ws`;        // Points to the isolated WS Gateway
const API_URL = `http://${HOST}:8002/api/command`;      // Points to the REST API Backend

const TARGET_DATE = "2026-04-07";
let currentUser = { id: null, role: 'GUEST' };

// --- 2. AUTHENTICATION & WEBSOCKET SETUP ---
const socket = new WebSocket(WS_URL);

socket.onopen = () => authenticate();
socket.onmessage = (event) => {
    const data = JSON.parse(event.data);
    renderGrid(data.grid[TARGET_DATE]);
    if (currentUser.role === "ADMIN") renderAdminQueue(data.pending);
};
socket.onclose = () => console.warn("Live connection lost.");

function authenticate() {
    const id = prompt("Enter Account ID (admin_1, user_alice, user_bob):");
    if (!id) return authenticate(); 
    
    currentUser.id = id;
    currentUser.role = (id.startsWith("admin")) ? "ADMIN" : "MEMBER";
    document.getElementById('user-display').innerText = `User: ${id} (${currentUser.role})`;
    if (currentUser.role === "ADMIN") document.getElementById('admin-nav').style.display = "block";
}

// --- 3. REST API COMMUNICATION ---
function sendCommandToAPI(payload) {
    fetch(API_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
    }).catch(err => console.error("API Error:", err));
}

// --- 4. DOM EVENT HANDLERS (Exposed globally for HTML buttons) ---
window.handleClick = function(time, isOccupied) {
    let action = "ADD";
    if (isOccupied) {
        const choice = prompt("Type 'O' to Overwrite or 'D' to Delete.");
        if (!choice) return;
        action = choice.toUpperCase() === 'O' ? "OVERWRITE" : "REMOVE";
    }

    if (currentUser.role === "ADMIN" && action === "REMOVE") action = "ADMIN_REMOVE";
    
    let task = (action !== "REMOVE" && action !== "ADMIN_REMOVE") ? prompt("Enter Task:") : "";
    if (action !== "REMOVE" && action !== "ADMIN_REMOVE" && !task) return;
    
    let reason = prompt("Why are you doing this?");
    if (!reason) return;

    sendCommandToAPI({ action, member_id: currentUser.id, target_member: currentUser.id, date: TARGET_DATE, time, task, reason });
};

window.processApproval = function(reqId, approved) {
    sendCommandToAPI({ action: "APPROVE_PENDING", member_id: currentUser.id, request_id: reqId, approved });
};

// --- 5. DOM RENDERING ---
function renderGrid(dayData) {
    const container = document.getElementById('timetable-container');
    container.innerHTML = "";
    for (const [time, slot] of Object.entries(dayData)) {
        const isOccupied = slot !== null;
        const text = isOccupied ? `${slot.member_id}: ${slot.task}` : "[ Empty Slot ]";
        let btnClass = isOccupied ? (slot.member_id.startsWith("admin") ? "btn-warning" : "btn-info") : "btn-outline-secondary";

        container.innerHTML += `
            <div class="d-flex align-items-center mb-2">
                <div class="fw-bold me-3" style="width: 70px;">${time}</div>
                <button class="btn ${btnClass} w-100 text-start slot-btn p-3" onclick="handleClick('${time}', ${isOccupied})">${text}</button>
            </div>`;
    }
}

function renderAdminQueue(pending) {
    const list = document.getElementById('pending-list');
    document.getElementById('badge').innerText = pending.length;
    list.innerHTML = "";
    document.getElementById('empty-msg').style.display = pending.length === 0 ? "block" : "none";

    pending.forEach(req => {
        list.innerHTML += `
            <div class="list-group-item list-group-item-action mb-2 border rounded">
                <div class="d-flex justify-content-between align-items-center">
                    <h6 class="mb-1 text-primary">${req.action}</h6>
                    <div class="btn-group">
                        <button class="btn btn-sm btn-success" onclick="processApproval(${req.request_id}, true)">Approve</button>
                        <button class="btn btn-sm btn-danger" onclick="processApproval(${req.request_id}, false)">Reject</button>
                    </div>
                </div>
                <small><b>User:</b> ${req.member_id} | <b>Time:</b> ${req.time}</small><br>
                <small class="text-muted"><b>Reason:</b> ${req.reason}</small>
            </div>`;
    });
}