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
    gstins_text: str = Form(None)
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
    output_path = os.path.join(output_dir, f"GST_Bulk_Search_{os.getpid()}_{int(os.path.exists(output_dir))}.xlsx")

    try:
        model_path = os.path.join("app", "engines", "captcha_model.onnx")
        client = GSTClient(model_path=model_path)

        taxpayers = []
        returns = []

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

                for fy in ["2024-25", "2023-24"]:
                    try:
                        ret_resp = client.get_return_details(gstin, fy)
                        if isinstance(ret_resp, dict):
                            flat_rets = client.flatten_returns(ret_resp)
                            for ret in flat_rets:
                                if isinstance(ret, dict):
                                    returns.append({
                                        "GSTIN": gstin,
                                        "Legal Name": tp_data.get("lgnm", "") if isinstance(tp_data, dict) else "",
                                        "Financial Year": fy,
                                        "Month": ret.get("retprd", ret.get("mth", "")),
                                        "GSTR-1 Status": ret.get("rtntyp") == "GSTR1" and ret.get("status") or ret.get("gstr1Sts", ""),
                                        "GSTR-1 Filing Date": ret.get("dof", ""),
                                        "GSTR-3B Status": ret.get("rtntyp") == "GSTR3B" and ret.get("status") or ret.get("gstr3bSts", ""),
                                        "GSTR-3B Filing Date": ret.get("dof", ""),
                                        "Processing Status": "Success",
                                        "Error / Remarks": ""
                                    })
                    except Exception as re:
                        print(f"Error fetching returns for {gstin} {fy}: {re}")

            except Exception as e:
                print(f"Error fetching {gstin}: {e}")
                taxpayers.append({
                    "GSTIN": gstin,
                    "Processing Status": "Failed",
                    "Error / Remarks": str(e)
                })

        save_taxpayer_records(taxpayers, output_path)
        if returns:
            save_return_records(returns, output_path)
        else:
            save_return_records([{
                "GSTIN": gstins[0],
                "Legal Name": "",
                "Financial Year": "2024-25",
                "Month": "",
                "GSTR-1 Status": "",
                "GSTR-1 Filing Date": "",
                "GSTR-3B Status": "",
                "GSTR-3B Filing Date": "",
                "Processing Status": "Notice",
                "Error / Remarks": "No return filing records returned"
            }], output_path)

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
        filename="GST_Bulk_Search_Report.xlsx"
    )
