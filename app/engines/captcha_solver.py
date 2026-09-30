import os

import cv2
import numpy as np
import onnxruntime as ort


MODEL_WIDTH = 182
MODEL_HEIGHT = 50
BLANK_CLASS = 10


class CaptchaSolver:
    def __init__(self, model_path="captcha_model.onnx"):
        if not os.path.exists(model_path):
            raise FileNotFoundError(
                f"CAPTCHA model not found: {model_path}"
            )

        self.session = ort.InferenceSession(
            model_path,
            providers=["CPUExecutionProvider"]
        )

        self.input_name = self.session.get_inputs()[0].name
        self.output_name = self.session.get_outputs()[0].name

    def _decode_ctc(self, prediction):
        sequence = np.argmax(
            prediction[0],
            axis=-1
        )

        result = []
        previous = None

        for value in sequence:
            value = int(value)

            if value != previous:
                if 0 <= value <= 9:
                    result.append(str(value))

            previous = value

        return "".join(result)

    def solve(self, image_bytes):
        data = np.frombuffer(
            image_bytes,
            np.uint8
        )

        image = cv2.imdecode(
            data,
            cv2.IMREAD_GRAYSCALE
        )

        if image is None:
            raise RuntimeError(
                "Unable to decode CAPTCHA image."
            )

        image = cv2.resize(
            image,
            (MODEL_WIDTH, MODEL_HEIGHT)
        )

        image = (
            image.astype(np.float32)
            / 255.0
        )

        image = np.expand_dims(
            image,
            axis=-1
        )

        image = np.expand_dims(
            image,
            axis=0
        )

        prediction = self.session.run(
            [self.output_name],
            {
                self.input_name: image
            }
        )[0]

        captcha = self._decode_ctc(
            prediction
        )

        return captcha