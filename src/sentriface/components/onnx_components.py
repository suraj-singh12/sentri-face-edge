from __future__ import annotations
from loguru import logger
from pathlib import Path
from typing import Any

from sentriface.components.image_ops import crop_face, load_bgr_image
from sentriface.errors import ModelSetupError
from sentriface.models import DetectedFace, Embedding, FaceBox

'''
    OnnxRuntimeSession = the engine that knows how to run any ONNX model.
'''
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

'''
    OnnxScrfdDetector = the driver using the engine specifically for face detection.
'''
class OnnxScrfdDetector:
    """CPU SCRFD detector wrapper.
    Sample and Computation Redistribution for Efficient Face Detection 
    This targets compatible SCRFD-style ONNX detector models.
    """
    def __init__(
        self,
        model_path: Path,
        max_image_edge: int = 880,
        input_size: int = 640,
        confidence_threshold: float = 0.55,
        intra_op_threads: int = 1,
        storage_key: bytes | None = None,
    ) -> None:
        self.model_path = model_path
        self.max_image_edge = max_image_edge
        self.confidence_threshold = confidence_threshold
        self.storage_key = storage_key
        self.runtime = OnnxRuntimeSession(model_path, intra_op_threads)
        self.input_size = _input_size(self.runtime.input_shape, fallback=input_size)

    def detect(self, image_path: Path) -> list[DetectedFace]:
        image = load_bgr_image(image_path, self.storage_key)
        prepared, scale, pad = _scrfd_letterbox(image, self.input_size)
        tensor = _detector_tensor(prepared)
        outputs = self.runtime.run(tensor)
        decoded_scrfd = _decode_scrfd(outputs, scale, pad, self.confidence_threshold)
        return decoded_scrfd


class OnnxArcFaceEmbedder:
    """CPU ArcFace-style embedder that returns normalized 512D vectors."""
    def __init__(
        self,
        model_path: Path,
        intra_op_threads: int = 1,
        output_size: int = 112,
        storage_key: bytes | None = None,
    ) -> None:
        self.model_path = model_path
        self.output_size = output_size
        self.storage_key = storage_key
        self.runtime = OnnxRuntimeSession(model_path, intra_op_threads)
        logger.debug(
            "ArcFace embedder initialized: model={} threads={} output_size={}",
            model_path,
            intra_op_threads,
            output_size,
        )

    def encode(self, image_path: Path, face: DetectedFace) -> Embedding:
        image = load_bgr_image(image_path, self.storage_key)
        crop = crop_face(image, face, output_size=self.output_size)
        tensor = _arcface_tensor(crop)
        outputs = self.runtime.run(tensor)
        vector = _flatten(outputs[0])
        return _normalize(vector)
    
"""
Convert OpenCV image into the exact format the detector model expects.
For Detection purpose
"""
def _detector_tensor(image: Any) -> Any:
    np = _numpy()
    cv2 = _cv2()
    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    tensor = rgb.astype(np.float32)
    tensor = (tensor - 127.5) / 128.0       # return a number btw -1.0 to 1.0 
    # (ht, wt, color_channels) -> transpose -> ( color_channels, ht, wt)
    tensor = np.transpose(tensor, (2, 0, 1))[None, :, :, :]    
    # return as a contiguous array of channels (easier to work on) [[RR, ..], [BB, ..], [GG, ..]] - all 3 channels, as separate contigous memory.
    contiguous = np.ascontiguousarray(tensor)
    return contiguous


# ---------------------------------- Recognizer ----------------------------------

'''
transforms an OpenCV face crop into the exact tensor that ArcFace expects: RGB, float32, 
normalized to approximately [-1, 1], channel-first (CHW), batched (NCHW), and stored contiguously in memory.
For generating face recognition (embeddings)
'''
def _arcface_tensor(face_crop: Any) -> Any:
    np = _numpy()
    cv2 = _cv2()
    # convert channel format BGR to RGB
    rgb = cv2.cvtColor(face_crop, cv2.COLOR_BGR2RGB)
    tensor = rgb.astype(np.float32)
    tensor = (tensor - 127.5) / 128.0       # tensor normalized, pixels lie in [-1,1] (-1: black, 0: grey, 1: white)
    # neural nw expects: (batch,channel,height,width), so post transposing (h,w,c) to (c,h,w) 
    # add additional dimension i.e. batch using [None, ;, ;, ;]
    # that translates to batch: no of images, channel: RGB, height, width
    tensor = np.transpose(tensor, (2, 0, 1))[None, :, :, :]
    # Ensuring memory layout is contiguous for efficient inference
    return np.ascontiguousarray(tensor)


def _input_size(shape: list[Any], fallback: int) -> tuple[int, int]:
    # shape of typical onnx input is: (batch, channel, height, width)
    if len(shape) == 4 and isinstance(shape[2], int) and isinstance(shape[3], int):
        return shape[3], shape[2]       # return (width, height) 
    return fallback, fallback           # otherwise return default e.g. 640, 640

'''
given an image of any size (axb), resize it to 640x640 size, 
'''
def _scrfd_letterbox(image: Any, input_size: tuple[int, int]) -> tuple[Any, float, tuple[int, int]]:
    np = _numpy()
    cv2 = _cv2()
    input_width, input_height = input_size      # (640 x 640) for scrfd model
    height, width = image.shape[:2]
    scale = min(input_width / width, input_height / height)
    resized_width = int(round(width * scale))
    resized_height = int(round(height * scale))
    # resized image 
    resized = cv2.resize(image, (resized_width, resized_height), interpolation=cv2.INTER_AREA)
    # black canvas of 640 x 640 
    canvas = np.zeros((input_height, input_width, 3), dtype=image.dtype)
    pad_x = (input_width - resized_width) // 2
    pad_y = (input_height - resized_height) // 2
    # paste the resized image on this canvas in a manner 
    # that padding remains in sides and image in center in case any dimension of actual image 
    # is smaller than standard 640x640 
    canvas[pad_y : pad_y + resized_height, pad_x : pad_x + resized_width] = resized
    return canvas, scale, (pad_x, pad_y)

'''
Decides what type of decoder to be used.
Scrfd decoder or simple
'''
def _decode_scrfd(
    outputs: list[Any],
    scale: float,
    pad: tuple[int, int],
    threshold: float,
) -> list[DetectedFace]:
    np = _numpy()
    arrays = [np.asarray(output) for output in outputs]
    if len(arrays) in {6, 9}:       # if output tensors are 6 or 9, it is scrfd model, we will use scrfd decoder 
        # 6: (scores, boxes), 9: (scores, boxes, landmarks)
        decoded_feature_maps = _decode_scrfd_feature_maps(arrays, scale, pad, threshold)
        return decoded_feature_maps
    # otherwise we have baked response (x1,y1,x2,y2,score), so that's simple decoder required 
    decoded_simple_det = _decode_simple_detections(arrays, scale, pad, threshold)
    return decoded_simple_det

'''
simpler version of _decode_scrfd_detections()
_decode_scrfd_detections(): used for scrfd detectors returning raw output
def _decode_simple_detections(): used for detectors which return baked output instead of raw.
Does: 
Read detections
      ↓
Remove low-confidence detections
      ↓
Undo letterboxing
      ↓
Create DetectedFace objects
'''
def _decode_simple_detections(
    outputs: list[Any],
    scale: float,
    pad: tuple[int, int],
    threshold: float,
) -> list[DetectedFace]:
    detections = None 
    for output in outputs:
        array = output
        if array.ndim == 3 and array.shape[0] == 1:     # if array is 3d (x,y,z) and x = 1, i.e. there's only 1 batch of 3d, then why not make it 2d, get rid of extra dimension
            array = array[0]
        if array.ndim == 2 and array.shape[1] >= 5:     # if array is 2d (x,y), check if no of cols is atleast 5 (so we know each row has x1,y1,x2,y2,score)
            detections = array
            break

    if detections is None:
        raise RuntimeError(
            "Unsupported detector output shape. Add a decoder for this SCRFD model variant."
        )
    
    faces: list[DetectedFace] = []
    inv_scale = 1.0 / scale
    for row in detections:
        score = float(row[4])           # row[4] is score. row=(x1, y1, x2, y2, score)
        if score < threshold:
            continue
        # get the coordinates of the face on initial input image
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

'''
This is the heart of the SCRFD post-processing pipeline.
The neural network has already run. 
This function takes the raw tensors produced by the model and converts them into actual face detections.
Image
   │
SCRFD Neural Network
   │
Raw Numbers (outputs)
   │
_decode_scrfd_feature_maps()
   │
DetectedFace objects


In detail: 
Image
   │
   ▼
SCRFD Model
   │
   ▼
Scores
Boxes
Landmarks
   │
   ▼
For each stride (8,16,32)
   │
   ▼
Generate anchor centers
   │
   ▼
Keep scores > threshold
   │
   ▼
Decode boxes
   │
   ▼
Decode landmarks
   │
   ▼
Collect proposals
   │
   ▼
Sort by confidence
   │
   ▼
Non-Maximum Suppression
   │
   ▼
Undo letterboxing
   │
   ▼
Create DetectedFace objects
   │
   ▼
Return faces

This function translates the raw neural network outputs into usable face detections by matching predictions 
to anchor centers, filtering weak detections, decoding boxes and landmarks into image coordinates, 
removing duplicates with NMS, undoing image preprocessing, 
and finally returning clean DetectedFace objects. 
Once this fn is understood, the entire inference pipeline of an anchor-based face detector like SCRFD is understood.
'''
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
    # [(score, box, landmarks:optional)]

    for level, stride in enumerate(strides):
        scores = outputs[level].reshape(-1)
        boxes = outputs[level + feature_count].reshape((-1, 4)) * stride        
        # box(face distance from anchor center) * strides = pixel distances from anchor center
        landmarks = None
        if has_landmarks:
            landmarks = outputs[level + feature_count * 2].reshape((-1, 10)) * stride

        centers = _anchor_centers(input_width, input_height, stride)
        # when using diff recognition models, we need to make sure of compatibility 
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

'''
Figure out what input image size (320x320, 480x480, 512x512, 640x640) 
was used by the SCRFD model, 
just by looking at the model outputs.
Model outputs
       │
Flatten outputs
       │
Count number of anchors
       │
Try known input sizes
       │
       ├── Match? → Return that size
       │
Otherwise:
Recover size mathematically
'''
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

'''
Function computes the center coordinates of all anchor boxes for a given feature map.
'''
def _anchor_centers(width: int, height: int, stride: int) -> Any:
    np = _numpy()
    y_values = np.arange(0, height // stride) * stride
    x_values = np.arange(0, width // stride) * stride
    grid_x, grid_y = np.meshgrid(x_values, y_values)
    centers = np.stack((grid_x, grid_y), axis=-1).reshape(-1, 2)
    centers = centers + stride // 2
    return np.repeat(centers, 2, axis=0).astype(np.float32)

'''
predicts 4 distances: left_distance, top_distance, right_distance, bottom_distance
i.e. face box boundaries
'''
def _distance_to_box(center: Any, distance: Any) -> list[float]:
    return [
        float(center[0] - distance[0]),
        float(center[1] - distance[1]),
        float(center[0] + distance[2]),
        float(center[1] + distance[3]),
    ]


'''
distance from centre of face to the landmarks (left eye, right eye, nose, left mouth, right mouth) in image 
'''
def _distance_to_landmarks(center: Any, distance: Any) -> list[float]:
    points: list[float] = []
    for index in range(0, 10, 2):
        points.append(float(center[0] + distance[index]))
        points.append(float(center[1] + distance[index + 1]))
    return points


'''
Prediction
↓
Remove padding
↓
Undo scaling
↓
Original coordinates
'''
def _unletterbox_box(box: Any, inv_scale: float, pad: tuple[int, int]) -> tuple[int, int, int, int]:
    pad_x, pad_y = pad
    x1 = int(round((float(box[0]) - pad_x) * inv_scale))
    y1 = int(round((float(box[1]) - pad_y) * inv_scale))
    x2 = int(round((float(box[2]) - pad_x) * inv_scale))
    y2 = int(round((float(box[3]) - pad_y) * inv_scale))
    return x1, y1, x2, y2

'''
performs Non-Maximum Suppression (NMS).
The purpose of NMS is:
If multiple boxes detect the same object, keep only the best one.
Assumes: proposals are already sorted by confidence/scores
'''
def _nms(
    proposals: list[tuple[float, list[float], list[float] | None]],
    iou_threshold: float,
) -> list[tuple[float, list[float], list[float] | None]]:
    kept: list[tuple[float, list[float], list[float] | None]] = []
    for proposal in proposals:
        if all(_iou(proposal[1], kept_item[1]) < iou_threshold for kept_item in kept):
            kept.append(proposal)
    return kept

'''
calculates intersection over union.
IoU is used everywhere in object detection:
* During training (to compare predicted vs. ground-truth boxes)
* During Non-Maximum Suppression (NMS) to remove duplicate detections

The closer the result is to 1, the more the two boxes overlap.
'''
def _iou(left: list[float], right: list[float]) -> float:
    '''
        A bounding box is represented as:   [x1, y1, x2, y2]
        so:
        left bounding box = [left[0], left[1], left[2], left[3]]
        right bounding box = [right[0], right[1], right[2], right[3]]
    '''
    x1 = max(left[0], right[0])
    y1 = max(left[1], right[1])
    x2 = min(left[2], right[2])
    y2 = min(left[3], right[3])
    intersection = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    left_area = max(0.0, left[2] - left[0]) * max(0.0, left[3] - left[1])
    right_area = max(0.0, right[2] - right[0]) * max(0.0, right[3] - right[1])
    union = left_area + right_area - intersection
    return intersection / union if union > 0 else 0.0

'''
Function converts whatever the model returned into a simple 1D Python list of floats
'''
def _flatten(output: Any) -> list[float]:
    np = _numpy()
    return np.asarray(output, dtype=np.float32).reshape(-1).tolist()


'''
This function converts any vector into a unit vector (length = 1) by dividing every element by its Euclidean length.
This lets you compare vectors based on direction rather than magnitude
'''
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


'''
Google Maps                     CNN Feature Maps
Street Level   <--------->      80x80 (High Spatial Resolution)
City Level     <--------->      40x40
Country Level  <--------->      20x20 (Low Spatial Resolution)

There are:
* Small face (20x20 px)
* Medium face (80x80 px)
* Large face (250x250 px)

The CNN produces three feature maps:
80x80
40x40
20x20

Each has its own detection head.
80x80 ---> Detect small faces           [80x80 means there are 80 rows, 80 cols of the 640x640 img now]
40x40 ---> Detect medium faces
20x20 ---> Detect large faces

Each head predicts:
* Is there an object?
* Bounding box
* Class
* Confidence
The predictions are merged, then duplicate boxes are removed using Non-Maximum Suppression (NMS).

The real intuition
Imagine you're searching for people from a helicopter.
* Flying low (high spatial resolution) lets you spot a child in a crowd, but you see only a small area at once.
* Flying high (low spatial resolution) lets you quickly spot a football stadium, but a single person disappears.

A detector needs both viewpoints because real images contain objects at many scales. 
That's why architectures like YOLO and RetinaFace use multiple feature maps with strides 8, 16, and 32. 
They aren't redundant. They're specialists working together.

recognition engine output / proposals: [scores, box, landmarks] 
                            i.e. [confidence, face_loc_from_anchor[], landmarks[]]
                            landmarks[] are left eye, right eye, nose, left mouth, right mouth. Each has 2 coordinates
                            box: location of face from center anchor i.e. left, right, up, down from anchor

'''
