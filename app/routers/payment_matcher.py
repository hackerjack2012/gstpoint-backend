from fastapi import APIRouter, UploadFile, File, Form
from fastapi.responses import FileResponse

from app.services.payment_matcher_service import process_payment_matcher

router = APIRouter(
    prefix="/payment-matcher",
    tags=["Payment Matcher"]
)


@router.post("/")
async def payment_matcher(
    file: UploadFile = File(...),
    ledger_type: str = Form(...),
    delay_threshold: int = Form(...),
    gst_rate: float = Form(...)
):

    output_file = process_payment_matcher(
        file,
        ledger_type,
        delay_threshold,
        gst_rate
    )

    return FileResponse(
        output_file,
        filename="MatchedFIFO.xlsx"
    )