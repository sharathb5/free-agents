from fastapi import FastAPI, HTTPException, Request
import httpx

app = FastAPI(title="Free Agents MCP Server")

FREE_AGENTS_BASE = "https://free-agents.onrender.com"


@app.get("/")
async def health_check():
    return {"status": "ok"}


@app.get("/tools")
async def list_tools():
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{FREE_AGENTS_BASE}/agents")
        response.raise_for_status()
        agents = response.json()

    tools = []
    for agent in agents:
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
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            f"{FREE_AGENTS_BASE}/agents/{agent_id}/invoke",
            json=body
        )
        if response.status_code == 404:
            raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")
        response.raise_for_status()
        return response.json()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=4281)
