/** WebSocket client with auto-reconnect and JWT auth (CRKY-13). */

export interface WSMessage {
	type: string;
	data: Record<string, unknown>;
}

type MessageHandler = (msg: WSMessage) => void;

let socket: WebSocket | null = null;
let handlers: MessageHandler[] = [];
let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
let intentionallyClosed = false;

function getWsUrl(): string {
	const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
	let url = `${proto}//${window.location.host}/ws`;

	// Append JWT token if available (required when auth is enabled)
	const token = localStorage.getItem('ck:auth_token');
	if (token) {
		url += `?token=${encodeURIComponent(token)}`;
	}
	return url;
}

function doConnect() {
	if (socket?.readyState === WebSocket.OPEN || socket?.readyState === WebSocket.CONNECTING) {
		return;
	}

	socket = new WebSocket(getWsUrl());

	socket.onopen = () => {
		if (reconnectTimer) {
			clearTimeout(reconnectTimer);
			reconnectTimer = null;
		}
	};

	socket.onmessage = (event) => {
		try {
			const msg: WSMessage = JSON.parse(event.data);
			for (const handler of handlers) {
				handler(msg);
			}
		} catch {
			// ignore malformed messages
		}
	};

	socket.onclose = () => {
		socket = null;
		if (!intentionallyClosed) {
			reconnectTimer = setTimeout(doConnect, 2000);
		}
	};

	socket.onerror = () => {
		socket?.close();
	};
}

export function connect() {
	intentionallyClosed = false;
	doConnect();
}

export function disconnect() {
	intentionallyClosed = true;
	if (reconnectTimer) {
		clearTimeout(reconnectTimer);
		reconnectTimer = null;
	}
	socket?.close();
	socket = null;
}

export function onMessage(handler: MessageHandler): () => void {
	handlers.push(handler);
	return () => {
		handlers = handlers.filter((h) => h !== handler);
	};
}

export function isConnected(): boolean {
	return socket?.readyState === WebSocket.OPEN;
}
