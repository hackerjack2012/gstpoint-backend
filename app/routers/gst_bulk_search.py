from fastapi import APIRouter, UploadFile, File, Form, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse
import os
import tempfile
import pandas as pd
from typing import List

from app.engines.gst_client import GSTClient
from app.engines.excel_handler import (
    save_taxpayer_records,
    save_return_records
)

router = APIRouter(
    prefix="/gst-bulk-search",
    tags=["GST Bulk Search"]
)

def is_valid_gstin(value):
    import re
    value = str(value or "").strip().upper()
    return bool(re.fullmatch(
        r"[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][0-9A-Z]Z[0-9A-Z]", value
    ))

@router.post("/")
async def gst_bulk_search(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(None),
    gstins_text: str = Form(None),
    search_mode: str = Form("taxpayer"),
    financial_year: str = Form("2024-25"),
    month: str = Form("All"),
    return_type: str = Form("Both")
):
    gstins = []

    if file is not None:
        content = await file.read()
        temp_in = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
        temp_in.write(content)
        temp_in.close()
        try:
            if file.filename.endswith(".csv"):
                df = pd.read_csv(temp_in.name, header=None)
            else:
                df = pd.read_excel(temp_in.name, header=None)
            for col in df.columns:
                for val in df[col].dropna().astype(str):
                    val_clean = val.strip().upper()
                    if is_valid_gstin(val_clean):
                        gstins.append(val_clean)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to read uploaded file: {str(e)}")
        finally:
            if os.path.exists(temp_in.name):
                os.remove(temp_in.name)

    if gstins_text:
        for line in gstins_text.splitlines():
            val_clean = line.strip().upper()
            if is_valid_gstin(val_clean):
                gstins.append(val_clean)

    gstins = list(dict.fromkeys(gstins)) # remove duplicates

    if not gstins:
        raise HTTPException(status_code=400, detail="No valid GSTINs provided.")

    output_dir = "app/temp"
    os.makedirs(output_dir, exist_ok=True)

    try:
        model_path = os.path.join("app", "engines", "captcha_model.onnx")
        client = GSTClient(model_path=model_path)

        if search_mode == "taxpayer":
            output_path = os.path.join(output_dir, f"GST_Taxpayer_Details_{os.getpid()}_{int(os.path.exists(output_dir))}.xlsx")
            taxpayers = []

            for gstin in gstins:
                try:
                    tp_data = client.get_taxpayer_details(gstin)
                    if isinstance(tp_data, dict) and tp_data.get("gstin"):
                        goods_data = {}
                        try:
                            goods_data = client.get_goods_services(gstin)
                        except Exception as ge:
                            print(f"Error fetching goods/services for {gstin}: {ge}")

                        record = client.build_taxpayer_record(tp_data, goods_data)
                        taxpayers.append(record)
                    else:
                        taxpayers.append({
                            "GSTIN": gstin,
                            "Processing Status": "Failed",
                            "Error / Remarks": "Invalid taxpayer response"
                        })
                except Exception as e:
                    print(f"Error fetching taxpayer {gstin}: {e}")
                    taxpayers.append({
                        "GSTIN": gstin,
                        "Processing Status": "Failed",
                        "Error / Remarks": str(e)
                    })

            save_taxpayer_records(taxpayers, output_path)
            report_filename = "GST_Taxpayer_Details_Report.xlsx"

        else:
            # Return filing status mode
            output_path = os.path.join(output_dir, f"GST_Return_Status_{os.getpid()}_{int(os.path.exists(output_dir))}.xlsx")
            returns_records = []

            # financial_year e.g. "2024-25" -> fy = "2024"
            fy = financial_year.split("-")[0] if "-" in financial_year else financial_year

            for gstin in gstins:
                record = {
                    "GSTIN": gstin,
                    "Legal Name": "",
                    "Financial Year": financial_year,
                    "Month": month,
                    "GSTR-1 Status": "",
                    "GSTR-1 Filing Date": "",
                    "GSTR-3B Status": "",
                    "GSTR-3B Filing Date": "",
                    "Processing Status": "Success",
                    "Error / Remarks": ""
                }

                try:
                    # Get taxpayer details first for legal name
                    try:
                        taxpayer = client.get_taxpayer_details(gstin)
                        if isinstance(taxpayer, dict):
                            record["Legal Name"] = taxpayer.get("lgnm", "")
                    except Exception as te:
                        print(f"Error fetching taxpayer name for {gstin}: {te}")

                    return_data = client.get_return_details(gstin, fy)
                    returns_list = client.flatten_returns(return_data)

                    gstr1 = None
                    gstr3b = None

                    for item in returns_list:
                        if not isinstance(item, dict):
                            continue
                        item_month = str(item.get("taxp", item.get("mth", ""))).strip()
                        rtn_typ = str(item.get("rtntype", "")).strip().upper()

                        if month != "All" and item_month.lower() != month.lower():
                            continue

                        if rtn_typ in ["GSTR1", "GSTR-1"]:
                            gstr1 = item
                        elif rtn_typ in ["GSTR3B", "GSTR-3B"]:
                            gstr3b = item

                    if return_type in ["Both", "GSTR-1"]:
                        if gstr1:
                            record["GSTR-1 Status"] = gstr1.get("status", "")
                            record["GSTR-1 Filing Date"] = gstr1.get("dof", "")
                        else:
                            record["GSTR-1 Status"] = "No filing record found"

                    if return_type in ["Both", "GSTR-3B"]:
                        if gstr3b:
                            record["GSTR-3B Status"] = gstr3b.get("status", "")
                            record["GSTR-3B Filing Date"] = gstr3b.get("dof", "")
                        else:
                            record["GSTR-3B Status"] = "No filing record found"

                    returns_records.append(record)

                except Exception as e:
                    print(f"Error fetching returns for {gstin}: {e}")
                    record["Processing Status"] = "Failed"
                    record["Error / Remarks"] = str(e)
                    returns_records.append(record)

            save_return_records(returns_records, output_path)
            report_filename = "GST_Return_Status_Report.xlsx"

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"GST bulk search processing failed: {str(e)}")

    def cleanup():
        if os.path.exists(output_path):
            try:
                os.remove(output_path)
            except:
                pass

    background_tasks.add_task(cleanup)

    return FileResponse(
        output_path,
        filename=report_filename
    )
