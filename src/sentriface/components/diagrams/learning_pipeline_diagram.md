# High-Level Architecture
```text
                    Image Path
                        │
                        ▼
               load_bgr_image()
                        │
                        ▼
                  BGR NumPy Image
                        │
          ┌─────────────┴─────────────┐
          │                           │
          ▼                           ▼
   Face Detection              Face Recognition
      (SCRFD)                    (ArcFace)
```

## Complete Pipeline

```text
                             image.jpg
                                 │
                                 ▼
                      load_bgr_image(image_path)
                                 │
                                 ▼
                  NumPy Image (H × W × 3, BGR)
                                 │
                                 ▼
                [    FACE DETECTION (SCRFD)    ]
                                 │
                                 ▼
                  _scrfd_letterbox(image, input_size)
                                 │
               Resize while maintaining aspect ratio
                                 │
                                 ▼
                     Add black padding (Letterbox)
                                 │
                                 ▼
                  640×640 (or model input size)
                                 │
                                 ▼
                    _detector_tensor(prepared)
                                 │
         BGR → RGB
         uint8 → float32
         Normalize to [-1,1]
         HWC → CHW
         Add batch dimension
         Make contiguous
                                 │
                                 ▼
                     Tensor (1×3×640×640)
                                 │
                                 ▼
                  OnnxRuntimeSession.run(tensor)
                                 │
                                 ▼
                     SCRFD ONNX Neural Network
                                 │
                                 ▼
 Raw outputs
 (scores, bounding boxes, landmarks)
                                 │
                                 ▼
                     _decode_scrfd(outputs)
                                 │
             ┌───────────────────┴──────────────────┐
             │                                      │
             ▼                                      ▼
   _decode_scrfd_feature_maps()        _decode_simple_detections()
             │
             ▼
      _infer_scrfd_input_size()
             │
             ▼
       _anchor_centers()
             │
             ▼
     Decode distance predictions
             │
             ▼
      _distance_to_box()
             │
             ▼
 _distance_to_landmarks() (optional)
             │
             ▼
      Generate proposals
             │
             ▼
      Sort by confidence
             │
             ▼
             _nms()
             │
             ▼
    Remove duplicate detections
             │
             ▼
      _unletterbox_box()
             │
             ▼
 Map coordinates back to original image
             │
             ▼
        List< DetectedFace >
```

## Face Recognition Pipeline

```text
DetectedFace
      │
      ▼
crop_face(image, face)
      │
      ▼
Aligned Face
112×112×3
      │
      ▼
_arcface_tensor()
      │
BGR → RGB
uint8 → float32
Normalize
HWC → CHW
Batch Dimension
Contiguous
      │
      ▼
Tensor
1×3×112×112
      │
      ▼
OnnxRuntimeSession.run()
      │
      ▼
ArcFace ONNX Model
      │
      ▼
Output
1×512
      │
      ▼
_flatten()
      │
      ▼
512 values
      │
      ▼
_normalize()
      │
      ▼
Unit-Length Embedding
      │
      ▼
tuple[float, ...] (512D)
```

## Class Interaction Diagram

```text
                    OnnxScrfdDetector
                           │
                           │ creates
                           ▼
                 OnnxRuntimeSession
                           │
                           │ owns
                           ▼
                ONNX Runtime Session
                           │
                           ▼
                  SCRFD ONNX Model
```

### Similarily

```text
                 OnnxArcFaceEmbedder
                           │
                           │ creates
                           ▼
                 OnnxRuntimeSession
                           │
                           ▼
                  ArcFace ONNX Model
```

## Detection Flow

```text
Image
 │
 ▼
Letterbox
 │
 ▼
Tensor Conversion
 │
 ▼
SCRFD
 │
 ▼
Scores + Boxes + Landmarks
 │
 ▼
Decode
 │
 ▼
NMS
 │
 ▼
Restore Original Coordinates
 │
 ▼
DetectedFace
```

## Recognition Flow

```text
DetectedFace
 │
 ▼
Crop Face
 │
 ▼
ArcFace Tensor
 │
 ▼
ArcFace Network
 │
 ▼
512-D Vector
 │
 ▼
Normalize
 │
 ▼
Embedding
```

## Data Shape Evolution

### Detection 

```text
Image
(1920×1080×3)
↓
Letterbox
↓
640×640×3
↓
Detector Tensor
↓
1×3×640×640
↓
SCRFD
↓
Scores
(12800)
Boxes
(12800×4)
Landmarks
(12800×10)
↓
Decode
↓
DetectedFace


### Recognition

Detected Face
↓
Crop
↓
112×112×3
↓
Tensor
↓
1×3×112×112
↓
ArcFace
↓
1×512
↓
Flatten
↓
512
↓
Normalize
↓
Embedding
```

## Pipeline Architecture

```text
Image
  │
  ▼
Letterbox
  │
  ▼
Tensor
  │
  ▼
Inference
  │
  ▼
Decode
  │
  ▼
NMS
  │
  ▼
DetectedFace
```

## architecture in UML-ish form
```text
                   +----------------------+
                   | OnnxScrfdDetector    |
                   +----------------------+
                   | runtime              |
                   | input_size           |
                   +----------+-----------+
                              |
                              |
                              v
                  +----------------------+
                  | OnnxRuntimeSession   |
                  +----------------------+
                  | session              |
                  | input_name           |
                  | input_shape          |
                  +----------+-----------+
                             |
                             |
                             v
                     +---------------+
                     | ONNX Runtime  |
                     +-------+-------+
                             |
                             |
                             v
                     +---------------+
                     | SCRFD Model   |
                     +---------------+
```

and

```text
                +-------------------------+
                | OnnxArcFaceEmbedder     |
                +-------------------------+
                | runtime                 |
                +-----------+-------------+
                            |
                            v
                 +----------------------+
                 | OnnxRuntimeSession   |
                 +----------------------+
                            |
                            v
                     ArcFace Model
```


## Architecture Maturity

```text
Script
   │
   ▼
Modular Code
   │
   ▼
Object-Oriented
   │
   ▼
Layered Architecture      ← You are here
   │
   ▼
Service-Oriented
   │
   ▼
Hexagonal / Clean Architecture
   │
   ▼
Distributed Microservices
```


## Entire system
```text
                         image.jpg
                             │
                             ▼
                    load_bgr_image()
                             │
                             ▼
                       NumPy Image
                             │
           ┌─────────────────┴─────────────────┐
           │                                   │
           ▼                                   ▼
      Letterbox                         Keep Original
           │
           ▼
   Detector Tensor
           │
           ▼
   SCRFD ONNX Runtime
           │
           ▼
   Raw Model Outputs
           │
           ▼
      Decode SCRFD
           │
           ▼
     Non-Max Suppression
           │
           ▼
     DetectedFace List
           │
      For each face
           │
           ▼
       crop_face()
           │
           ▼
     112×112 Face Crop
           │
           ▼
    ArcFace Tensor
           │
           ▼
   ArcFace ONNX Runtime
           │
           ▼
      512-D Feature
           │
           ▼
      Normalize
           │
           ▼
      Face Embedding
           │
           ▼
Cosine Similarity / Face Matching
```


# Current integration

`FaceEngine` is the top-level orchestrator. It coordinates detection, quality
checks, cropping/embedding, index search, reviewed persistence, request-scoped
metrics, and cancellation checkpoints. The detector and embedder remain
replaceable components behind that engine.