package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"log"
	"net"
	"os"
)

// mt5-pp-cli: Out-of-GIL Go Order Transaction Layer
// Communicates with MT5 via a decoupled TCP Socket Bridge (mt5_socket_bridge.py).

type IPCRequest struct {
	Command string  `json:"command"`
	Symbol  string  `json:"symbol"`
	Size    float64 `json:"size"`
	SL      float64 `json:"sl"`
	TP      float64 `json:"tp"`
	Ticket  int     `json:"ticket"`
}

type IPCResponse struct {
	Status  string `json:"status"`
	Message string `json:"message"`
}

func main() {
	symbol := flag.String("symbol", "", "Target asset symbol")
	size := flag.Float64("size", 0.0, "Lot size")
	sl := flag.Float64("sl", 0.0, "Stop loss price")
	tp := flag.Float64("tp", 0.0, "Take profit price")
	ticket := flag.Int("ticket", 0, "Position ticket ID")

	flag.Parse()
	args := flag.Args()

	if len(args) < 1 {
		log.Fatalf("FATAL: Missing command argument. Expected: buy, sell, modify, cancel")
	}

	req := IPCRequest{
		Command: args[0],
		Symbol:  *symbol,
		Size:    *size,
		SL:      *sl,
		TP:      *tp,
		Ticket:  *ticket,
	}

	payload, err := json.Marshal(req)
	if err != nil {
		log.Fatalf("FATAL: JSON encoding failed: %v", err)
	}

	conn, err := net.Dial("tcp", "127.0.0.1:15555")
	if err != nil {
		log.Fatalf("FATAL: Cannot connect to MT5 Socket Bridge: %v", err)
	}
	defer conn.Close()

	_, err = conn.Write(payload)
	if err != nil {
		log.Fatalf("FATAL: Failed to send IPC payload: %v", err)
	}

	buffer := make([]byte, 4096)
	n, err := conn.Read(buffer)
	if err != nil {
		log.Fatalf("FATAL: Failed to read IPC response: %v", err)
	}

	var res IPCResponse
	err = json.Unmarshal(buffer[:n], &res)
	if err != nil {
		log.Fatalf("FATAL: Invalid IPC response JSON: %v", err)
	}

	if res.Status == "success" {
		fmt.Printf("%s\n", res.Message)
		os.Exit(0)
	} else {
		fmt.Printf("ERROR: %s\n", res.Message)
		os.Exit(1)
	}
}
