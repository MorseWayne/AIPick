import os
import asyncio
import logging
import json
import time
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import uvicorn
from pydantic import BaseModel
from typing import List, Optional
from dotenv import load_dotenv

from src.agent import RecommendationAgent
from src.models import SearchIntent, WebSearchReport, RecommendationReport

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# Make sure static and output directories exist
os.makedirs("static", exist_ok=True)
os.makedirs("output", exist_ok=True)

app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/output", StaticFiles(directory="output"), name="output")

HISTORY_FILE = "history.json"

class SessionEntry(BaseModel):
    id: str
    query: str
    timestamp: float
    md_path: str
    intent: Optional[dict] = None
    final_report: Optional[dict] = None

def load_history() -> List[SessionEntry]:
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return [SessionEntry(**item) for item in data]
    except Exception as e:
        logger.error(f"Error loading history: {e}")
        return []

def save_history(history: List[SessionEntry]):
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump([item.model_dump() for item in history], f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Error saving history: {e}")

@app.get("/")
async def get_index():
    return FileResponse("static/index.html")

@app.get("/api/history")
async def get_history():
    history = load_history()
    # Sort by timestamp descending
    history.sort(key=lambda x: x.timestamp, reverse=True)
    return history

@app.get("/api/session/{session_id}")
async def get_session(session_id: str):
    history = load_history()
    session = next((s for s in history if s.id == session_id), None)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Read the markdown file if it exists
    content = ""
    if os.path.exists(session.md_path):
        with open(session.md_path, "r", encoding="utf-8") as f:
            content = f.read()
    
    return {
        "session": session,
        "content": content
    }

class WebSocketCallback:
    def __init__(self, websocket: WebSocket, initial_query: str):
        self.ws = websocket
        self.loop = asyncio.get_running_loop()
        self.input_queue = asyncio.Queue()
        self.md_path = ""
        self.initial_query = initial_query
        
    def _send(self, data: dict):
        self.loop.create_task(self.ws.send_json(data))

    def on_status_update(self, stage: str, message: str) -> None:
        self._send({"type": "status", "stage": stage, "message": message})

    def on_info(self, message: str) -> None:
        if message.startswith("\n📄 推荐清单已保存到: "):
            self.md_path = message.replace("\n📄 推荐清单已保存到: ", "").strip()
            self._send({"type": "md_path", "path": self.md_path})
        self._send({"type": "info", "message": message})

    def on_warning(self, message: str) -> None:
        self._send({"type": "warning", "message": message})

    def on_question_asked(self, question: str, reason: str) -> None:
        self._send({"type": "question", "question": question, "reason": reason})

    def on_intent_confirmed(self, intent: SearchIntent) -> None:
        self._send({"type": "intent", "data": intent.model_dump()})

    def on_recommendation_completed(self, intent: SearchIntent, web_report: WebSearchReport, final_report: RecommendationReport) -> None:
        # Save to history
        session_id = str(int(time.time()))
        new_entry = SessionEntry(
            id=session_id,
            query=self.initial_query,
            timestamp=time.time(),
            md_path=self.md_path,
            intent=intent.model_dump(),
            final_report=final_report.model_dump()
        )
        history = load_history()
        history.append(new_entry)
        save_history(history)

        self._send({
            "type": "completed", 
            "session_id": session_id,
            "intent": intent.model_dump(),
            "web_report": web_report.model_dump(),
            "final_report": final_report.model_dump(),
            "md_path": self.md_path
        })

    async def request_user_input(self, prompt: str) -> str:
        self._send({"type": "request_input", "prompt": prompt})
        answer = await self.input_queue.get()
        return answer

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    
    mcp_url = os.getenv("XHS_MCP_URL", "http://10.10.131.118:18060/mcp")
    agent = RecommendationAgent(mcp_url=mcp_url)
    
    pipeline_task = None
    callback = None
    
    while True:
        try:
            data = await websocket.receive_json()
            msg_type = data.get("type")
            
            if msg_type == "query":
                query_content = data.get("content")
                callback = WebSocketCallback(websocket, query_content)
                # Cancel previous pipeline if any
                if pipeline_task and not pipeline_task.done():
                    pipeline_task.cancel()
                
                async def run_agent():
                    try:
                        await agent.run_pipeline(query_content, callback=callback)
                        await websocket.send_json({"type": "pipeline_end"})
                    except asyncio.CancelledError:
                        logger.info("Pipeline cancelled.")
                    except Exception as e:
                        logger.exception("Pipeline error")
                        await websocket.send_json({"type": "error", "message": str(e)})
                        
                pipeline_task = asyncio.create_task(run_agent())
                
            elif msg_type == "answer":
                if callback:
                    await callback.input_queue.put(data.get("content"))
                
        except WebSocketDisconnect:
            logger.info("Client disconnected")
            if pipeline_task and not pipeline_task.done():
                pipeline_task.cancel()
            break

if __name__ == "__main__":
    uvicorn.run("web:app", host="0.0.0.0", port=8000, reload=True)
