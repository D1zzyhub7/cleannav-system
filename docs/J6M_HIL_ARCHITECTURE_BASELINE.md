# CleanNav J6M Algorithm HIL Architecture Baseline

**Status:** M0 FROZEN — component SHAs and local tag finalized
**Baseline:** `competition-hil-baseline-20260921`
**Date:** 2026-09-21

> The earlier physical Navigation Algorithm HIL plan and its DDS experiments are
> retained below as historical evidence. They are not the M0 operational path.

## 0. M0 Competition HIL operational path

The current repeatable competition path is:

```text
Phone APP
    -> PC HMI Gateway
    -> HTTP/TCP
    -> J6M Mission Manager HTTP ingress
    -> J6 navigation events/results over HTTP
    -> PC HIL Execution Bridge
    -> frozen task30 PC Showcase runtime
    -> Nav2 / Safety / Gazebo
```

The current Voice path is separate from the APP path:

```text
PC microphone
    -> SenseVoice / VoicePolicy
    -> TaskCommand(source=VOICE)
    -> HTTP HIL
    -> J6M Mission Manager
```

The boundaries are fixed for M0:

- J6 Mission Manager is the external mission authority.
- PC Navigation/Safety is the simulation execution adapter.
- PC Voice still produces the formal `TaskCommand`; HTTP is only its HIL transport.
- PC HMI Gateway forces `source=APP=2` and does not publish `/cmd_vel`.
- The PC physical leaf-completion latch is Showcase-only semantics.
- M0 is a Competition HIL baseline, not the final vehicle architecture.

Cross-machine DDS was tested experimentally. Due to WSL/Windows/Hyper-V UDP
inbound and discovery issues, DDS is marked `DEFERRED / EXPERIMENTAL` and is
not the M0 operational transport.

---

## 1. Frozen M0 Objective and Future Direction

M0 freezes a repeatable **Competition HIL** path without changing the verified
PC Showcase, Voice, Mission Manager or Navigation runtime contracts. Physical
J6M algorithm execution is a separate future track.

Future work is explicitly outside the current M0 capability:

1. M1 — APP HIL runtime completion;
2. M2 — SenseVoice / ASR to J6M BPU / HBM;
3. M3 — APP Gateway and Voice runtime J6-native;
4. M4 — real vehicle integration;
5. M5 — navigation hardening.

Perception remains part of the final vehicle architecture, but leaf/puddle perception is not the current critical path.

The project now prioritizes integration and verification over further architecture exploration.

---

## 2. Frozen HIL Definition

The historical J6M Algorithm HIL definition below is retained for future
physical-board work. It is not the current M0 Competition HIL baseline.

### PC side

The PC runs:

- Gazebo;
- simulated environment;
- Ackermann vehicle plant;
- simulated LiDAR;
- simulated camera when required;
- simulated odometry;
- simulation clock.

### J6M side

The physical J6M runs the algorithms under verification:

- Navigation;
- Safety Supervisor;
- Mission Manager in the later stage;
- APP / offline voice command integration in the later stage;
- perception when perception itself is being validated.

The required closed loop is:

```text
PC Simulator
    |
    | simulated sensors / environment
    v
Physical J6M
    |
    | algorithms execute on J6M
    v
vehicle command
    |
    v
PC Gazebo Ackermann plant
    |
    | updated state / sensors
    +------------------------> J6M
```

A PC-only algorithm run is SIL, not J6M HIL.

---

## 3. M0 Priority

```text
P0  formal interface and source identity
P1  PC Gazebo Showcase execution path
P2  J6 Mission Manager HTTP HIL ingress/events/results
P3  APP -> PC Gateway -> J6 HIL
P4  PC Voice -> TaskCommand -> J6 HIL
P5  reproducible evidence and component pinning
```

Physical J6M algorithm HIL remains a separate future track and must not change
the already-verified M0 PC Showcase or HIL contracts.

---

## 4. Deferred Work

The following are not part of the current critical path:

- complex camera-interface HIL;
- physical VIN / ISP / VIO injection;
- multi-camera perception;
- BEV perception;
- VLA or LLM deployment;
- custom transport variants outside the M0 HTTP/TCP path;
- physical CAN integration before Navigation HIL;
- PTP/gPTP tuning before functional HIL works;
- replacing Hybrid-A* or MPPI;
- custom NMPC / MPCC / CBF;
- creating new platform repositories without concrete need.

---

## 5. Historical J6M Algorithm HIL — deferred from M0

### PC provides

```text
/map
/scan
/odom
/tf
/tf_static
/clock
```

A direct `/goal_pose` is allowed during early proof.

PC runs:

```text
Gazebo
Ackermann vehicle simulation
LiDAR simulation
test map
simulation clock
```

PC must not run the Navigation algorithms claimed as J6M HIL.

### J6M runs

```text
/goal_pose
    ↓
CleanNav Hybrid Planner Bridge
    ↓
Nav2 ComputePathToPose
    ↓
Smac Hybrid-A*
    ↓
/cleannav/global_path
    ↓
CleanNav Path Executor
    ↓
Nav2 FollowPath
    ↓
MPPI Ackermann Controller
    ↓
/cleannav/cmd_vel_candidate
    ↓
CleanNav Safety Supervisor
    ↓
/cmd_vel
```

J6M `/cmd_vel` is returned to the PC.

The PC Ackermann plant consumes the command and produces new `/odom` and `/scan`.

---

## 6. Transport Baseline

M0 operational transport:

```text
HTTP/TCP over the reachable Ethernet/Wi-Fi path
```

Initial architecture:

```text
PC APP / Voice / HMI Gateway
    ↕
HTTP/TCP
    ↕
J6 Mission Manager HTTP HIL server
```

M0 requirements:

- reachable IP addresses;
- bounded HTTP timeout and retry behavior;
- idempotent command/event handling;
- explicit `TaskCommand` source and command identity preservation.

Historical DDS experiment:

```text
PC ROS 2 <-> Ethernet/DDS <-> J6M ROS 2
```

Status: `DEFERRED / EXPERIMENTAL / NOT M0 OPERATIONAL PATH`.
The historical cross-machine test did not deliver Fast DDS messages under the
WSL/Windows/Hyper-V network path; the historical evidence remains below.

---

## 7. J6M ROS 2 Rule

Keep these two statements separate:

```text
J6/J6M can run ROS 2.
```

and:

```text
The actual J6M image provides the exact ROS 2 environment
needed by the current CleanNav ROS 2 Humble workspace.
```

The second statement must be proven on the physical board.

Possible paths after the board audit:

```text
A. native compatible ROS 2 environment
B. install/build required ROS 2 packages
C. containerized ROS 2 environment
D. minimal compatibility / transport adaptation
```

---

## 8. Time Baseline

For functional HIL:

```text
PC Gazebo
    ↓
/clock
    ↓
J6M
```

J6M Navigation uses:

```text
use_sim_time=true
```

PTP/gPTP/PPS are deferred until functional HIL is working.

---

## 9. Frozen Navigation Architecture

Planner:

```text
Smac Hybrid-A*
```

Controller:

```text
MPPI Ackermann
```

Chain:

```text
Hybrid Planner Bridge
    ↓
Smac Hybrid-A*
    ↓
Path Executor
    ↓
FollowPath
    ↓
MPPI
    ↓
Safety Supervisor
```

Current HIL Navigation baseline:

```text
cleannav_navigation/launch/cleannav_ackermann_navigation.launch.py
```

This launch intentionally does not start:

- Gazebo;
- chassis simulation;
- localization;
- map_server;
- Mission Manager;
- HMI;
- perception.

---

## 10. Safety Boundary

Frozen authority:

```text
controller_server
    ↓
/cleannav/cmd_vel_candidate
    ↓
cleannav_safety_supervisor
    ↓
/cmd_vel
```

Default remains:

```text
block_all=true
```

J6M CAN frames and real chassis protocols must not be embedded in Safety Supervisor.

---

## 11. Mission Manager Boundary

Mission Manager remains platform independent.

It must not:

- publish `/cmd_vel`;
- contain J6M hardware settings;
- contain Ackermann geometry;
- contain CAN frames;
- directly control steering or wheel actuators.

Its chain remains:

```text
TaskCommand
    ↓
task interpretation
    ↓
execution state
    ↓
navigation request
```

Task Catalog remains the task expansion authority.

---

## 12. M0 Mission Manager + APP + Voice HIL

The current M0 path is:

```text
Phone APP
    ↓ HTTP
PC HMI Gateway
    ↓ HTTP `/task`
J6M Mission Manager
    ↓ HTTP `/nav/events` and `/nav/result`
PC HIL Execution Bridge
    ↓
frozen task30 PC Showcase runtime
    ↓
Nav2 / Safety / Gazebo
```

APP:

```text
Phone APP
    ↓ HTTP
PC HMI Gateway
    ↓ HTTP /task
J6M Mission Manager
```

The Gateway accepts `POST /api/tasks`, `GET /api/state`, `GET /api/map` and
`POST /api/emergency-reset`. It forwards APP tasks to the J6 `/task` ingress
and returns the upstream delivery result.
It forces `source=APP=2`; APP never publishes `/cmd_vel`.

Voice:

```text
PC microphone
    ↓
SenseVoice / VoicePolicy
    ↓
TaskCommand(source=VOICE)
    ↓ HTTP HIL adapter
J6 Mission Manager
```

Voice is not forwarded through the APP. J6-native Voice is an M2/M3 future
track and should preserve the formal Voice-to-TaskCommand boundary.

Historical future design:

```text
APP or Voice
    ↓
TaskCommand(task_id)
    ↓
Mission Manager on J6M
```

Offline voice:

```text
Offline Voice
    ↓
TaskCommand(task_id)
    ↓
Mission Manager
```

APP and voice must not create separate low-level control paths.

Offline voice must not directly map a phrase to `RESET_ESTOP`.

### M0 Verification Evidence

- Interfaces build/interface verification: `PASS`;
- Navigation config + scene: `49 passed`;
- NavigationFacade: `26 passed`;
- Navigation scene suite: `43 passed`;
- Navigation independent build: `6 packages finished`;
- RTAB: portable `38-line` config, machine path count `0`;
- Mission Manager: `584 passed`, `1 skipped`;
- Voice: `51 passed`;
- HMI Python: `19 passed`;
- HMI Flutter analyze/test/build: `UNVERIFIED` because Flutter/Dart SDK is unavailable.

### M0 Known Limitations

1. Flutter analyze/test/build: `UNVERIFIED` in the current WSL environment;
2. dedicated dynamic obstacle runtime: not separately validated;
3. near-goal MPPI behavior: deferred for hardening;
4. real vehicle calibration: not performed;
5. physical leaf completion: Competition Demo semantics only;
6. SenseVoice: currently PC-side;
7. J6M BPU/HBM: not implemented in M0;
8. cross-machine DDS: `DEFERRED / EXPERIMENTAL`;
9. current operational HIL transport: HTTP/TCP.

---

## 13. Perception Scope

Perception is not the current critical path.

Final chain:

```text
camera/image
    ↓
J6M perception
    ↓
CleaningTargetArray
    ↓
Mission Manager
```

Current perception scope is limited to task-relevant targets such as:

- fallen leaves;
- puddles.

If perception itself is claimed as J6M HIL, inference must execute on J6M.

Complex physical camera-interface HIL is not required for the current algorithm-HIL baseline.

---

## 14. SIL / HIL / Real Profiles

### SIL

```text
PC:
Simulator
Perception
Mission Manager
Navigation
Safety
```

### Algorithm HIL

```text
PC:
Simulator
Sensor simulation
Vehicle plant

J6M:
Navigation
Safety
Mission Manager when enabled
Perception when enabled
```

### Real Vehicle

```text
J6M:
Perception
Mission Manager
Navigation
Safety
Vehicle adapter

Physical:
Camera
LiDAR
Vehicle chassis
```

Algorithm semantics should remain stable between profiles.

---

## 15. J6-HIL Gate Sequence

### J6-HIL-0 — Environment Audit

Verify:

```text
OS
kernel
ARM64
ROS 2 / TROS
ROS distribution
Python
compiler
container runtime
storage
memory
network
```

### J6-HIL-1 — Network Proof

Verify:

```text
PC -> J6M ping
J6M -> PC ping
```

Then verify one ROS 2 topic in both directions.

### J6-HIL-2 — Environment Topic Proof

Verify J6M receives:

```text
/clock
/odom
/scan
/map
/tf
/tf_static
```

### J6-HIL-3 — Navigation Startup

Verify on J6M:

```text
planner_server active
controller_server active
cleannav_hybrid_planner_bridge alive
cleannav_path_executor alive
cleannav_safety_supervisor alive
```

### J6-HIL-4 — Planning Proof

Verify:

```text
/goal_pose
    ↓
Hybrid Planner Bridge
    ↓
Smac Hybrid-A*
    ↓
/cleannav/global_path
```

Planning must execute on J6M.

### J6-HIL-5 — Closed-Loop Motion Proof

Verify:

```text
PC simulated environment
    ↓
J6M
    ↓
Hybrid-A*
    ↓
MPPI
    ↓
Safety
    ↓
J6M /cmd_vel
    ↓
PC Gazebo Ackermann
    ↓
changed /odom
    ↓
J6M
```

Evidence must include:

```text
global path on J6M
nonzero cmd_vel_candidate on J6M
nonzero final cmd_vel on J6M
PC vehicle displacement
new odom returned to J6M
```

### J6-HIL-6 — Repeatability

Create a repeatable clean-start procedure and preserve:

```text
node states
topic authority
planner result
MPPI candidate
Safety output
vehicle displacement
logs
recovery procedure
```

---

## 16. Historical J6M HMI HIL Sequence — not M0 operational path

After J6-HIL-5:

```text
J6-HMI-1
Mission Manager -> Navigation HIL

J6-HMI-2
APP -> TaskCommand -> Mission Manager -> Navigation HIL

J6-HMI-3
Offline Voice -> TaskCommand -> Mission Manager -> Navigation HIL
```

---

## 17. 15-Day Schedule

```text
Day 1      J6-HIL-0 environment audit
Day 2      J6-HIL-1 network + DDS
Day 3-4    J6-HIL-2 environment topics
Day 5      J6-HIL-3 Navigation startup
Day 6      J6-HIL-4 planning
Day 7-8    J6-HIL-5 closed-loop motion
Day 9      J6-HIL-6 repeatability
Day 10     evidence / logs / screenshots / video
Day 11     Mission Manager HIL
Day 12     APP HIL
Day 13     offline voice HIL
Day 14     system integration / recovery
Day 15     competition buffer
```

If schedule slips, reduce scope in this order:

```text
1. perception HIL complexity
2. offline voice polish
3. APP polish
```

Navigation HIL must remain complete.

---

## 18. Current Verified Baseline

The current PC Ackermann Navigation baseline has already demonstrated:

```text
Smac Hybrid-A* path generation
Path Executor acceptance
MPPI Ackermann candidate velocity
Safety final velocity
Ackermann vehicle motion
```

The production Navigation launch has passed:

```text
source audit
build
launch validation
unit tests
runtime closed-loop motion proof
```

This remains SIL/runtime evidence only.

It must not be described as J6M HIL evidence.

---

## 19. Frozen Decision Rule

This baseline may change only because of concrete evidence from:

1. physical J6M limitations;
2. ROS 2 compatibility limitations;
3. competition requirements;
4. measured HIL failures;
5. delivered hardware interfaces.

Until such evidence exists:

```text
do not replace Hybrid-A*
do not replace MPPI
do not move Safety authority
do not redesign Mission Manager
do not introduce a custom HIL bridge
do not place J6M hardware details into platform-independent modules
```

The project now prioritizes execution, validation and competition readiness.

---

## 20. 2026-09-04 Physical J6M HIL Bring-up

This section records physical-board evidence obtained on 2026-09-04.

Facts marked as verified below are measured results from the physical J6M.
The deployment architecture described later is a candidate plan and has
not yet been implemented.

### 20.1 Physical platform

Verified board and operating-system information:

- Board: `J6M_SIP_Matrix_V1.1`
- Architecture: `aarch64`
- OS: Debian GNU/Linux 12 (bookworm)
- Kernel: Linux 6.1.158 with PREEMPT_RT
- Shell authority: root

Verified power configuration:

- Power adapter: 12 V DC, 6.67 A, 80 W
- Red/black power pair is sufficient for normal boot.
- The additional yellow/ACC-style line is not used in the verified boot setup.

### 20.2 Debug access

ADB access from Windows was verified.

- adb protocol version: 1.0.41
- Android platform-tools: 37.0.1
- Device ID: `083207a8309228a2`
- ACore shell: root
- Native Ethernet SSH is also available.

ADB remains a useful recovery/debug channel, but Ethernet is the intended
communication path for HIL.

### 20.3 J6M Ethernet

Verified J6M interfaces:

- `eth0 = 192.168.8.10/24`
- `eth1 = 10.7.0.118/24`
- Driver: `hobot_gmac`
- Link mode: fixed/SGMII
- Link speed: 1000 Mb/s Full Duplex
- SSH server: TCP port 22

Verified PC-side dedicated Ethernet interface:

- Adapter: Realtek PCIe GbE Family Controller
- Address: `192.168.8.20/24`
- No dedicated default gateway is required for the J6M link.

The currently verified hardware path is:

    J6M
      -> 1000M Master T1 cable
      -> SE1001Pro
      -> RJ45 Ethernet cable
      -> Windows Realtek Ethernet

The cable labelled `1000M Slave` did not provide a reliable operating
configuration in this setup.

Using the `1000M Master` path, the following were verified:

- Windows Ethernet status: Up
- Link speed: 1 Gbps
- PC to J6M ping: 50/50 replies
- Packet loss: 0%
- RTT: approximately 1-2 ms
- SSH TCP/22: PASS

### 20.4 SE1001Pro observations

Observed converter state during successful operation:

- RUN indicator: normal flashing
- T1 Link indicator: active
- SQI: 100%
- RJ45: 1 Gbps when mechanically stable

A reproducible mechanical robustness problem was observed:

- Lifting or moving the SE1001Pro can cause the RJ45 link to drop.
- The PC Realtek port and replacement RJ45 cable were independently
  verified using a router.
- The same failure was not reproduced with the PC port and RJ45 cable alone.

Current leading diagnosis:

    suspected SE1001Pro RJ45 mechanical/contact fault

Possible fault locations include the RJ45 receptacle, connector contacts,
local solder joints or nearby PCB mechanical integrity.

The T1 side itself did not indicate poor signal quality because the
SE1001Pro continuously reported `SQI = 100%`.

### 20.5 Stationary-link stability

With the converter and all cables left mechanically undisturbed, the
link was stable.

Verified results:

- Windows Ethernet: Up
- Windows link speed: 1 Gbps
- Windows to J6M ping: 50/50, 0% packet loss
- WSL route to `192.168.8.10`: via mirrored `eth1`
- WSL source address: `192.168.8.20`
- WSL to J6M SSH: PASS
- J6M eth0: 1000 Mb/s Full Duplex
- J6M Link detected: yes

The following J6M error counters remained zero:

- `mmc_tx_carrier_error`
- `mmc_rx_crc_error`
- `mmc_rx_udp_err`
- `rx_crc_errors`
- `rx_gmac_overflow`
- `rx_missed_cntr`
- `rx_overflow_cntr`
- `rx_buf_unav_irq`

A two-minute stationary-link test executed 12 consecutive checks.

Result:

- 12/12 Windows status: Up
- 12/12 Windows speed: 1 Gbps
- 12/12 WSL SSH: PASS

Current interpretation:

- Stationary Ethernet link: VERIFIED STABLE
- Mechanical robustness: NOT VERIFIED
- SE1001Pro RJ45 fault: SUSPECTED AND MECHANICALLY REPRODUCIBLE

### 20.6 UDP measurements

Earlier UDP measurements showed inconsistent reception while the
SE1001Pro hardware path was mechanically suspect.

Representative measurements included approximately 53-58 received
packets out of 100.

One instrumented Windows-to-J6M run measured:

- Windows `SentUnicastPackets`: +100
- J6M `mmc_rx_udp_gd`: +58
- J6M UDP `InDatagrams`: +58
- Application `RX_UNIQUE`: 58/100

During that run there was no increase in:

- CRC errors
- UDP errors
- GMAC overflow
- RX missed counters
- RX buffer unavailable IRQs

Because the SE1001Pro RJ45 mechanical problem was subsequently reproduced,
these UDP-loss results are not accepted as valid ROS 2 or DDS network
qualification evidence.

UDP multicast and DDS qualification must be repeated with a mechanically
trustworthy Ethernet path.

### 20.7 Board deployment environment

The current J6M runtime does not contain a ROS 2 development/runtime
installation suitable for CleanNav.

Verified absent tools include:

- `ros2`
- `colcon`
- `gcc`
- `g++`
- `cmake`
- `make`

No `/opt/ros` installation was found.

The J6M system uses a protected platform layout including overlay root,
dm-verity and secure/verified boot.

CleanNav deployment must therefore not depend on disabling or modifying
the verified root filesystem.

Verified writable deployment area:

- Path: `/map`
- Device: `/dev/mmcblk0p32`
- Filesystem: ext4
- Mount state: rw
- Capacity: approximately 15 GB
- Available space: approximately 14 GB
- Script execution from `/map`: PASS

Verified host utilities include:

- `chroot`
- `mount`
- `umount`
- `findmnt`
- `tar`
- `gzip`
- `xz`
- `scp`
- `sftp`
- `wget`

The following virtual filesystems are available for a future chroot:

- `/proc`
- `/sys`
- `/dev`
- `/dev/pts`
- `/dev/shm`

### 20.8 Candidate ROS 2 deployment architecture

The current candidate deployment layout is:

    /map/cleannav_runtime/
    `-- jammy/

The candidate is an Ubuntu 22.04 ARM64 userspace operated through chroot.

Its purpose is to preserve compatibility with the already validated PC
software baseline:

- ROS 2 Humble
- Nav2
- Smac Hybrid-A*
- MPPI Ackermann
- CleanNav Navigation

The J6M native kernel, device drivers, Ethernet interfaces and vendor
runtime would remain unchanged.

This is a candidate architecture only.

It has not yet been installed or accepted as J6M runtime evidence.

### 20.9 Current HIL gate status

Current physical-board status:

- J6-HIL-0A Power + USB/ADB: PASS / CLOSED
- J6-HIL-0B Shell / OS / basic network audit: PASS / CLOSED
- J6-HIL-0C Board / runtime audit: PASS / CLOSED
- J6-HIL-0D Deployment environment audit: PASS / CLOSED
- J6-HIL-0E `/map` writable/executable proof: PASS / CLOSED
- J6-HIL-0F USB host capability audit: PASS / CLOSED
  - USB host capability was not proven active.
- J6-HIL-0G Ethernet PHY / driver mapping: PASS / CLOSED
- J6-HIL-1 PC to J6M basic Ethernet and SSH: PASS / CLOSED
- J6-HIL-2A ROS 2 deployment environment audit: PASS / CLOSED
- J6-HIL-2B Jammy chroot feasibility audit: PASS / CLOSED
- J6-HIL-2C Network qualification: PARTIAL / HARDWARE-LIMITED

For J6-HIL-2C:

- Stationary physical link: PASS
- Mechanical robustness: NOT ACCEPTED
- UDP multicast: DEFERRED
- ROS 2 DDS: DEFERRED

Current hardware blocker:

    suspected SE1001Pro RJ45 mechanical/contact fault

Deployment preparation may continue while the converter remains stationary,
but final DDS, network-stability and closed-loop HIL evidence must be
repeated using a mechanically trustworthy Ethernet path.


## 21. 2026-09-04 Jammy / ROS 2 Humble Runtime Bring-up

### 21.1 Clock synchronization

The J6M system clock was manually synchronized from the WSL host before package installation.

Final clock consistency proof:

- J6 host epoch and Jammy chroot epoch were identical.
- `CLOCK_DELTA_SECONDS=0`.
- `CHROOT_CLOCK_CONSISTENCY=PASS`.
- Timezone remained `+0800 CST`.

The onboard RTC remains a known platform limitation. Although `hwclock -w -u -f /dev/rtc0` returned success, the RTC sysfs time did not change from its old value. Therefore:

- runtime system clock: PASS;
- Jammy chroot clock: PASS;
- RTC persistence: FAIL / non-blocking;
- after every future reboot or power cycle, host time must be synchronized again before APT, ROS, logging, or HIL testing.

### 21.2 Repository access through WSL reverse tunnels

Because the J6M host has no proven direct Internet access, repository access was provided through SSH reverse tunnels from J6M to WSL:

- `127.0.0.1:18080 -> WSL -> ports.ubuntu.com:80`
- `127.0.0.1:18081 -> WSL -> packages.ros.org:80`

Both listeners were verified on J6M.

Ubuntu Jammy ARM64 repository proof:

- Ubuntu `InRelease` returned HTTP 200;
- signed payload was present;
- `apt-get update` successfully downloaded Jammy ARM64 package indices;
- main, restricted, universe, and multiverse indices were verified.

ROS 2 repository proof:

- ROS 2 Jammy `InRelease` returned HTTP 200;
- signed payload was present;
- ROS 2 ARM64 package index was downloaded successfully.

The repository tunnel is a development/HIL transport mechanism only and is not part of the final vehicle runtime architecture.

### 21.3 ROS 2 APT bootstrap

The verified bootstrap package was installed inside the Jammy chroot:

- package: `ros2-apt-source`;
- version: `1.2.0~jammy`;
- architecture: `all`;
- status: `install ok installed`.

The installed source configuration resolves inside the chroot as:

`/etc/apt/sources.list.d/ros2.sources -> /usr/share/ros-apt-source/ros2.sources`

The ROS 2 signing key and repository configuration were both verified.

### 21.4 Humble ARM64 package availability

The ROS 2 Jammy ARM64 index confirmed availability of:

- `ros-humble-ros-base`;
- `ros-humble-navigation2`;
- `ros-humble-nav2-bringup`;
- `ros-humble-nav2-smac-planner`;
- `ros-humble-nav2-mppi-controller`.

Observed Nav2 package version was `1.1.20`.

The package architecture reported by APT and dpkg was `arm64`.

### 21.5 ROS Base installation

A dry-run dependency audit was completed before installation.

Simulation result:

- 6 packages upgraded;
- 388 newly installed;
- 394 package operations in total;
- approximately 108 MB download;
- approximately 442 MB additional installed space;
- no kernel, bootloader, firmware, Horizon, or Hobot platform packages were detected by the risk scan.

`ros-humble-ros-base` was then installed successfully inside:

`/map/cleannav_runtime/jammy`

Final evidence:

- package version: `0.10.0-1jammy.20260804.223545`;
- architecture: `arm64`;
- status: `install ok installed`;
- ROS distro: `humble`;
- ROS version: `2`;
- ROS Python version: `3`;
- Python: `3.10.12`;
- machine architecture: `aarch64`;
- `ros2 --help`: PASS;
- `rclpy` import: PASS;
- `rmw_fastrtps_cpp`: installed;
- `dpkg --audit`: PASS;
- APT dependency check: PASS;
- `/opt/ros/humble`: approximately 107 MB;
- installed ROS Humble package count: 193.

After installation `/map` remained below 10% utilization.

### 21.6 Local Fast DDS runtime proof

A two-process ROS 2 pub/sub smoke test was executed entirely on the J6M.

Test configuration:

- `ROS_DOMAIN_ID=42`;
- `ROS_LOCALHOST_ONLY=1`;
- `RMW_IMPLEMENTATION=rmw_fastrtps_cpp`.

A separate rclpy publisher and subscriber successfully exchanged:

`J6_HIL_DDS_OK`

Final result:

- subscriber initialization: PASS;
- publisher initialization: PASS;
- Fast DDS local discovery: PASS;
- message delivery: PASS;
- residual test processes: none;
- residual mounts: none.

Therefore the J6M ARM64 ROS 2 runtime and local Fast DDS path are verified.

### 21.7 Cross-machine DDS status

A cross-machine test was then performed between:

- WSL2 Ubuntu 22.04 / ROS 2 Humble / amd64;
- J6M Jammy chroot / ROS 2 Humble / arm64.

Basic IPv4 connectivity remained healthy:

- WSL: `192.168.8.20`;
- J6M eth0: `192.168.8.10`;
- eth0 carrier: up;
- 10/10 ICMP packets received;
- 0% packet loss.

For the WSL publisher to J6 subscriber test:

- WSL publisher ran successfully;
- J6 subscriber started successfully;
- Fast DDS message delivery did not occur;
- J6 subscriber timed out after 20 seconds.

Therefore:

`J6-HIL-2E2B2 cross-machine DDS = FAIL / OPEN`

The failure has not yet been root-caused. Current candidates include Fast DDS discovery behavior, multicast transport, or network-interface selection. It must not yet be attributed to any single layer.

The existing SE1001Pro mechanical/contact concern also remains relevant when interpreting future network tests.

### 21.8 ROS 2 daemon cleanup

The `ros2 topic` CLI test spawned a persistent ROS 2 daemon for domain 43.

The daemon:

- remained after the CLI test;
- held the Jammy `/dev` and `/dev/shm` bind mounts busy;
- did not terminate after SIGTERM.

After the daemon was positively identified as the test-created chroot ROS 2 daemon, SIGKILL was applied only to that exact PID.

Final cleanup proof:

- daemon exited;
- no processes remained rooted in the Jammy chroot;
- `/dev/shm` unmounted normally;
- `/dev` unmounted normally;
- no residual Jammy mounts remained;
- no domain-43 ROS 2 daemon remained.

### 21.9 End-of-day checkpoint

At the end of the 2026-09-04 session:

PASS:

- J6M physical power and ADB;
- dedicated Ethernet and SSH;
- Jammy ARM64 chroot;
- native ARM64 chroot execution;
- runtime VFS access;
- corrected system clock;
- signed Ubuntu APT access;
- signed ROS 2 APT access;
- ROS 2 Humble ros-base installation;
- rclpy runtime;
- Fast DDS local two-process communication.

OPEN:

- RTC persistence;
- cross-machine WSL/J6 Fast DDS communication;
- final mechanical robustness of the SE1001Pro path.

DEFERRED:

- Nav2 installation;
- Hybrid-A* / MPPI runtime validation on J6M;
- CleanNav navigation deployment;
- Mission Manager and HMI integration HIL.

Next power-on procedure:

1. verify ADB / Ethernet / SSH;
2. immediately synchronize J6M system time from the development host because RTC persistence is not available;
3. verify Jammy rootfs and ROS Humble installation;
4. continue cross-machine DDS diagnosis using direct rclpy tests without `ros2 topic` daemon dependency;
5. after DDS transport is understood, proceed to Nav2 installation and Navigation HIL.
