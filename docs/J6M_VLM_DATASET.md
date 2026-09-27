# CleanNav J6M VLM Dataset and Calibration Record

> Purpose: record the actual visual data used for the current PC baseline,
> Vision parity test and J6M PTQ calibration preparation.
>
> Last updated: 2026-09-27

---

## 1. Dataset role

The current dataset is used for:

~~~text
PC semantic validation
Vision interface inspection
Full-vs-single-tile comparison
PyTorch ↔ ONNX numerical parity
PTQ calibration-data generation
~~~

It is NOT used to fine-tune SmolVLM2.

No model training is currently performed on this dataset.

---

## 2. Current local dataset

Local path:

~~~text
/mnt/d/CleanNav_VLM/datasets/camvid_tiny/images
~~~

Current size:

~~~text
100 PNG road-scene images
~~~

Current internal name:

~~~text
camvid_tiny
~~~

`camvid_tiny` is a **CleanNav local engineering subset name**.

It is NOT an official CamVid dataset split named `camvid_tiny`, and team
members should not expect to download an official dataset with this exact
name.

The current local images are associated with the CamVid road-scene data
family and preserve CamVid-style sequence filenames.

The filenames correspond to CamVid-style sequences such as:

~~~text
0001TP
0006R0
0016E5
Seq05VD
~~~

The full original CamVid database is not committed into CleanNav GitHub.

---

## 3. CamVid provenance

Original project:

~~~text
Cambridge-driving Labeled Video Database
CamVid
~~~

Official University of Cambridge page:

~~~text
https://mi.eng.cam.ac.uk/research/projects/VideoRec/CamVid/
~~~

The original CamVid project contains road-driving image/video sequences
captured from a vehicle viewpoint and manually annotated semantic labels.

The current CleanNav repository only documents the local engineering
subset.

It does not redistribute the full external dataset.

---

## 4. Observed source-image properties

For the inspected current `camvid_tiny` images:

~~~text
SOURCE_IMAGE_MODE:
RGB

Representative source shape:
128 × 96
~~~

Example inspected files:

~~~text
0001TP_006750.png
0001TP_008070.png
0006R0_f01710.png
~~~

The SmolVLM2 official processor expands these images into its own
multi-tile visual representation.

---

## 5. Official SmolVLM2 processing

Current processor:

~~~text
AutoProcessor
HuggingFaceTB/SmolVLM2-500M-Video-Instruct
~~~

Configuration:

~~~text
do_image_splitting = true
do_normalize       = true
image_mean         = [0.5, 0.5, 0.5]
image_std          = [0.5, 0.5, 0.5]
do_pad             = true
size.longest_edge  = 2048
max_image_size     = 512
~~~

Observed output per source image:

~~~text
13 tiles
~~~

Processor tensor:

~~~text
[1, 13, 3, 512, 512]
float32
~~~

Tile composition:

~~~text
12 local tiles
+
1 global tile
~~~

All inspected tiles were fully valid:

~~~text
VALID_PIXEL_RATIO:
1.0

VALID_PATCH_RATIO:
1.0
~~~

---

## 6. Vision parity test dataset

Three source images were used for the current float ONNX numerical parity
gate:

~~~text
0001TP_006750.png
0001TP_008070.png
0006R0_f01710.png
~~~

Each source image produced:

~~~text
13 tiles
~~~

Total parity samples:

~~~text
3 × 13 = 39 tiles
~~~

Saved parity directory:

~~~text
/mnt/d/CleanNav_VLM/onnx/parity/
~~~

Artifacts:

~~~text
0001TP_006750_vision_parity.npz
0001TP_008070_vision_parity.npz
0006R0_f01710_vision_parity.npz
pytorch_reference_manifest.json
onnx_comparison_report.json
pytorch_reference_run.log
onnx_comparison_run.log
~~~

Global parity result:

~~~text
GLOBAL_MAX_ABS_ERROR:
0.000303268433

GLOBAL_MEAN_ABS_ERROR:
7.72870993e-06

GLOBAL_RMSE:
1.15176759e-05

GLOBAL_MEAN_COSINE:
0.999999999996

GLOBAL_MIN_COSINE:
0.999999999987
~~~

---

## 7. PTQ calibration source selection

Available local images:

~~~text
TOTAL_AVAILABLE_IMAGES:
100
~~~

The calibration source images were selected deterministically using
evenly spaced indices over the sorted filename list.

Selected images:

~~~text
source_index=0
0001TP_006750.png

source_index=11
0001TP_008940.png

source_index=22
0006R0_f02610.png

source_index=33
0016E5_01260.png

source_index=44
0016E5_06570.png

source_index=55
0016E5_08057.png

source_index=66
0016E5_08370.png

source_index=77
Seq05VD_f01260.png

source_index=88
Seq05VD_f03060.png

source_index=99
Seq05VD_f04980.png
~~~

Selection characteristics:

~~~text
deterministic
repeatable
non-random
distributed across the local 100-image list
~~~

---

## 8. PTQ calibration tensor generation

Each selected source image produces:

~~~text
13 fully-valid tiles
~~~

Total:

~~~text
10 source images
×
13 tiles
=
130 calibration tensors
~~~

Calibration output directory:

~~~text
/mnt/d/CleanNav_VLM/calibration/
smolvlm2_500m_official_processor_v1/npy/
~~~

Manifest:

~~~text
/mnt/d/CleanNav_VLM/calibration/
smolvlm2_500m_official_processor_v1/manifest.json
~~~

Per sample:

~~~text
shape:
[1, 3, 512, 512]

dtype:
float32
~~~

No `.bin` duplicates are currently generated.

---

## 9. Calibration statistics

Current generated calibration set:

~~~text
FULLY_VALID_TILES:
130

SKIPPED_PADDED_TILES:
0

TOTAL_CALIBRATION_FILES:
130

TOTAL_SIZE_MIB:
390.015869

GLOBAL_MIN:
-1

GLOBAL_MAX:
1

MEAN_OF_SAMPLE_MEANS:
-0.202588747

MEAN_OF_SAMPLE_STDS:
0.319618590
~~~

Save/reload validation:

~~~text
SAVE_RELOAD_CHECKED_TILES:
9

MAX_SAVE_RELOAD_ERROR:
0
~~~

The calibration-generation script validates tensor integrity before
accepting samples. No NaN/Inf validation failure was reported in the
current successful calibration run.

---

## 10. Why official preprocessing is required

The final CleanNav calibration set is intentionally generated using the
same official SmolVLM2 processor used for runtime inference.

The earlier audited D-Robotics sample calibration script uses a different
preprocessing configuration.

Therefore CleanNav freezes the rule:

~~~text
Inference preprocessing
=
PTQ calibration preprocessing
~~~

Current normalized pixel range:

~~~text
approximately [-1, 1]
~~~

No additional clipping is applied.

---

## 11. Dataset files are not committed to GitHub

Do not commit:

~~~text
PNG image dataset
calibration .npy tensors
parity .npz tensors
large generated binary data
~~~

GitHub stores only:

~~~text
dataset identity
local path
source URLs
selected filenames
sampling rule
tensor contract
statistics
artifact manifest information
~~~

Large data remains under:

~~~text
D:\CleanNav_VLM\
~~~

---

## 12. Reproducibility requirements

If the local dataset is replaced or extended:

1. record the new dataset origin;
2. record the image count;
3. record the file list or manifest;
4. preserve deterministic calibration sampling;
5. rerun Vision processor inspection;
6. rerun padding-mask validation;
7. rerun PTQ calibration statistics;
8. record new hashes/manifests;
9. do not silently replace the current frozen calibration baseline.

Any future real-vehicle camera calibration dataset must be versioned
separately from:

~~~text
smolvlm2_500m_official_processor_v1
~~~
