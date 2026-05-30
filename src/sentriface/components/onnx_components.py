from __future__ import annotations

from pathlib import Path
from typing import Any

from sentriface.components.image_ops import crop_face, load_bgr_image
from sentriface.errors import ModelSetupError
from sentriface.models import DetectedFace, Embedding, FaceBox


class OnnxRuntimeSession:
    """Small wrapper that keeps ONNX Runtime CPU-only and lazy-imported."""

    def __init__(self, model_path: Path, intra_op_threads: int = 1) -> None:
        if not model_path.exists():
            raise ModelSetupError(f"Model file not found: {model_path}")
        ort = _onnxruntime()
        options = ort.SessionOptions()
        options.intra_op_num_threads = max(1, intra_op_threads)
        options.inter_op_num_threads = 1
        options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self.session = ort.InferenceSession(
            str(model_path),
            sess_options=options,
            providers=["CPUExecutionProvider"],
        )
        self.input_name = self.session.get_inputs()[0].name
        self.input_shape = self.session.get_inputs()[0].shape

    def run(self, input_tensor: Any) -> list[Any]:
        return self.session.run(None, {self.input_name: input_tensor})


class OnnxScrfdDetector:
    """CPU SCRFD detector wrapper.

    This targets InsightFace SCRFD models such as det_500m.onnx.
    """

    def __init__(
        self,
        model_path: Path,
        max_image_edge: int = 880,
        input_size: int = 640,
        confidence_threshold: float = 0.55,
        intra_op_threads: int = 1,
    ) -> None:
        self.model_path = model_path
        self.max_image_edge = max_image_edge
        self.confidence_threshold = confidence_threshold
        self.runtime = OnnxRuntimeSession(model_path, intra_op_threads)
        self.input_size = _input_size(self.runtime.input_shape, fallback=input_size)

    def detect(self, image_path: Path) -> list[DetectedFace]:
        image = load_bgr_image(image_path)
        prepared, scale, pad = _scrfd_letterbox(image, self.input_size)
        tensor = _detector_tensor(prepared)
        outputs = self.runtime.run(tensor)
        return _decode_scrfd(outputs, scale, pad, self.confidence_threshold)


class OnnxArcFaceEmbedder:
    """CPU ArcFace-style embedder that returns normalized 512D vectors."""

    def __init__(
        self,
        model_path: Path,
        intra_op_threads: int = 1,
        output_size: int = 112,
    ) -> None:
        self.model_path = model_path
        self.output_size = output_size
        self.runtime = OnnxRuntimeSession(model_path, intra_op_threads)

    def encode(self, image_path: Path, face: DetectedFace) -> Embedding:
        image = load_bgr_image(image_path)
        crop = crop_face(image, face, output_size=self.output_size)
        tensor = _arcface_tensor(crop)
        outputs = self.runtime.run(tensor)
        vector = _flatten(outputs[0])
        return _normalize(vector)


def _detector_tensor(image: Any) -> Any:
    np = _numpy()
    cv2 = _cv2()
    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    tensor = rgb.astype(np.float32)
    tensor = (tensor - 127.5) / 128.0
    tensor = np.transpose(tensor, (2, 0, 1))[None, :, :, :]
    return np.ascontiguousarray(tensor)


def _arcface_tensor(face_crop: Any) -> Any:
    np = _numpy()
    cv2 = _cv2()
    rgb = cv2.cvtColor(face_crop, cv2.COLOR_BGR2RGB)
    tensor = rgb.astype(np.float32)
    tensor = (tensor - 127.5) / 128.0
    tensor = np.transpose(tensor, (2, 0, 1))[None, :, :, :]
    return np.ascontiguousarray(tensor)


def _input_size(shape: list[Any], fallback: int) -> tuple[int, int]:
    if len(shape) == 4 and isinstance(shape[2], int) and isinstance(shape[3], int):
        return shape[3], shape[2]
    return fallback, fallback


def _scrfd_letterbox(image: Any, input_size: tuple[int, int]) -> tuple[Any, float, tuple[int, int]]:
    np = _numpy()
    cv2 = _cv2()
    input_width, input_height = input_size
    height, width = image.shape[:2]
    scale = min(input_width / width, input_height / height)
    resized_width = int(round(width * scale))
    resized_height = int(round(height * scale))
    resized = cv2.resize(image, (resized_width, resized_height), interpolation=cv2.INTER_AREA)
    canvas = np.zeros((input_height, input_width, 3), dtype=image.dtype)
    pad_x = (input_width - resized_width) // 2
    pad_y = (input_height - resized_height) // 2
    canvas[pad_y : pad_y + resized_height, pad_x : pad_x + resized_width] = resized
    return canvas, scale, (pad_x, pad_y)


def _decode_scrfd(
    outputs: list[Any],
    scale: float,
    pad: tuple[int, int],
    threshold: float,
) -> list[DetectedFace]:
    np = _numpy()
    arrays = [np.asarray(output) for output in outputs]
    if len(arrays) in {6, 9}:
        return _decode_scrfd_feature_maps(arrays, scale, pad, threshold)
    return _decode_simple_detections(arrays, scale, pad, threshold)


def _decode_simple_detections(
    outputs: list[Any],
    scale: float,
    pad: tuple[int, int],
    threshold: float,
) -> list[DetectedFace]:
    detections = None
    for output in outputs:
        array = output
        if array.ndim == 3 and array.shape[0] == 1:
            array = array[0]
        if array.ndim == 2 and array.shape[1] >= 5:
            detections = array
            break

    if detections is None:
        raise RuntimeError(
            "Unsupported detector output shape. Add a decoder for this SCRFD model variant."
        )

    faces: list[DetectedFace] = []
    inv_scale = 1.0 / scale
    for row in detections:
        score = float(row[4])
        if score < threshold:
            continue
        x1, y1, x2, y2 = _unletterbox_box(row[:4], inv_scale, pad)
        faces.append(
            DetectedFace(
                box=FaceBox(
                    x=x1,
                    y=y1,
                    width=max(0, x2 - x1),
                    height=max(0, y2 - y1),
                    confidence=score,
                ),
                quality_score=score,
            )
        )
    return faces


def _decode_scrfd_feature_maps(
    outputs: list[Any],
    scale: float,
    pad: tuple[int, int],
    threshold: float,
) -> list[DetectedFace]:
    np = _numpy()
    input_height, input_width = _infer_scrfd_input_size(outputs)
    strides = [8, 16, 32]
    feature_count = 3
    has_landmarks = len(outputs) == 9
    proposals: list[tuple[float, list[float], list[float] | None]] = []

    for level, stride in enumerate(strides):
        scores = outputs[level].reshape(-1)
        boxes = outputs[level + feature_count].reshape((-1, 4)) * stride
        landmarks = None
        if has_landmarks:
            landmarks = outputs[level + feature_count * 2].reshape((-1, 10)) * stride

        centers = _anchor_centers(input_width, input_height, stride)
        if len(centers) != len(scores):
            repeat = max(1, len(scores) // max(1, len(centers)))
            centers = np.repeat(centers, repeat, axis=0)

        selected = np.where(scores >= threshold)[0]
        for index in selected:
            score = float(scores[index])
            box = _distance_to_box(centers[index], boxes[index])
            kps = None
            if landmarks is not None:
                kps = _distance_to_landmarks(centers[index], landmarks[index])
            proposals.append((score, box, kps))

    proposals.sort(key=lambda item: item[0], reverse=True)
    kept = _nms(proposals, iou_threshold=0.4)
    inv_scale = 1.0 / scale
    faces: list[DetectedFace] = []
    for score, box, landmarks in kept:
        x1, y1, x2, y2 = _unletterbox_box(box, inv_scale, pad)
        restored_landmarks = None
        if landmarks is not None:
            pad_x, pad_y = pad
            restored_landmarks = tuple(
                (
                    (float(landmarks[i]) - pad_x) * inv_scale,
                    (float(landmarks[i + 1]) - pad_y) * inv_scale,
                )
                for i in range(0, 10, 2)
            )
        faces.append(
            DetectedFace(
                box=FaceBox(
                    x=x1,
                    y=y1,
                    width=max(0, x2 - x1),
                    height=max(0, y2 - y1),
                    confidence=score,
                ),
                quality_score=score,
                landmarks=restored_landmarks,
            )
        )
    return faces


def _infer_scrfd_input_size(outputs: list[Any]) -> tuple[int, int]:
    counts = [outputs[index].reshape(-1).shape[0] for index in range(3)]
    strides = [8, 16, 32]
    for width in (640, 512, 480, 320):
        height = width
        expected = [((height // stride) * (width // stride) * 2) for stride in strides]
        if expected == counts:
            return height, width
    side = int((counts[0] / 2) ** 0.5) * 8
    return side, side


def _anchor_centers(width: int, height: int, stride: int) -> Any:
    np = _numpy()
    y_values = np.arange(0, height // stride) * stride
    x_values = np.arange(0, width // stride) * stride
    grid_x, grid_y = np.meshgrid(x_values, y_values)
    centers = np.stack((grid_x, grid_y), axis=-1).reshape(-1, 2)
    centers = centers + stride // 2
    return np.repeat(centers, 2, axis=0).astype(np.float32)


def _distance_to_box(center: Any, distance: Any) -> list[float]:
    return [
        float(center[0] - distance[0]),
        float(center[1] - distance[1]),
        float(center[0] + distance[2]),
        float(center[1] + distance[3]),
    ]


def _distance_to_landmarks(center: Any, distance: Any) -> list[float]:
    points: list[float] = []
    for index in range(0, 10, 2):
        points.append(float(center[0] + distance[index]))
        points.append(float(center[1] + distance[index + 1]))
    return points


def _unletterbox_box(box: Any, inv_scale: float, pad: tuple[int, int]) -> tuple[int, int, int, int]:
    pad_x, pad_y = pad
    x1 = int(round((float(box[0]) - pad_x) * inv_scale))
    y1 = int(round((float(box[1]) - pad_y) * inv_scale))
    x2 = int(round((float(box[2]) - pad_x) * inv_scale))
    y2 = int(round((float(box[3]) - pad_y) * inv_scale))
    return x1, y1, x2, y2


def _nms(
    proposals: list[tuple[float, list[float], list[float] | None]],
    iou_threshold: float,
) -> list[tuple[float, list[float], list[float] | None]]:
    kept: list[tuple[float, list[float], list[float] | None]] = []
    for proposal in proposals:
        if all(_iou(proposal[1], kept_item[1]) < iou_threshold for kept_item in kept):
            kept.append(proposal)
    return kept


def _iou(left: list[float], right: list[float]) -> float:
    x1 = max(left[0], right[0])
    y1 = max(left[1], right[1])
    x2 = min(left[2], right[2])
    y2 = min(left[3], right[3])
    intersection = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    left_area = max(0.0, left[2] - left[0]) * max(0.0, left[3] - left[1])
    right_area = max(0.0, right[2] - right[0]) * max(0.0, right[3] - right[1])
    union = left_area + right_area - intersection
    return intersection / union if union > 0 else 0.0


def _flatten(output: Any) -> list[float]:
    np = _numpy()
    return np.asarray(output, dtype=np.float32).reshape(-1).tolist()


def _normalize(vector: list[float]) -> Embedding:
    norm = sum(value * value for value in vector) ** 0.5 or 1.0
    return tuple(value / norm for value in vector)


def _onnxruntime() -> Any:
    try:
        import onnxruntime

        return onnxruntime
    except ImportError as exc:
        raise ModelSetupError(
            "ONNX Runtime is required for real face recognition. Install with: "
            "pip install onnxruntime"
        ) from exc


def _numpy() -> Any:
    try:
        import numpy

        return numpy
    except ImportError as exc:
        raise ModelSetupError("NumPy is required for ONNX components. Install with: pip install numpy") from exc


def _cv2() -> Any:
    try:
        import cv2

        return cv2
    except ImportError as exc:
        raise ModelSetupError(
            "OpenCV is required for ONNX components. Install with: "
            "pip install opencv-python-headless"
        ) from exc
