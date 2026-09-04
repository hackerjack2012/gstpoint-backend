from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers.payment_matcher import router as payment_router

app = FastAPI(title="GSTPoint API")

# Allow all localhost ports for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://gstpoint-tools.vercel.app",
        "http://localhost:3000",
        "http://localhost:3001",
        "http://localhost:3002",
        "http://localhost:3003",
        "http://localhost:3004",
        "http://localhost:3005",
        "http://localhost:4000",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
        "http://127.0.0.1:3002",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(payment_router)


@app.get("/")
def root():
    return {
        "status": "running",
        "application": "GSTPoint API",
        "version": "1.0.0",
        "endpoints": {
            "/": "Health check",
            "/payment-matcher/": "POST - Process Excel file for payment matching",
        }
    }
