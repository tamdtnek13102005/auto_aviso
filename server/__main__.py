"""Chạy Server: python -m server.main"""
import uvicorn
from . import print_api_info, SERVER_HOST, SERVER_PORT
from .main import app

if __name__ == "__main__":
    print_api_info()
    uvicorn.run(app, host=SERVER_HOST, port=SERVER_PORT)
