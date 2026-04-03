"""Chạy Local Agent: python -m local.agent"""
import uvicorn
from .agent import app

if __name__ == "__main__":
    print("=" * 50)
    print("🚀 AUTO AVISO - LOCAL AGENT")
    print("=" * 50)
    print("📡 Server:   http://0.0.0.0:8000")
    print("📖 API Docs: http://localhost:8000/docs")
    print("=" * 50)
    uvicorn.run(app, host="0.0.0.0", port=8000)
