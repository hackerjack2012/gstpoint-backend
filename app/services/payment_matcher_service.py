import os
from app.engines.single_ledger_matcher import match_fifo
from app.engines.multi_ledger_matcher import multi_ledger_match


def process_payment_matcher(
    input_file,
    ledger_type,
    delay_threshold,
    gst_rate
):
    os.makedirs("app/temp", exist_ok=True)

    input_path = os.path.join(
        "app/temp",
        input_file.filename
    )

    with open(input_path, "wb") as f:
        f.write(input_file.file.read())

    output_path = input_path.replace(
        ".xlsx",
        "_MatchedFIFO.xlsx"
    )

    if ledger_type == "single":
        match_fifo(
            input_path,
            delay_threshold,
            gst_rate,
            output_path
        )
    else:
        multi_ledger_match(
            input_path,
            delay_threshold,
            gst_rate,
            output_path
        )

    return output_path