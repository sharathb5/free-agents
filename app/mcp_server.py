import os

import httpx
from fastapi import FastAPI, HTTPException, Request

app = FastAPI(title="Free Agents MCP Server")

FREE_AGENTS_BASE = os.getenv("FREE_AGENTS_BASE", "http://localhost:4280").rstrip("/")
UPSTREAM_TIMEOUT = httpx.Timeout(30.0, connect=5.0)


@app.get("/")
async def health_check():
    return {"status": "ok"}


@app.get("/tools")
async def list_tools():
    try:
        async with httpx.AsyncClient(timeout=UPSTREAM_TIMEOUT) as client:
            response = await client.get(f"{FREE_AGENTS_BASE}/agents")
            response.raise_for_status()
            payload = response.json()
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Upstream Free Agents API timed out")
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Upstream Free Agents API error: {exc.response.status_code}",
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Upstream Free Agents API request failed: {exc}")

    if isinstance(payload, dict):
        agents = payload.get("agents", [])
    elif isinstance(payload, list):
        agents = payload
    else:
        agents = []

    tools = []
    for agent in agents:
        if isinstance(agent, str):
            tools.append({
                "name": agent,
                "description": "",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The input query to send to the agent"
                        }
                    },
                    "required": ["query"]
                }
            })
            continue
        if not isinstance(agent, dict):
            continue
        tools.append({
            "name": agent.get("id") or agent.get("agent_id") or agent.get("name", ""),
            "description": agent.get("description") or agent.get("prompt", ""),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The input query to send to the agent"
                    }
                },
                "required": ["query"]
            }
        })

    return tools


@app.post("/tools/{agent_id}")
async def invoke_tool(agent_id: str, request: Request):
    body = await request.json()
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=5.0)) as client:
            response = await client.post(
                f"{FREE_AGENTS_BASE}/agents/{agent_id}/invoke",
                json=body
            )
            if response.status_code == 404:
                raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")
            response.raise_for_status()
            return response.json()
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Upstream Free Agents API timed out")
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Upstream Free Agents API error: {exc.response.status_code}",
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Upstream Free Agents API request failed: {exc}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=4281)
