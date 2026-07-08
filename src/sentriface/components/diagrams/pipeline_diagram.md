# Face Recognition Pipeline (SCRFD + ArcFace + ONNX Runtime)

A lightweight CPU-based face recognition pipeline built using **SCRFD** for face detection and **ArcFace** for face embedding. The pipeline uses **ONNX Runtime** for fast model inference and is designed with a modular architecture so that detectors, embedders, or runtime backends can be replaced independently.

---

# Architecture Overview

```text
                         Image Path
                              │
                              ▼
                     load_bgr_image()
                              │
                              ▼
                        NumPy Image
                              │
          ┌───────────────────┴────────────────────┐
          │                                        │
          ▼                                        ▼
   Face Detection                          Face Recognition
      (SCRFD)                                 (ArcFace)
```

---

# High-Level Pipeline

```text
                         image.jpg
                              │
                              ▼
                     load_bgr_image()
                              │
                              ▼
                        NumPy Image
                              │
        ┌─────────────────────┴─────────────────────┐
        │                                           │
        ▼                                           ▼
  Face Detection                             Face Recognition
     (SCRFD)                                   (ArcFace)
```

The pipeline consists of two independent stages:

1. **Face Detection**
   - Detects all faces present in the image.
   - Returns bounding boxes and facial landmarks.

2. **Face Recognition**
   - Crops each detected face.
   - Converts it into a normalized **512-dimensional embedding**.
   - Embeddings can later be compared using cosine similarity.

---

# Face Detection Pipeline (SCRFD)

```text
Image
 │
 ▼
Letterbox Resize
 │
 ▼
Tensor Conversion
 │
 ▼
SCRFD ONNX Model
 │
 ▼
Raw Outputs
 │
 ▼
Decode Predictions
 │
 ▼
Non-Max Suppression
 │
 ▼
Restore Original Coordinates
 │
 ▼
DetectedFace[]
```

---

## Detailed Detection Flow

```text
image.jpg
    │
    ▼
load_bgr_image()
    │
    ▼
NumPy Image (H × W × 3)
    │
    ▼
_scrfd_letterbox()
    │
    ├── Resize while preserving aspect ratio
    └── Add black padding
    │
    ▼
640 × 640 Image
    │
    ▼
_detector_tensor()
    │
    ├── BGR → RGB
    ├── uint8 → float32
    ├── Normalize to [-1,1]
    ├── HWC → CHW
    ├── Add Batch Dimension
    └── Make Memory Contiguous
    │
    ▼
Tensor (1 × 3 × 640 × 640)
    │
    ▼
OnnxRuntimeSession.run()
    │
    ▼
SCRFD ONNX Model
    │
    ▼
Raw Model Outputs
(scores, boxes, landmarks)
    │
    ▼
_decode_scrfd()
    │
    ├── Feature Map Decoder
    └── Simple Detection Decoder
    │
    ▼
Anchor Generation
    │
    ▼
Bounding Box Decoding
    │
    ▼
Landmark Decoding
    │
    ▼
Sort by Confidence
    │
    ▼
Non-Max Suppression
    │
    ▼
Restore Original Coordinates
    │
    ▼
List<DetectedFace>
```

---

# Face Recognition Pipeline (ArcFace)

For every detected face:

```text
DetectedFace
      │
      ▼
crop_face()
      │
      ▼
Aligned Face (112 × 112)
      │
      ▼
_arcface_tensor()
      │
      ├── BGR → RGB
      ├── uint8 → float32
      ├── Normalize to [-1,1]
      ├── HWC → CHW
      ├── Add Batch Dimension
      └── Make Memory Contiguous
      │
      ▼
Tensor (1 × 3 × 112 × 112)
      │
      ▼
OnnxRuntimeSession.run()
      │
      ▼
ArcFace ONNX Model
      │
      ▼
Embedding (1 × 512)
      │
      ▼
Flatten
      │
      ▼
Normalize
      │
      ▼
512-D Unit Vector
```

---

# Data Shape Evolution

## Detection

```text
Input Image
1920 × 1080 × 3

        │

        ▼

Letterbox

        │

        ▼

640 × 640 × 3

        │

        ▼

Tensor

1 × 3 × 640 × 640

        │

        ▼

SCRFD

        │

        ▼

Scores       (12800)
Boxes        (12800 × 4)
Landmarks    (12800 × 10)

        │

        ▼

DetectedFace[]
```

---

## Recognition

```text
DetectedFace

      │

      ▼

Face Crop

112 × 112 × 3

      │

      ▼

Tensor

1 × 3 × 112 × 112

      │

      ▼

ArcFace

      │

      ▼

1 × 512

      │

      ▼

Flatten

      │

      ▼

512

      │

      ▼

Normalize

      │

      ▼

Embedding
```

---

# Class Architecture

```text
                   +---------------------------+
                   |  OnnxScrfdDetector        |
                   +-------------+-------------+
                                 |
                                 | uses
                                 ▼
                    +---------------------------+
                    |  OnnxRuntimeSession       |
                    +-------------+-------------+
                                  |
                                  ▼
                          ONNX Runtime
                                  |
                                  ▼
                           SCRFD Model
```

```text
                   +---------------------------+
                   | OnnxArcFaceEmbedder       |
                   +-------------+-------------+
                                 |
                                 | uses
                                 ▼
                    +---------------------------+
                    |  OnnxRuntimeSession       |
                    +-------------+-------------+
                                  |
                                  ▼
                          ONNX Runtime
                                  |
                                  ▼
                          ArcFace Model
```

---

# Responsibility of Each Component

| Component | Responsibility |
|-----------|----------------|
| `OnnxRuntimeSession` | Loads ONNX model and performs inference |
| `OnnxScrfdDetector` | Face detection pipeline |
| `_scrfd_letterbox()` | Resize while preserving aspect ratio |
| `_detector_tensor()` | Convert image into detector tensor |
| `_decode_scrfd()` | Decode SCRFD outputs |
| `_anchor_centers()` | Generate feature map anchors |
| `_distance_to_box()` | Decode bounding boxes |
| `_distance_to_landmarks()` | Decode facial landmarks |
| `_nms()` | Remove duplicate detections |
| `_unletterbox_box()` | Restore coordinates to original image |
| `crop_face()` | Crop and align face |
| `_arcface_tensor()` | Convert face crop into ArcFace tensor |
| `_flatten()` | Flatten network output |
| `_normalize()` | Produce unit-length embedding |
| `OnnxArcFaceEmbedder` | Generate 512-dimensional face embedding |

---

# Runtime Flow

```text
Image
   │
   ▼
Detector
   │
   ▼
Detected Faces
   │
   ▼
Crop Each Face
   │
   ▼
ArcFace
   │
   ▼
512-D Embeddings
   │
   ▼
Cosine Similarity
```

---

# Design Principles

The project follows several software engineering principles:

- Layered architecture
- Processing pipeline architecture
- Composition over inheritance
- Separation of concerns
- Reusable utility modules
- ONNX Runtime abstraction through a dedicated wrapper

---

# Current Architecture

```text
                Application
                     │
                     ▼
        ┌───────────────────────────┐
        │   OnnxScrfdDetector       │
        └─────────────┬─────────────┘
                      │
                      ▼
           OnnxRuntimeSession
                      │
                      ▼
               ONNX Runtime
                      │
                      ▼
                SCRFD Model
```

```text
                Application
                     │
                     ▼
       ┌────────────────────────────┐
       │ OnnxArcFaceEmbedder        │
       └─────────────┬──────────────┘
                     │
                     ▼
          OnnxRuntimeSession
                     │
                     ▼
              ONNX Runtime
                     │
                     ▼
              ArcFace Model
```

---

# End-to-End System

```text
image.jpg
    │
    ▼
load_bgr_image()
    │
    ▼
Letterbox
    │
    ▼
Detector Tensor
    │
    ▼
SCRFD ONNX Runtime
    │
    ▼
Decode
    │
    ▼
Non-Max Suppression
    │
    ▼
DetectedFace[]
    │
    ├─────────────────────────────────────┐
    │                                     │
    ▼                                     ▼
crop_face()                       crop_face()
    │                                     │
    ▼                                     ▼
ArcFace Tensor                   ArcFace Tensor
    │                                     │
    ▼                                     ▼
ArcFace Runtime                  ArcFace Runtime
    │                                     │
    ▼                                     ▼
Embedding 1                     Embedding 2
          \                     /
           \                   /
            ▼                 ▼
          Cosine Similarity / Face Matching
```

---

# Future Improvements

Introduce a high-level orchestration layer that encapsulates the complete face recognition workflow.

```text
                FaceRecognitionPipeline
                         │
          ┌──────────────┼──────────────┐
          │              │              │
          ▼              ▼              ▼
 OnnxScrfdDetector   crop_face()   OnnxArcFaceEmbedder
```

This would simplify the public API to:

```python
pipeline = FaceRecognitionPipeline(...)

results = pipeline.process(image_path)
```

instead of manually coordinating the detector and embedder.

---

# Future Enhancements

- Batch inference support
- GPU execution provider (CUDA / TensorRT)
- Multiple detector backends
- Multiple embedding backends
- Face alignment improvements
- Model configuration through YAML
- Tracking support for video streams
- End-to-end `FaceRecognitionPipeline`
- Performance benchmarking
- Unit and integration tests