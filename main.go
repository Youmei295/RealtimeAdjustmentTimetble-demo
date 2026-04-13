package main

import (
	"database/sql"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"sync"

	"github.com/gorilla/websocket"
	_ "modernc.org/sqlite" // Pure Go SQLite driver
)

// --- CONFIGURATION ---
const TargetDate = "2026-04-07"

var timeSlots = []string{"09:00", "10:00", "11:00", "12:00", "13:00", "14:00"}

// --- DATA STRUCTURES (Strict Typing) ---
type Slot struct {
	MemberID string `json:"member_id"`
	Task     string `json:"task"`
}

type PendingReq struct {
	RequestID    int    `json:"request_id"`
	Action       string `json:"action"`
	Date         string `json:"date"`
	Time         string `json:"time"`
	MemberID     string `json:"member_id"`
	TargetMember string `json:"target_member"`
	Task         string `json:"task"`
	Reason       string `json:"reason"`
}

// The payload sent to the frontend
type BroadcastMessage struct {
	Grid    map[string]map[string]*Slot `json:"grid"` // Pointer allows for 'null' in JSON
	Pending []PendingReq                `json:"pending"`
}

// --- GLOBAL STATE & MUTEX (Thread Safety) ---
var (
	// In Go, we must explicitly lock memory when multiple threads (Goroutines) access it
	clients   = make(map[*websocket.Conn]bool)
	clientsMu sync.Mutex
	db        *sql.DB

	// Upgrades standard HTTP to a WebSocket connection
	upgrader = websocket.Upgrader{
		CheckOrigin: func(r *http.Request) bool { return true }, // Allow all CORS
	}
)

func main() {
	var err error
	// Open connection to your existing SQLite database
	db, err = sql.Open("sqlite", "./timetable.db")
	if err != nil {
		log.Fatal("Failed to open database:", err)
	}
	defer db.Close() // Automatically close when main() exits

	// Define endpoints
	http.HandleFunc("/ws", handleConnections)
	http.HandleFunc("/internal/broadcast", handleWebhook)

	fmt.Println("Starting Go WebSocket Gateway on ws://0.0.0.0:8001")
	log.Fatal(http.ListenAndServe(":8001", nil))
}

// --- ENDPOINT: WEBSOCKET MANAGER ---
func handleConnections(w http.ResponseWriter, r *http.Request) {
	// Upgrade GET request to a WebSocket
	ws, err := upgrader.Upgrade(w, r, nil)
	if err != nil {
		log.Println("Upgrade error:", err)
		return
	}
	defer ws.Close()

	// Lock mutex, add to map, unlock (C++ style thread safety!)
	clientsMu.Lock()
	clients[ws] = true
	clientsMu.Unlock()

	fmt.Printf("[NETWORK] Client connected. Total: %d\n", len(clients))

	// Send initial data immediately upon connection
	broadcastState()

	// Keep the connection alive and listen for disconnects
	for {
		_, _, err := ws.ReadMessage()
		if err != nil {
			clientsMu.Lock()
			delete(clients, ws)
			clientsMu.Unlock()
			fmt.Println("[NETWORK] Client disconnected.")
			break
		}
	}
}

// --- ENDPOINT: INTERNAL WEBHOOK ---
func handleWebhook(w http.ResponseWriter, r *http.Request) {
	// Add CORS headers for the HTTP response
	w.Header().Set("Access-Control-Allow-Origin", "*")
	if r.Method == http.MethodOptions {
		return // Handle preflight
	}

	fmt.Println("[WEBHOOK] Signal received from API! Broadcasting to WebSockets...")
	broadcastState()

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]string{"status": "broadcast_triggered"})
}

// --- CORE LOGIC: FETCH DB & BROADCAST ---
func broadcastState() {
	// 1. Initialize empty grid (matching Python's structure)
	dayGrid := make(map[string]*Slot)
	for _, t := range timeSlots {
		dayGrid[t] = nil
	}

	// 2. Fetch Active Slots from SQLite
	rows, _ := db.Query("SELECT time, member_id, task FROM slots WHERE date=?", TargetDate)
	defer rows.Close()
	for rows.Next() {
		var timeStr, memberID, task string
		rows.Scan(&timeStr, &memberID, &task)
		// Point to a new Slot struct in memory
		dayGrid[timeStr] = &Slot{MemberID: memberID, Task: task}
	}

	// 3. Fetch Pending Requests from SQLite
	pending := []PendingReq{}
	pRows, _ := db.Query("SELECT request_id, action, date, time, member_id, target_member, task, reason FROM pending_requests")
	defer pRows.Close()
	for pRows.Next() {
		var req PendingReq
		pRows.Scan(&req.RequestID, &req.Action, &req.Date, &req.Time, &req.MemberID, &req.TargetMember, &req.Task, &req.Reason)
		pending = append(pending, req)
	}

	// 4. Construct JSON Payload
	msg := BroadcastMessage{
		Grid:    map[string]map[string]*Slot{TargetDate: dayGrid},
		Pending: pending,
	}

	// 5. Broadcast to all active Goroutine connections safely
	clientsMu.Lock()
	defer clientsMu.Unlock()
	for client := range clients {
		err := client.WriteJSON(msg)
		if err != nil {
			client.Close()
			delete(clients, client)
		}
	}
}
