import random
import time

import requests

from app.engines.captcha_solver import CaptchaSolver


BASE_URL = "https://services.gst.gov.in"


class GSTClient:

    # ========================================================
    # INITIALIZATION
    # ========================================================

    def __init__(
        self,
        model_path="captcha_model.onnx",
        captcha_retries=4,
        timeout=30,
        request_retries=4
    ):
        self.timeout = timeout
        self.captcha_retries = captcha_retries
        self.request_retries = request_retries
        self.backoff_base = 1.5

        self.solver = CaptchaSolver(
            model_path
        )

        self.session = requests.Session()

        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 "
                "(Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/153.0.0.0 "
                "Safari/537.36"
            ),
            "Accept": (
                "application/json, "
                "text/plain, */*"
            ),
            "Referer": (
                BASE_URL +
                "/services/searchtp"
            )
        })

        self.initialize_session()

    # ========================================================
    # HTTP RETRY / BACKOFF
    # ========================================================

    def _request_with_retry(self, method, url, **kwargs):
        last_error = None

        for attempt in range(1, self.request_retries + 1):
            try:
                response = self.session.request(method, url, **kwargs)

                # Retry only temporary server/rate-limit responses.
                if response.status_code == 429 or 500 <= response.status_code <= 599:
                    if attempt < self.request_retries:
                        time.sleep(self.backoff_base * (2 ** (attempt - 1)))
                        continue

                response.raise_for_status()
                return response

            except (requests.Timeout, requests.ConnectionError) as exc:
                last_error = exc
                if attempt < self.request_retries:
                    time.sleep(self.backoff_base * (2 ** (attempt - 1)))
                    continue
                raise

            except requests.HTTPError as exc:
                last_error = exc
                status = getattr(exc.response, "status_code", None)
                if (status == 429 or (status is not None and 500 <= status <= 599)) and attempt < self.request_retries:
                    time.sleep(self.backoff_base * (2 ** (attempt - 1)))
                    continue
                raise

        raise RuntimeError(f"Request failed after retries: {last_error}")

    # ========================================================
    # GST SESSION
    # ========================================================

    def initialize_session(self):

        response = self._request_with_retry(
            "GET",
            BASE_URL + "/services/searchtp",
            timeout=self.timeout
        )

        response.raise_for_status()

    # ========================================================
    # CAPTCHA
    # ========================================================

    def get_captcha(self):

        response = self._request_with_retry(
            "GET",
            BASE_URL + "/services/captcha",

            params={
                "rnd": random.random()
            },

            timeout=self.timeout
        )

        response.raise_for_status()

        captcha = self.solver.solve(
            response.content
        )

        if (
            len(captcha) != 6
            or not captcha.isdigit()
        ):
            raise RuntimeError(
                "CAPTCHA model returned "
                f"invalid value: {captcha}"
            )

        return captcha

    # ========================================================
    # TAXPAYER DETAILS
    # ========================================================

    def get_taxpayer_details(
        self,
        gstin
    ):

        last_error = None

        for attempt in range(
            1,
            self.captcha_retries + 1
        ):

            try:

                captcha = self.get_captcha()

                response = self._request_with_retry(
                    "POST",
                    BASE_URL +
                    "/services/api/search/"
                    "taxpayerDetails",

                    json={
                        "gstin": gstin,
                        "captcha": captcha
                    },

                    timeout=self.timeout
                )

                response.raise_for_status()

                data = response.json()

                if data.get("gstin"):
                    return data

                last_error = (
                    data.get("message")
                    or data.get("error")
                    or str(data)
                )

            except Exception as exc:

                last_error = str(exc)

            if (
                attempt
                <
                self.captcha_retries
            ):
                time.sleep(0.8)

        raise RuntimeError(
            "Unable to obtain taxpayer "
            "details after "
            f"{self.captcha_retries} attempts. "
            f"Last response: {last_error}"
        )

    # ========================================================
    # GOODS / SERVICES
    # ========================================================

    def get_goods_services(
        self,
        gstin
    ):

        response = self._request_with_retry(
            "GET",
            BASE_URL +
            "/services/api/search/goodservice",

            params={
                "gstin": gstin
            },

            timeout=self.timeout
        )

        response.raise_for_status()

        return response.json()

    # ========================================================
    # RETURN FILING DETAILS
    # ========================================================

    def get_return_details(
        self,
        gstin,
        fy
    ):

        response = self._request_with_retry(
            "POST",
            BASE_URL +
            "/services/api/search/"
            "taxpayerReturnDetails",

            json={
                "gstin": gstin,
                "fy": str(fy)
            },

            timeout=self.timeout
        )

        response.raise_for_status()

        return response.json()

    # ========================================================
    # FORMAT STATE JURISDICTION
    # ========================================================

    @staticmethod
    def format_state_office(
        stj
    ):

        if not stj:
            return ""

        values = {}

        for part in stj.split(","):

            part = part.strip()

            if " - " not in part:
                continue

            key, value = part.split(
                " - ",
                1
            )

            value = (
                value.replace(
                    "(Jurisdictional Office)",
                    ""
                ).strip()
            )

            values[
                key.strip().lower()
            ] = value

        parts = [
            "STATE"
        ]

        if values.get("state"):

            parts.append(
                values["state"]
            )

        if values.get("division"):

            parts.append(
                "Division: "
                + values["division"]
            )

        if values.get("district"):

            parts.append(
                "District: "
                + values["district"]
            )

        if values.get("ward"):

            parts.append(
                "Ward: "
                + values["ward"]
            )

        return " | ".join(
            parts
        )

    # ========================================================
    # FORMAT CENTER JURISDICTION
    # ========================================================

    @staticmethod
    def format_center_office(
        ctj
    ):

        if not ctj:
            return ""

        values = {}

        for part in ctj.split(","):

            part = part.strip()

            if " - " not in part:
                continue

            key, value = part.split(
                " - ",
                1
            )

            value = (
                value.replace(
                    "(Jurisdictional Office)",
                    ""
                ).strip()
            )

            values[
                key.strip().lower()
            ] = value

        parts = [
            "CENTER"
        ]

        if values.get("zone"):

            parts.append(
                "Zone: "
                + values["zone"]
            )

        if values.get(
            "commissionerate"
        ):

            parts.append(
                "Commissionerate: "
                + values[
                    "commissionerate"
                ]
            )

        if values.get("division"):

            parts.append(
                "Division: "
                + values["division"]
            )

        if values.get("range"):

            parts.append(
                "Range: "
                + values["range"]
            )

        return " | ".join(
            parts
        )

    # ========================================================
    # DETERMINE ADMINISTRATIVE OFFICE
    # ========================================================

    def get_jurisdiction_offices(
        self,
        taxpayer
    ):

        stj = str(
            taxpayer.get(
                "stj",
                ""
            )
            or ""
        )

        ctj = str(
            taxpayer.get(
                "ctj",
                ""
            )
            or ""
        )

        state_office = (
            self.format_state_office(
                stj
            )
        )

        center_office = (
            self.format_center_office(
                ctj
            )
        )

        # ----------------------------------------------------
        # IMPORTANT:
        #
        # GST marks the Administrative Office by putting:
        #
        # (Jurisdictional Office)
        #
        # inside either stj OR ctj.
        # ----------------------------------------------------

        stj_is_admin = (
            "(jurisdictional office)"
            in stj.lower()
        )

        ctj_is_admin = (
            "(jurisdictional office)"
            in ctj.lower()
        )

        # STATE is Administrative Office
        if (
            stj_is_admin
            and not ctj_is_admin
        ):

            return (
                state_office,
                center_office
            )

        # CENTER is Administrative Office
        if (
            ctj_is_admin
            and not stj_is_admin
        ):

            return (
                center_office,
                state_office
            )

        # ----------------------------------------------------
        # EDGE CASE
        #
        # If GST marks both or neither, DON'T GUESS.
        # Keep both available and flag it in remarks.
        # ----------------------------------------------------

        return (
            "",
            "",
            state_office,
            center_office
        )

    # ========================================================
    # PARSE GOODS AND SERVICES
    # ========================================================

    @staticmethod
    def parse_goods_services(
        goods_data
    ):

        goods_hsn = []
        goods_description = []

        services_hsn = []
        services_description = []

        if not isinstance(
            goods_data,
            dict
        ):

            return (
                goods_hsn,
                goods_description,
                services_hsn,
                services_description
            )

        # ----------------------------------------------------
        # GOODS
        #
        # Confirmed GST response:
        #
        # bzgddtls
        #   hsncd
        #   gdes
        # ----------------------------------------------------

        known_goods = goods_data.get(
            "bzgddtls",
            []
        )

        if isinstance(
            known_goods,
            list
        ):

            for item in known_goods:

                if not isinstance(
                    item,
                    dict
                ):
                    continue

                code = str(
                    item.get(
                        "hsncd",
                        ""
                    )
                    or ""
                ).strip()

                description = str(
                    item.get(
                        "gdes",
                        ""
                    )
                    or ""
                ).strip()

                if code:

                    goods_hsn.append(
                        code
                    )

                if description:

                    goods_description.append(
                        description
                    )

        # ----------------------------------------------------
        # SERVICES
        #
        # Inspect additional arrays returned by goodservice.
        # We do not assume bzgddtls is services.
        # ----------------------------------------------------

        for (
            array_name,
            array_data
        ) in goods_data.items():

            if array_name == "bzgddtls":
                continue

            if not isinstance(
                array_data,
                list
            ):
                continue

            for item in array_data:

                if not isinstance(
                    item,
                    dict
                ):
                    continue

                code = ""

                for key in [
                    "saccd",
                    "sac",
                    "sacCode",
                    "hsncd",
                    "hsn",
                    "code"
                ]:

                    value = item.get(
                        key
                    )

                    if value not in [
                        None,
                        ""
                    ]:

                        code = str(
                            value
                        ).strip()

                        break

                description = ""

                for key in [
                    "sdes",
                    "sdesc",
                    "serviceDescription",
                    "gdes",
                    "description",
                    "desc"
                ]:

                    value = item.get(
                        key
                    )

                    if value not in [
                        None,
                        ""
                    ]:

                        description = str(
                            value
                        ).strip()

                        break

                if (
                    not code
                    and not description
                ):
                    continue

                array_lower = str(
                    array_name
                ).lower()

                looks_like_service = (
                    "service"
                    in array_lower

                    or "serv"
                    in array_lower

                    or "sac"
                    in array_lower

                    or "saccd"
                    in item

                    or "sdes"
                    in item

                    or "sdesc"
                    in item
                )

                if looks_like_service:

                    if code:

                        services_hsn.append(
                            code
                        )

                    if description:

                        services_description.append(
                            description
                        )

        # ----------------------------------------------------
        # REMOVE DUPLICATES
        # ----------------------------------------------------

        goods_hsn = list(
            dict.fromkeys(
                goods_hsn
            )
        )

        goods_description = list(
            dict.fromkeys(
                goods_description
            )
        )

        services_hsn = list(
            dict.fromkeys(
                services_hsn
            )
        )

        services_description = list(
            dict.fromkeys(
                services_description
            )
        )

        return (
            goods_hsn,
            goods_description,
            services_hsn,
            services_description
        )

    # ========================================================
    # FLATTEN RETURN RESPONSE
    # ========================================================

    @staticmethod
    def flatten_returns(
        data
    ):

        result = []

        groups = data.get(
            "filingStatus",
            []
        )

        for group in groups:

            if isinstance(
                group,
                list
            ):

                result.extend(
                    group
                )

            elif isinstance(
                group,
                dict
            ):

                result.append(
                    group
                )

        return result

    # ========================================================
    # BUILD FINAL TAXPAYER RECORD
    # ========================================================

    def build_taxpayer_record(
        self,
        taxpayer,
        goods_data
    ):

        # ----------------------------------------------------
        # DETERMINE ADMIN / OTHER OFFICE
        # ----------------------------------------------------

        jurisdiction_result = (
            self.get_jurisdiction_offices(
                taxpayer
            )
        )

        jurisdiction_warning = ""

        if len(
            jurisdiction_result
        ) == 2:

            (
                administrative_office,
                other_office
            ) = jurisdiction_result

        else:

            (
                administrative_office,
                other_office,
                state_office,
                center_office
            ) = jurisdiction_result

            jurisdiction_warning = (
                "GST response did not uniquely identify "
                "Administrative Office. "
                "State Jurisdiction: "
                f"{state_office} || "
                "Center Jurisdiction: "
                f"{center_office}"
            )

        # ----------------------------------------------------
        # NATURE OF BUSINESS
        # ----------------------------------------------------

        nba = taxpayer.get(
            "nba",
            []
        )

        if isinstance(
            nba,
            list
        ):

            nba = "; ".join(
                str(x)
                for x in nba
            )

        else:

            nba = str(
                nba or ""
            )

        # ----------------------------------------------------
        # GOODS / SERVICES
        # ----------------------------------------------------

        (
            goods_hsn,
            goods_description,
            services_hsn,
            services_description
        ) = self.parse_goods_services(
            goods_data
        )

        # ----------------------------------------------------
        # FINAL OUTPUT
        # ----------------------------------------------------

        return {

            "GSTIN":
                taxpayer.get(
                    "gstin",
                    ""
                ),

            "Legal Name":
                taxpayer.get(
                    "lgnm",
                    ""
                ),

            "Trade Name":
                taxpayer.get(
                    "tradeNam",
                    ""
                ),

            "Registration Date":
                taxpayer.get(
                    "rgdt",
                    ""
                ),

            "Constitution":
                taxpayer.get(
                    "ctb",
                    ""
                ),

            "GSTIN Status":
                taxpayer.get(
                    "sts",
                    ""
                ),

            "Taxpayer Type":
                taxpayer.get(
                    "dty",
                    ""
                ),

            # ----------------------------------------
            # Correct dynamic jurisdiction assignment
            # ----------------------------------------

            "Administrative Office (Main Dealing Office)":
                administrative_office,

            "Other Office":
                other_office,

            # ----------------------------------------

            "Principal Place of Business":
                taxpayer.get(
                    "pradr",
                    {}
                ).get(
                    "adr",
                    ""
                ),

            "Aadhaar Authenticated":
                taxpayer.get(
                    "adhrVFlag",
                    ""
                ),

            "Aadhaar Authentication Date":
                taxpayer.get(
                    "adhrVdt",
                    ""
                ),

            "e-KYC Verified":
                taxpayer.get(
                    "ekycVFlag",
                    ""
                ),

            "Nature of Core Business Activity":
                taxpayer.get(
                    "ntcrbs",
                    ""
                ),

            "Nature of Business Activities":
                nba,

            "E-Invoice Status":
                taxpayer.get(
                    "einvoiceStatus",
                    ""
                ),

            "Field Visit Conducted":
                taxpayer.get(
                    "isFieldVisitConducted",
                    ""
                ),

            # ----------------------------------------
            # GOODS
            # ----------------------------------------

            "Goods HSN":
                "; ".join(
                    goods_hsn
                ),

            "Goods Description":
                "; ".join(
                    goods_description
                ),

            # ----------------------------------------
            # SERVICES
            # ----------------------------------------

            "Services HSN/SAC":
                "; ".join(
                    services_hsn
                ),

            "Services Description":
                "; ".join(
                    services_description
                ),

            # ----------------------------------------
            # PROCESSING
            # ----------------------------------------

            "Processing Status":
                "Success",

            "Error / Remarks":
                jurisdiction_warning
        }