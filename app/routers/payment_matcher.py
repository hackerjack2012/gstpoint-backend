from fastapi import APIRouter, UploadFile, File, Form, BackgroundTasks
from fastapi.responses import FileResponse
import os

from app.services.payment_matcher_service import process_payment_matcher

router = APIRouter(
    prefix="/payment-matcher",
    tags=["Payment Matcher"]
)


@router.post("/")
async def payment_matcher(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    ledger_type: str = Form(...),
    delay_threshold: int = Form(...),
    gst_rate: float = Form(...)
):
    if delay_threshold < 0:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Delay threshold must be non-negative.")
    if gst_rate <= 0:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="GST rate must be greater than zero.")

    input_path, output_path = process_payment_matcher(
        file,
        ledger_type,
        delay_threshold,
        gst_rate
    )

    def cleanup_files():
        for path in [input_path, output_path]:
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except Exception:
                    pass

    background_tasks.add_task(cleanup_files)

    return FileResponse(
        output_path,
        filename="MatchedFIFO.xlsx"
    )