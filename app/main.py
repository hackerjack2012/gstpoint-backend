from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers.payment_matcher import router as payment_router
from app.routers.gst_bulk_search import router as bulk_search_router


# ============================================================
# FastAPI Application
# ============================================================

app = FastAPI(
    title="GSTPoint API",
    version="1.0.0",
    description="Backend API for GSTPoint Tools",
)


# ============================================================
# CORS Configuration
# ============================================================

# Production frontend + local development environments.
#
# allow_origin_regex also permits Vercel preview deployments such as:
# https://gstpoint-tools-xxxxx.vercel.app

app.add_middleware(
    CORSMiddleware,

    allow_origins=[
        "https://gstpoint-tools.vercel.app",

        # Local development
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

    # Allow Vercel preview deployments
    allow_origin_regex=r"https://.*\.vercel\.app",

    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# Routers
# ============================================================

app.include_router(payment_router)
app.include_router(bulk_search_router)


# ============================================================
# Health Check
# ============================================================

@app.get("/")
def root():
    return {
        "status": "running",
        "application": "GSTPoint API",
        "version": "1.0.0",
        "endpoints": {
            "/": "GET - Health check",
            "/payment-matcher/": "POST - Process Excel file for payment matching",
        },
    }