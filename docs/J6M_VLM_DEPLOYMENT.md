# CleanNav J6M VLM Deployment

> Status: Host-side deployment preparation
> Target: Horizon Journey 6M / `nash-m`
> VLM: `HuggingFaceTB/SmolVLM2-500M-Video-Instruct`
> Runtime role: Shadow Semantic Observer
> Last updated: 2026-09-27

---

## 1. Purpose

This document records the engineering baseline, frozen interfaces,
toolchain, validation results and deployment roadmap for the CleanNav
J6M multimodal semantic perception module.

The goal is to deploy a lightweight Vision-Language Model on Horizon J6M
for high-level road-scene semantic understanding.

The VLM is not part of the low-level vehicle control loop.

Frozen safety architecture:

~~~text
Camera
  ↓
VLM Semantic Observation
  ↓
Natural-language Scene Description
  ↓
Lightweight Semantic Parser
  ↓
Deterministic Rule Engine
  ↓
Shadow Decision
  ↓
UI / Logging / Optional Mission-level Hint
~~~

The VLM must NOT directly publish or control:

~~~text
/cmd_vel
steering
throttle
brake
CAN command
~~~

The motion-control path remains:

~~~text
Navigation
  ↓
candidate control
  ↓
Safety Supervisor
  ↓
vehicle command
~~~

Therefore the VLM is defined as a:

**Shadow Semantic Observer**

rather than an end-to-end autonomous-driving controller.

---

## 2. System deployment architecture

Current architecture:

~~~text
Camera Frame
    ↓
Official SmolVLM2 Processor
    ↓
13 × image tiles
[1, 3, 512, 512]
    ↓
Vision Encoder + Connector
J6M BPU / HBM
    ↓
13 × [64, 960]
    ↓
Multimodal Prefix Assembly
    ↓
SmolVLM Transformer
    ├── Prefill
    ├── KV Cache
    └── Autoregressive Decode
    ↓
Natural-language Scene Description
    ↓
Lightweight Semantic Parser
    ↓
Deterministic Rule Table
    ↓
Shadow Decision
~~~

The deployment is intentionally decomposed into stages instead of
attempting to compile the complete VLM into one monolithic HBM.

Target stages:

~~~text
Stage 1: Vision Encoder + Connector
Stage 2: Transformer Prefill
Stage 3: Transformer Decode
Stage 4: LM head / token selection / tokenizer decode
~~~

Main engineering reasons:

- static-shape BPU compilation;
- independent PTQ validation;
- KV-cache reuse;
- autoregressive generation;
- stage-level latency profiling;
- stage-level HBM debugging;
- reduced coupling between Vision and Transformer deployment.

---

## 3. PC VLM baseline

PC baseline is complete and frozen.

Host:

~~~text
Windows 11
WSL2 Ubuntu 22.04
Python 3.10.12
NVIDIA RTX 2060 6 GB
CUDA through WSL
~~~

Main VLM environment:

~~~text
Torch:        2.7.1+cu128
TorchVision:  0.22.1+cu128
Transformers: 4.51.3
Accelerate:   1.15.0
Pillow:       12.3.0
Attention:    SDPA
Model dtype:  FP16 for PC runtime
~~~

Model:

~~~text
HuggingFaceTB/SmolVLM2-500M-Video-Instruct
~~~

Frozen prompt:

~~~text
Describe only the most important road situation ahead in a few words.
Mention left, right, or center only when it is clearly relevant.
~~~

Runtime design:

~~~text
Natural-language VLM output
        ↓
shadow_decision_rules.py
        ↓
deterministic semantic decision
~~~

The earlier complex structured-output prompt was rejected because the
500M model produced significantly more stable semantics when generating
short natural-language descriptions.

No second VLM pass is used.

---


### 3.1 Validation history and rejected structured-output path

The PC baseline was not obtained in a single step.

The following validation sequence was completed.

#### G1 — single-image semantic inference

Single-image SmolVLM2 inference was successfully executed on the RTX 2060.

Representative result:

~~~text
Prompt:
Describe only the important road situation ahead in a few words.

Example output:
A bus is approaching a traffic light.
~~~

Observed single-image inference was approximately:

~~~text
1.3–1.4 s
~~~

Peak GPU memory was approximately:

~~~text
1325 MB
~~~

This gate proved that the 500M-class VLM could run reliably on the current
PC baseline.

#### G2 — continuous 0.5 Hz inference

The model was then kept resident in GPU memory and executed continuously.

The original continuous test used approximately:

~~~text
10 frames
target frequency = 0.5 Hz
model load count = 1
~~~

Observed inference time was approximately:

~~~text
mean ≈ 913 ms
deadline misses = 0
~~~

This gate proved that repeated inference did not require model reload and
that the shadow-only 0.5 Hz target was feasible on the PC baseline.

#### G3 — complex structured schema experiment

A more complex prompt was evaluated in an attempt to make the 500M model
directly emit a strict structured decision schema.

This approach failed as an engineering baseline.

Observed behavior included outputs such as:

~~~text
YES
YES.
~~~

instead of the requested complete structured result.

Final structured parse result:

~~~text
0 / 20 successfully parsed frames
~~~

This was classified as a **prompt/schema robustness failure**, not as
evidence that the visual model lacked road-scene semantic capability.

The design was therefore changed from:

~~~text
VLM
→ exact complex schema
→ action
~~~

to:

~~~text
VLM
→ short natural-language semantics
→ deterministic parser
→ deterministic rule table
~~~

This rejected G3 path is intentionally documented so that future team
members do not repeat the same exact-schema experiment without a specific
reason.

#### G3-lite — frozen semantic-observer baseline

The final G3-lite architecture is:

~~~text
Natural-language scene description
        ↓
simple semantic parser
        ↓
deterministic rule table
~~~

Final 20-frame event distribution:

~~~text
PERSON    5
CYCLIST   1
VEHICLE  12
OBSTACLE  0
CLEAR     1
UNKNOWN   1
~~~

Final 20-frame action distribution:

~~~text
YIELD_OR_STOP      6
SLOW_OR_YIELD     12
CONTINUE           1
HOLD_AND_OBSERVE   1
~~~

Final performance:

~~~text
Mean inference:
934.01 ms

Median inference:
999.77 ms

P95 inference:
1058.03 ms

Mean total:
1165.41 ms

P95 total:
1293.64 ms

Deadline misses:
0

Max GPU memory:
1326.36 MB

Model load count:
1
~~~

Frozen PC log:

~~~text
/mnt/d/CleanNav_VLM/logs/g3lite_shadow_20260926_231233.jsonl
~~~

The G3-lite PC baseline is considered frozen. Further work should focus
on J6M deployment rather than additional PC prompt polishing.


## 4. Shadow semantic decision

Current semantic event classes:

~~~text
PERSON
CYCLIST
VEHICLE
OBSTACLE
CLEAR
UNKNOWN
~~~

Representative rule mapping:

~~~text
PERSON
→ YIELD_OR_STOP

CYCLIST
→ YIELD_OR_STOP

VEHICLE
→ SLOW_OR_YIELD

CLEAR
→ CONTINUE

UNKNOWN
→ HOLD_AND_OBSERVE
~~~

This rule layer is deterministic.

The VLM performs semantic observation.

The rule layer performs interpretable high-level action suggestion.

---

## 5. PC baseline performance

Frozen G3-lite baseline:

~~~text
Mean inference:
934.01 ms

Median inference:
999.77 ms

P95 inference:
1058.03 ms

Mean total:
1165.41 ms

P95 total:
1293.64 ms

Deadline misses:
0

Max GPU memory:
1326.36 MB

Model load count:
1
~~~

The current target semantic-observer frequency is approximately:

~~~text
0.5 Hz
~~~

This is acceptable because the module is shadow-only and not a
high-frequency vehicle controller.

---

## 6. Official SmolVLM2 processor interface

The real processor interface was measured from the current model instead
of inferred from configuration files.

For the current road-image test set:

~~~text
SOURCE IMAGE
    ↓
Official AutoProcessor
    ↓
pixel_values:
[1, 13, 3, 512, 512]
~~~

The processor produces:

~~~text
12 local tiles
+
1 global tile
=
13 tiles / image
~~~

Per tile:

~~~text
Vision input:
[1, 3, 512, 512]

Vision last_hidden_state:
[1, 1024, 768]

Connector output:
[1, 64, 960]
~~~

Therefore:

~~~text
13 × 64
=
832 visual embedding tokens / frame
~~~

Current processor configuration:

~~~text
do_image_splitting = true
do_resize          = true
size.longest_edge  = 2048
max_image_size     = 512
do_pad             = true
do_normalize       = true
image_mean         = [0.5, 0.5, 0.5]
image_std          = [0.5, 0.5, 0.5]
~~~

The tested tiles were all fully valid:

~~~text
VALID_PIXEL_RATIO = 1.0
VALID_PATCH_RATIO = 1.0
~~~

No padding was present in the current tested single-image path.

---

## 7. Single-tile deployment experiment

A reduced deployment profile was evaluated:

~~~text
Full processor:
13 tiles
832 visual tokens

Single-tile profile:
1 tile
64 visual tokens
~~~

20-frame comparison:

~~~text
FULL
mean inference:
922.32 ms

SINGLE
mean inference:
790.50 ms

Speedup:
1.167×
~~~

However semantic consistency was poor:

~~~text
EVENT_MATCH_RATE:
0.550

ACTION_MATCH_RATE:
0.550
~~~

Observed degradation included:

- missed cyclist;
- missed pedestrian;
- CLEAR → VEHICLE mismatch;
- hallucinated pedestrian-crossing semantics.

Decision:

~~~text
Single-tile deployment profile:
REJECTED as current deployment baseline
~~~

Frozen deployment candidate:

~~~text
Full official 13-tile processor
~~~

Single-tile remains only as a future performance fallback experiment.

---

## 8. Vision float ONNX baseline

Current Vision float baseline:

~~~text
/mnt/d/CleanNav_VLM/onnx/reference/
smolvlm2_500M_visual_resampler_reference.onnx
~~~

SHA256:

~~~text
88aeb0ddf31104bc3f2071e952df3f0be467a409a936fb80c0eb0738f89c4b6c
~~~

ONNX metadata:

~~~text
IR version:
6

Opset:
11

Input:
name  = image
shape = [1, 3, 512, 512]
dtype = float32

Output:
name  = image_embeds
shape = [1, 64, 960]
dtype = float32
~~~

Validation:

~~~text
ONNX checker:
PASS

ONNX shape inference:
PASS
~~~

The model contains:

~~~text
Vision Encoder
+
Connector / Resampler
~~~

This artifact is derived from the D-Robotics SmolVLM PTQ reference path.

---

## 9. PyTorch ↔ ONNX numerical parity

The Vision float ONNX was validated against official Hugging Face
PyTorch Vision + Connector execution.

Test set:

~~~text
3 real road images
×
13 official processor tiles
=
39 real visual tiles
~~~

Global result:

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

Conclusion:

~~~text
Official PyTorch Vision
≈
D-Robotics float ONNX
~~~

The reference ONNX is therefore frozen as the current:

~~~text
Vision Float Baseline
~~~

No custom Vision ONNX re-export is currently required.

---

## 10. PTQ calibration dataset

The PTQ calibration data is generated from the official SmolVLM2
AutoProcessor.

Generic ImageNet preprocessing is NOT used.

Calibration path:

~~~text
/mnt/d/CleanNav_VLM/calibration/
smolvlm2_500m_official_processor_v1/
~~~

Source engineering dataset:

~~~text
/mnt/d/CleanNav_VLM/datasets/camvid_tiny/images
~~~

Current local dataset:

~~~text
100 road-scene PNG images
CamVid-derived engineering subset
~~~

Calibration sampling:

~~~text
10 deterministic evenly-spaced source images
×
13 official processor tiles
=
130 calibration tensors
~~~

Per tensor:

~~~text
shape:
[1, 3, 512, 512]

dtype:
float32
~~~

Calibration statistics:

~~~text
TOTAL_CALIBRATION_FILES:
130

TOTAL_SIZE:
390.015869 MiB

GLOBAL_MIN:
-1

GLOBAL_MAX:
1

MEAN_OF_SAMPLE_MEANS:
-0.202588747

MEAN_OF_SAMPLE_STDS:
0.319618590
~~~

Validation:

~~~text
FULLY_VALID_TILES:
130

SKIPPED_PADDED_TILES:
0

NaN:
0

Inf:
0

SAVE_RELOAD_MAX_ERROR:
0
~~~

Detailed dataset and calibration manifest information is maintained in:

~~~text
docs/J6M_VLM_DATASET.md
~~~

---

## 11. Docker / host environment

Docker Desktop has been installed with WSL2 backend.

Verified:

~~~text
Docker Desktop:
4.92.0

Docker Engine:
29.8.0

WSL:
2.7.14

Ubuntu:
22.04

WSL Docker CLI:
PASS

hello-world:
PASS

GPU passthrough:
PASS
~~~

Container GPU test detected:

~~~text
NVIDIA GeForce RTX 2060
Compute Capability 7.5
~~~

WSL NVIDIA environment:

~~~text
Driver:
570.86.17

Windows NVIDIA Driver:
572.47

CUDA reported:
12.8
~~~

Recommended large-data locations:

~~~text
D:\Docker\
D:\CleanNav_VLM\
~~~

Do not move large models, ONNX files, calibration data or Docker images
into the WSL root filesystem unless required.

---

## 12. Horizon OpenExplorer

Target BPU architecture:

~~~text
J6M
march = nash-m
~~~

Selected first deployment toolchain:

~~~text
Horizon OpenExplorer J6 v3.5.0
Python 3.10 generation
~~~

The first deployment uses 3.5.0 because the audited EdgeFM J6M SmolVLA
path was validated with the same OpenExplorer generation.

Downloaded official artifacts:

~~~text
D:\CleanNav_VLM\toolchains\OpenExplorer\3.5.0\
~~~

Files:

~~~text
docker_open_explorer_ubuntu_22_j6_gpu_v3.5.0.tar

horizon_j6_open_explorer_v3.5.0-py310_20250927.tar
~~~

Expected component generation based on the official 3.5.0 download page:

~~~text
HBDK4 compiler:
4.5.5

HMCT:
2.5.6
~~~

Actual runtime versions must still be verified after loading the Docker
image.

Current status:

~~~text
OpenExplorer 3.5.0 full package:
DOWNLOADED

OpenExplorer 3.5.0 GPU Docker image:
DOWNLOADED

Docker image load:
NOT YET VERIFIED

hb_compile / HMCT / HBDK runtime audit:
NOT YET VERIFIED

nash-m model compilation:
NOT YET VERIFIED
~~~

The existence of the downloaded artifacts must not be treated as proof
that the host compiler environment or `nash-m` compilation has already
passed.

Important:

J6 OpenExplorer is obtained through the official OpenExplorer download
portal and loaded locally.

Do NOT assume the J6 Docker image can be pulled anonymously from Docker
Hub.

---

## 13. External engineering references

### 13.1 EdgeFM

Repository:

~~~text
https://github.com/windog-labs/edge-fm-x
~~~

Pinned audited commit:

~~~text
83251d56a1a682729ef145535f6c4de23a4ce250
~~~

CleanNav reuse scope:

~~~text
Transformer stage abstraction
KV cache
prefill/decode separation
compile_spec
Horizon graph rewrite
attention-mask rewrite
RoPE rewrite
aarch64 runtime structure
J6M C++ runtime
~~~

Not used as the CleanNav control policy:

~~~text
Action Expert
flow matching
action chunk generation
low-level action control
~~~

EdgeFM does not replace Horizon OpenExplorer.

It prepares and adapts models, then invokes the Horizon compiler
toolchain.

---


### 13.1.1 EdgeFM scope boundary

The audited EdgeFM SmolVLA J6M implementation must NOT be described as a
complete SmolVLA or complete SmolVLM2 deployment.

The audited Horizon path currently provides the Transformer-side
engineering foundation:

~~~text
Prefill:
prefix embeddings / masks / positions
→ Transformer layers
→ prefix KV cache

Decode:
suffix embeddings / masks / positions
+
prefix KV
→ expert_hidden
~~~

The audited EdgeFM path does NOT by itself include the full CleanNav
semantic chain.

It does not directly provide:

~~~text
camera preprocessing
Vision Encoder
Connector / Resampler
image tile assembly
complete natural-language token logits
LM-head token generation loop
sampling / greedy decoding
EOS handling
tokenizer decode
full image → language CleanNav pipeline
~~~

It also contains SmolVLA Action-Expert concepts that CleanNav does not
require.

CleanNav therefore treats EdgeFM as a:

~~~text
Transformer deployment / KV-cache / Horizon runtime foundation
~~~

rather than a ready-made complete VLM application.

#### EdgeFM author-side J6M reference benchmark

The following numbers came from the audited EdgeFM J6M author-side
records and are external reference measurements, NOT CleanNav PC or J6M
measurements.

Prefill latency:

~~~text
prefix 512:
74.264 ms

prefix 1024:
248.272 ms

prefix 2048:
899.390 ms
~~~

Decode reference latency:

~~~text
prefix 512 / suffix 32:
12.511 ms

prefix 512 / suffix 64:
15.000 ms

prefix 1024 / suffix 32:
19.481 ms

prefix 1024 / suffix 64:
23.248 ms

prefix 2048 / suffix 32:
38.381 ms

prefix 2048 / suffix 64:
49.434 ms
~~~

Reference HBM sizes reported by the audited EdgeFM environment:

~~~text
Prefill p512:
~164 MiB

Prefill p1024:
~203 MiB

Prefill p2048:
~333 MiB

Decode:
approximately 103–116 MiB depending on configuration
~~~

These values are useful for architecture planning, but they must not be
presented as CleanNav measured performance.

The final CleanNav SmolVLM2 Transformer path still requires separate
host export, HBM compilation and physical J6M runtime validation.



### 13.1.2 Audited EdgeFM J6M stage contracts

The audited EdgeFM J6M path used the following host-side reference
toolchain generation:

~~~text
Python:
3.10

hb_compile:
3.5.3

HMCT:
2.5.6

HBDK:
4.5.5

target march:
nash-m
~~~

Audited prefill public interface:

~~~text
prefix_embeds:
[1, L, 960] float32

prefix_attention_mask:
[1, L, L] uint8

prefix_position_ids:
[1, L] int32

outputs:
prefix_kv_layer_0 ... prefix_kv_layer_15

per-layer KV:
[2, L, 5, 64] float32
~~~

Audited decode public interface:

~~~text
suffix_embeds:
[1, S, 720] float32

denoise_attention_mask:
[1, S, L+S] uint8

suffix_position_ids:
[1, S] int32

prefix_kv_layer_0 ... prefix_kv_layer_15:
[2, L, 5, 64] float32

output:
expert_hidden [1, S, 720] float32
~~~

These interfaces belong to the audited SmolVLA Transformer/Expert path.

They are engineering references for CleanNav and must not be copied
blindly as the final SmolVLM2 natural-language generation interface.

CleanNav still needs to expose the appropriate language-model hidden
state / logits path required for autoregressive text generation.


### 13.2 D-Robotics SmolVLM PTQ

Repository:

~~~text
https://github.com/D-Robotics-AI-Lab/SmolVLM_PTQ
~~~

Pinned audited commit:

~~~text
68601da027fccacdd0e2b7891e8df56beedb6547
~~~

CleanNav reuse scope:

~~~text
Vision + Connector float ONNX
Horizon PTQ reference
Vision hardware-oriented graph structure
~~~

The repository's original calibration preprocessing is NOT used as the
CleanNav final calibration pipeline.

CleanNav uses official SmolVLM2 preprocessing instead.

---

## 14. Official software and download URLs

### Horizon OpenExplorer

Homepage:

~~~text
https://oe.horizon.auto/
~~~

Official download page:

~~~text
https://oe.horizon.auto/download/oe
~~~

Current frozen initial target:

~~~text
J6 OpenExplorer 3.5.0
~~~

---

### Docker Desktop

Windows installation:

~~~text
https://docs.docker.com/desktop/setup/install/windows-install/
~~~

WSL2 backend:

~~~text
https://docs.docker.com/desktop/features/wsl/
~~~

---

### SmolVLM2

Model:

~~~text
https://huggingface.co/HuggingFaceTB/SmolVLM2-500M-Video-Instruct
~~~

---

### EdgeFM

~~~text
https://github.com/windog-labs/edge-fm-x
~~~

---

### D-Robotics SmolVLM PTQ

~~~text
https://github.com/D-Robotics-AI-Lab/SmolVLM_PTQ
~~~

---

### Horizon OE-Skills

~~~text
https://github.com/HorizonRobotics/OE-Skills
~~~

Useful for:

~~~text
HMCT
PTQ
HBDK
HBM compile
UCP inference
J6 deployment workflow
~~~

---

### CamVid

Original Cambridge CamVid project page:

~~~text
https://mi.eng.cam.ac.uk/research/projects/VideoRec/CamVid/
~~~

CleanNav does NOT currently redistribute the full CamVid dataset in
GitHub.

Only the local engineering subset and its manifests are documented.

---

## 15. Local workspace layout

Code:

~~~text
~/work/
├── j6m_vlm_demo/
├── edge-fm-x/
├── SmolVLM_PTQ/
└── .venv-onnx-tools/
~~~

Large artifacts:

~~~text
/mnt/d/CleanNav_VLM/
├── cache/
├── calibration/
│   └── smolvlm2_500m_official_processor_v1/
├── datasets/
│   └── camvid_tiny/
├── logs/
├── models/
├── onnx/
│   ├── parity/
│   └── reference/
└── toolchains/
    └── OpenExplorer/
        └── 3.5.0/
~~~

Do not commit the following to GitHub:

~~~text
*.onnx
*.hbm
*.npy
*.tar
*.tar.gz
model cache
OpenExplorer Docker images
full calibration tensor sets
~~~

Record instead:

~~~text
artifact filename
version
SHA256
source URL
generation command
validation result
~~~

---

## 16. Immediate next milestone — Vision HBM

Current milestone:

~~~text
J0-B7
OpenExplorer / Vision HBM
~~~

Planned sequence:

~~~text
OpenExplorer 3.5.0 Docker load
        ↓
environment audit
        ↓
verify:
hb_compile
HMCT
HBDK
GPU
nash-m
        ↓
Vision ONNX model check
        ↓
PTQ with official calibration tensors
        ↓
quantization accuracy validation
        ↓
HBDK / hb_compile
        ↓
Vision nash-m HBM
~~~

Target interface:

~~~text
Input:
float32 [1, 3, 512, 512]

Output:
[1, 64, 960]
~~~

Current full processor workload:

~~~text
13 Vision HBM executions / frame
~~~

HBM compilation on PC only proves:

~~~text
Host-side J6M target compilation PASS
~~~

It does NOT prove real-board deployment.

---

## 17. Transformer roadmap

After Vision HBM succeeds:

~~~text
13 × [64, 960]
        ↓
Multimodal Embedding Assembly
        ↓
Transformer Prefill HBM
        ↓
Prefix KV Cache
        ↓
Transformer Decode HBM
        ↓
LM Head
        ↓
Token Selection
        ↓
Tokenizer Decode
        ↓
Natural-language Description
~~~

Main engineering reference:

~~~text
EdgeFM
~~~

Reusable concepts:

~~~text
prefill/decode separation
KV request cache
static-shape stage specification
J6M-safe attention mask
RoPE rewrite
CPU tensor transfer
aarch64 runtime packaging
~~~

CleanNav does NOT require:

~~~text
Action Expert
flow matching
action chunks
low-level action generation
~~~

The required model output is:

~~~text
Natural-language road-scene semantics
~~~

---


### 17.1 Historical verified J6M system baseline

CleanNav has previously executed real J6M HIL software on the target
controller.

The historically verified board baseline is:

~~~text
Hardware:
SOLING J6M_SIP_Matrix_V1.1

Native OS:
Debian 12

Architecture:
ARM64 / aarch64

Historical kernel:
6.1.158-rt58
~~~

The native J6M root filesystem uses overlayroot and should not be treated
as a general Ubuntu development machine.

Persistent writable storage:

~~~text
/map
~~~

The historical CleanNav ROS2 runtime is located in:

~~~text
/map/cleannav_runtime/jammy
~~~

Runtime stack:

~~~text
J6M native Debian 12
        ↓
Jammy chroot
        ↓
Ubuntu 22.04 ARM64
        ↓
ROS2 Humble
        ↓
CleanNav runtime
~~~

Historical J6M CleanNav workspace:

~~~text
/root/cleannav_hil_ws
~~~

Historical network configuration:

~~~text
J6M:
192.168.8.10/24

PC / WSL:
192.168.8.20/24
~~~

The competition HIL path intentionally avoided relying on unstable
cross-machine ROS2 DDS discovery.

Verified operational transport:

~~~text
APP / Voice
    ↓
TaskCommand
    ↓
J6M Mission Manager
    ↓
HTTP/TCP
    ↓
PC Navigation / Safety / Gazebo
    ↓
Navigation Result
    ↓
J6M
~~~

Historical Mission Manager HIL endpoint:

~~~text
http://192.168.8.10:18081
~~~

This historical baseline proves that CleanNav has already executed:

~~~text
ARM64 J6M runtime
Ubuntu 22.04 Jammy environment
ROS2 Humble
CleanNav interfaces
Mission Manager
HTTP/TCP HIL transport
~~~

However it does NOT yet prove that the current board contains the exact
BPU runtime binaries and ABI required by the new VLM deployment.

When the board returns, the following must be audited again before HBM
runtime integration:

~~~text
/dev/bpu*
hrt_model_exec
libdnn
libhbrt
libhbucp
OpenExplorer / runtime ABI compatibility
~~~

Do not reinstall the native J6M operating system or blindly install ROS
packages into the Debian root filesystem.

Large VLM runtime artifacts should preferentially use persistent `/map`
storage.


## 18. J6M real-board validation

The following must wait until the physical J6M board is available.

Board runtime audit:

~~~text
/dev/bpu*
hrt_model_exec
libdnn
libhbrt
libhbucp
runtime ABI/version
~~~

Required gates:

~~~text
1. HBM model_info
2. HBM load
3. single-tile Vision execution
4. output shape validation
5. Vision numerical sanity
6. 13-tile execution
7. Transformer prefill
8. Transformer decode
9. real image → natural language
10. 0.5 Hz sustained execution
11. memory monitoring
12. thermal monitoring
13. camera integration
14. ROS2 integration
~~~

Do not label PC HBM compilation as successful board deployment.

---

## 19. Final ROS2 integration

Target interface:

~~~text
Camera
  ↓
J6M VLM Runtime
  ↓
/j6m_vlm/decision
  ↓
logging / visualization / mission-level consumer
~~~

Frozen control boundaries:

~~~text
VLM does not publish /cmd_vel
APP does not publish /cmd_vel
Voice does not publish /cmd_vel
Mission Manager does not publish /cmd_vel
Safety Supervisor remains the final motion gate
~~~

---

## 20. Current gate status

~~~text
G0      PC environment                    PASS
G1      Single-image SmolVLM              PASS
G2      Continuous 0.5 Hz                 PASS
G3-lite Shadow semantic decision          PASS / FROZEN

J0-B    EdgeFM J6M audit                   PASS
J0-B2   Official Vision interface          PASS
J0-B3   Single-tile deployment test        REJECTED
J0-B4   Mask + reference ONNX audit        PASS
J0-B5A  PyTorch ↔ ONNX parity              PASS
J0-B6A  Official PTQ calibration dataset   PASS

Docker Desktop                             PASS
WSL2 Docker integration                    PASS
Docker GPU passthrough                      PASS

OpenExplorer 3.5.0 full package            DOWNLOADED
OpenExplorer 3.5.0 GPU Docker              DOWNLOADED

OpenExplorer container audit               TODO
Vision PTQ                                 TODO
Vision nash-m HBM                          TODO
Transformer HBM                            TODO
J6M real-board runtime                     TODO
ROS2 VLM integration                       TODO
~~~

---

## 21. Team handoff rules

Before changing the model architecture or preprocessing:

1. Read this document.
2. Do not modify the frozen PC baseline without a new validation gate.
3. Do not replace official SmolVLM2 preprocessing with generic ImageNet preprocessing.
4. Do not silently change the Vision tensor contract.
5. Keep large artifacts on D:.
6. Record ONNX and HBM SHA256 hashes.
7. Record OpenExplorer / HMCT / HBDK versions.
8. Distinguish clearly between:
   - host compile PASS;
   - board runtime PASS;
   - HIL PASS;
   - real-vehicle PASS.
9. Do not introduce low-level VLM control into the frozen Safety architecture.
10. Prefer reproducible deterministic tests before performance optimization.

Current priority:

~~~text
Vision Float Baseline
→ OpenExplorer Audit
→ PTQ
→ nash-m HBM
→ J6M Runtime
→ Transformer
→ Full Semantic Chain
~~~

Do not expand the current scope into end-to-end VLA vehicle control.
