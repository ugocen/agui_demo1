"""Minimal A2A client — discovers the agent via its Agent Card, then calls it.

  1. Start the server:  python server.py            (listens on :9000)
  2. Call it:           python client.py "add SSO login"

Demonstrates the two halves of A2A: discovery (Agent Card at the well-known URL)
and invocation (JSON-RPC 2.0 `message/send` to the url from the card).
"""

import sys
import uuid

import httpx

BASE = "http://localhost:9000"


def main() -> None:
    prompt = " ".join(sys.argv[1:]) or "add Microsoft SSO login to the web app"

    # 1. Discovery — fetch the Agent Card from the well-known URL.
    card = httpx.get(f"{BASE}/.well-known/agent-card.json", timeout=10).json()
    print(f"Discovered agent: {card['name']} v{card['version']}")
    print(f"  {card['description']}")
    print("  skills:", ", ".join(s["id"] for s in card.get("skills", [])))
    endpoint = card["url"]

    # 2. Invocation — JSON-RPC 2.0 `message/send` to the agent's url.
    rpc = {
        "jsonrpc": "2.0",
        "id": str(uuid.uuid4()),
        "method": "message/send",
        "params": {
            "message": {
                "role": "user",
                "parts": [{"kind": "text", "text": prompt}],
                "messageId": str(uuid.uuid4()),
                "kind": "message",
            }
        },
    }
    print(f"\n> {prompt}\n")
    resp = httpx.post(endpoint, json=rpc, timeout=30).json()

    if "error" in resp:
        print("A2A error:", resp["error"])
        return
    for part in resp["result"].get("parts", []):
        if part.get("kind") == "text":
            print(part["text"])


if __name__ == "__main__":
    main()
