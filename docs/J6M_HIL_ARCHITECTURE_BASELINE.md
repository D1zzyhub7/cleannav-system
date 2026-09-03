# CleanNav J6M Algorithm HIL Architecture Baseline

**Status:** FROZEN  
**Baseline:** J6M-HIL v1.0  
**Date:** 2026-09-03  
**Remaining schedule:** approximately 15 days

---

## 1. Objective

The near-term objective is to complete a repeatable **Navigation Algorithm HIL** closed loop on the physical Horizon Journey J6M.

After Navigation HIL is stable, extend the same HIL environment to:

1. Mission Manager;
2. APP task control;
3. offline voice task control.

Perception remains part of the final vehicle architecture, but leaf/puddle perception is not the current critical path.

The project now prioritizes integration and verification over further architecture exploration.

---

## 2. Frozen HIL Definition

CleanNav uses **algorithm-level HIL** as the current baseline.

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

## 3. Frozen Priority

```text
P0  J6M environment and ROS 2 compatibility
P1  Navigation HIL
P2  Navigation HIL repeatability and evidence
P3  Mission Manager HIL
P4  APP TaskCommand HIL
P5  Offline Voice TaskCommand HIL
P6  Minimal perception HIL if time permits
```

Navigation HIL must not be sacrificed for lower-priority features.

---

## 4. Deferred Work

The following are not part of the current critical path:

- complex camera-interface HIL;
- physical VIN / ISP / VIO injection;
- multi-camera perception;
- BEV perception;
- VLA or LLM deployment;
- custom TCP/UDP HIL middleware before DDS is tested;
- physical CAN integration before Navigation HIL;
- PTP/gPTP tuning before functional HIL works;
- replacing Hybrid-A* or MPPI;
- custom NMPC / MPCC / CBF;
- creating new platform repositories without concrete need.

---

## 5. HIL-V1 — Navigation HIL

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

First choice:

```text
ROS 2 DDS over Ethernet
```

Initial architecture:

```text
PC ROS 2
    ↕
Ethernet / DDS
    ↕
J6M ROS 2
```

Requirements:

- reachable IP addresses;
- same `ROS_DOMAIN_ID`;
- compatible DDS/RMW;
- compatible QoS.

Do not implement a custom HIL bridge before direct DDS is tested.

A bridge is fallback only if direct DDS fails because of:

- discovery;
- ROS distribution incompatibility;
- middleware incompatibility;
- multicast/network restrictions;
- unacceptable latency;
- unacceptable bandwidth or jitter.

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

## 12. HIL-V2 — Mission Manager + HMI

After Navigation HIL is stable:

```text
TaskCommand(task_id)
    ↓
Mission Manager on J6M
    ↓
Navigation
    ↓
Hybrid-A*
    ↓
MPPI
    ↓
Safety
    ↓
PC Gazebo vehicle
```

APP:

```text
APP
    ↓
TaskCommand(task_id)
    ↓
Mission Manager
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

## 16. HMI HIL Sequence

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
