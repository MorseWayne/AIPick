import os
import asyncio
import logging
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import uvicorn
from pydantic import BaseModel
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

@app.get("/")
async def get_index():
    return FileResponse("static/index.html")

class WebSocketCallback:
    def __init__(self, websocket: WebSocket):
        self.ws = websocket
        self.loop = asyncio.get_running_loop()
        self.input_queue = asyncio.Queue()
        self.md_path = ""
        
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
        self._send({
            "type": "completed", 
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
    callback = WebSocketCallback(websocket)
    
    mcp_url = os.getenv("XHS_MCP_URL", "http://10.10.131.118:18060/mcp")
    agent = RecommendationAgent(mcp_url=mcp_url)
    
    pipeline_task = None
    
    while True:
        try:
            data = await websocket.receive_json()
            msg_type = data.get("type")
            
            if msg_type == "query":
                # Cancel previous pipeline if any
                if pipeline_task and not pipeline_task.done():
                    pipeline_task.cancel()
                
                async def run_agent():
                    try:
                        await agent.run_pipeline(data.get("content"), callback=callback)
                        await websocket.send_json({"type": "pipeline_end"})
                    except asyncio.CancelledError:
                        logger.info("Pipeline cancelled.")
                    except Exception as e:
                        logger.exception("Pipeline error")
                        await websocket.send_json({"type": "error", "message": str(e)})
                        
                pipeline_task = asyncio.create_task(run_agent())
                
            elif msg_type == "answer":
                await callback.input_queue.put(data.get("content"))
                
        except WebSocketDisconnect:
            logger.info("Client disconnected")
            if pipeline_task and not pipeline_task.done():
                pipeline_task.cancel()
            break

if __name__ == "__main__":
    uvicorn.run("web:app", host="0.0.0.0", port=8000, reload=True)
