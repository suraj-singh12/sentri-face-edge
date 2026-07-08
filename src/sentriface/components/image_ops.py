from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from sentriface.errors import InputImageError
from sentriface.models import DetectedFace
# Todo: crop_face() & crop_face_without_alignment() are similar!

'''
Pre-Processing: 
OPTIMIZATION of image prior to sending it to model for processing.

'''

ARCFACE_TEMPLATE = (
    (38.2946, 51.6963),
    (73.5318, 51.5014),
    (56.0252, 71.7366),
    (41.5493, 92.3655),
    (70.7299, 92.2041),
)


def load_bgr_image(image_path: Path) -> Any:
    path = image_path.resolve()
    try:
        stat = path.stat()
        image = _cached_imread(str(path), stat.st_mtime_ns, stat.st_size)
    except OSError:
        image = _cached_imread(str(path), 0, 0)
    if image is None:
        raise InputImageError(f"Could not read image: {image_path}")
    return image


@lru_cache(maxsize=8)
def _cached_imread(path: str, mtime_ns: int, size: int) -> Any:
    return _cv2().imread(path)



def resize_max_edge(image: Any, max_edge: int) -> tuple[Any, float]:
    """ 
    OPTIMIZATION during pre-processing: 
    Resize the image size in RAM (not on disk) if it is larger than max_edge, 
    and return resized image & scale
    -> reduces memory, cpu usage significantly while recognizing
    """
    cv2 = _cv2()
    height, width = image.shape[:2]
    longest = max(height, width)
    if longest <= max_edge:
        return image, 1.0
    scale = max_edge / float(longest)
    resized = cv2.resize(
        image,
        (int(width * scale), int(height * scale)),
        interpolation=cv2.INTER_AREA,       # averages neighbouring pixels, 
                    # results in cleaner face, better detector performance (boost) 
    )
    return resized, scale


def crop_face(image: Any, face: DetectedFace, output_size: int = 112) -> Any:
    """
    Extract a face crop suitable for the recognition model.
    If the detection contains facial landmarks (typically from SCRFD),
    the face is first aligned to the ArcFace template to improve
    recognition accuracy.
    If landmarks are unavailable, falls back to a simple bounding-box
    crop and resize.
    """
    cv2 = _cv2()
    if face.landmarks and len(face.landmarks) >= 5:
        return align_face(image, face, output_size)
    
    height, width = image.shape[:2]
    x1 = max(0, face.box.x)
    y1 = max(0, face.box.y)
    x2 = min(width, face.box.x + face.box.width)
    y2 = min(height, face.box.y + face.box.height)
    if x2 <= x1 or y2 <= y1:
        raise InputImageError("Invalid face box for crop")
    crop = image[y1:y2, x1:x2]
    return cv2.resize(crop, (output_size, output_size), interpolation=cv2.INTER_AREA)


def save_face_crop(image: Any, face: DetectedFace, output_path: Path, output_size: int = 112) -> str:
    """
    Image -> Crop / Align face -> Save face image to disk -> Return saved path
    This is what helps keeping the People library with images. 
    """
    cv2 = _cv2()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    crop = crop_face(image, face, output_size=output_size)
    if not cv2.imwrite(str(output_path), crop):
        raise InputImageError(f"Could not save face crop: {output_path}")
    return str(output_path)


"""
OPTIMIZATION: during pre-processing
Improves recognition accuracy
Straightens and standardizes the face before recognition.
# because same person + tilted face = lower similarity
# same person + tilted face = stronger match
> Face recognition models like ArcFace expect faces in a fixed layout
"""
def align_face(image: Any, face: DetectedFace, output_size: int = 112) -> Any:
    """
    Align a detected face using its five facial landmarks.
    The detected landmarks are mapped to the canonical ArcFace landmark
    template using an affine transformation, producing a normalized
    face crop of the requested output size.
    If the transformation cannot be estimated, a simple crop is used
    as a fallback.
    """
    cv2 = _cv2()
    np = _numpy()
    source = np.array(face.landmarks[:5], dtype=np.float32)
    destination = np.array(ARCFACE_TEMPLATE, dtype=np.float32)
    if output_size != 112:
        destination *= output_size / 112.0
    matrix, _ = cv2.estimateAffinePartial2D(source, destination, method=cv2.LMEDS)
    if matrix is None:
        return crop_face_without_alignment(image, face, output_size)
    return cv2.warpAffine(
        image,
        matrix,
        (output_size, output_size),
        flags=cv2.INTER_LINEAR,
        borderValue=0,
    )


def crop_face_without_alignment(image: Any, face: DetectedFace, output_size: int = 112) -> Any:
    """
    Crop the face directly from its bounding box without alignment.
    Used as a fallback when facial landmarks are unavailable or
    alignment fails. The cropped face is resized to the required
    output size.
    """
    cv2 = _cv2()
    height, width = image.shape[:2]
    x1 = max(0, face.box.x)
    y1 = max(0, face.box.y)
    x2 = min(width, face.box.x + face.box.width)
    y2 = min(height, face.box.y + face.box.height)
    if x2 <= x1 or y2 <= y1:
        raise InputImageError("Invalid face box for crop")
    crop = image[y1:y2, x1:x2]
    return cv2.resize(crop, (output_size, output_size), interpolation=cv2.INTER_AREA)


def _cv2() -> Any:
    try:
        import cv2

        return cv2
    except ImportError as exc:
        raise RuntimeError(
            "OpenCV is required for image processing. Install with: "
            "pip install opencv-python-headless"
        ) from exc


def _numpy() -> Any:
    try:
        import numpy

        return numpy
    except ImportError as exc:
        raise RuntimeError("NumPy is required for image alignment. Install with: pip install numpy") from exc
