# CleanNav × Legacy Autoware vehicle gateway V1

Status: **OFFLINE VERIFIED** (ROS 2 workspace build, localhost UDP integration,
and full workspace regression passed). This document describes a loopback-only
development protocol. It is **NOT YET HARDWARE VERIFIED**.

No code in this package sends the legacy IVCU protocol. It does not use UDP
4500, 4501, or 6667, and it does not publish ROS 1 /vehicle_cmd. The future ROS 1
adapter is documented below and is **NOT BUILT / NEED AUTOWARE RUNTIME**.

## Architecture

~~~mermaid
flowchart LR
    nav[Navigation] --> candidate[/cleannav/cmd_vel_candidate]
    candidate --> safety[Safety Supervisor]
    safety --> cmd[/cmd_vel post-limit]
    cmd --> j6[J6M ROS 2 gateway]
    j6 <-->|UDP V1, localhost in offline mode| mock[Autoware-side mock]
    mock --> state[Mock vehicle state]
    state --> j6
    j6 --> topics[/cleannav/vehicle state and diagnostics]
~~~

The J6M gateway subscribes only to the Safety Supervisor output /cmd_vel. It
does not subscribe to /cleannav/cmd_vel_candidate. Sending an enabled command
also requires a fresh SafetyStatus with autonomous_enabled=true,
block_all=false, emergency_stop_active=false; a fresh /cmd_vel; a live peer
session, heartbeat, and vehicle state; an autonomous vehicle mode; a live
mock driver; and no reported fault.

In offline_test_mode=true, both configured IPv4 endpoints must equal
127.0.0.1. The ROS launch also sets ROS_LOCALHOST_ONLY=1. The mock independently
rejects non-loopback bind and peer addresses. Default ports 39181 and 39182 are
parameterized **OFFLINE_DEFAULTS**, not a hardware port allocation.

## Protocol Header

All fields use network byte order (big endian). Header and payload are encoded
field-by-field with Python struct; no language ABI or compiler padding is used.
The fixed header is 24 bytes:

| Offset | Width | Field | V1 value / meaning |
|---:|---:|---|---|
| 0 | 4 | magic | ASCII CNVG |
| 4 | 1 | version | 1 |
| 5 | 1 | message_type | Message Types below |
| 6 | 2 | flags | 0; other values rejected |
| 8 | 4 | sequence | uint32 per sender and message type |
| 12 | 8 | timestamp_ms | Unix epoch milliseconds |
| 20 | 2 | payload_length | Exact number of payload bytes |
| 22 | 2 | reserved | 0; other values rejected |
| 24 | variable | payload | Message-specific fixed layout |
| end-4 | 4 | crc32 | Big-endian IEEE CRC-32 |

CRC is zlib.crc32 over bytes 0 through the last payload byte. The trailing CRC
field is excluded from the CRC input. Empty payloads are legal at the framing
layer but are rejected for every defined message type. Maximum datagram size is
512 bytes. Wrong magic, version, type, flags, length, payload enum, or CRC is
rejected before it can update command/state.

The timestamp is Unix time, not a cross-host monotonic clock. Receivers enforce
the message-specific age/validity and allow at most 200 ms future skew.
Autoware PC and J6M clocks must be synchronized before NET-1. CRC detects
corruption; it is not authentication. NET-1 must isolate the control segment
and validate peer addresses and firewall policy.

## Message Types

| Value | Name | Payload struct |
|---:|---|---|
| 1 | MSG_HELLO | !QB16s |
| 2 | MSG_HEARTBEAT | !Q16s |
| 3 | MSG_CONTROL_COMMAND | !Q16sBBBbHfff |
| 4 | MSG_VEHICLE_STATE | !Q16sffbBBBBI |
| 5 | MSG_GATEWAY_STATUS | !QB8I |

In struct formats, ! means network byte order, Q is uint64, I is uint32, H is
uint16, B is uint8, b is int8, f is IEEE-754 binary32, and 16s is exactly
16 ASCII bytes padded with zeroes. Owner IDs are 1–16 ASCII bytes.

HELLO includes session_id, role, and owner_id. A new session_id resets the
receiver's sequence windows. Roles are J6M_GATEWAY=1 and AUTOWARE_MOCK=2.
The mock uses the same AUTOWARE_MOCK role in this offline build; the production
Autoware adapter role assignment is deferred to NET-1.

HEARTBEAT includes session_id and owner_id. Both peers send it every 100 ms by
default. It reports process reachability and carries no command.

MSG_ESTOP is not a separate type in V1. An emergency_stop bit in a validated
CONTROL_COMMAND latches peer E-stop. The mock has no network reset message;
local reset or process restart is required. Real reset authority and vehicle
behavior remain unresolved.

## Command Schema

CONTROL_COMMAND payload order:

1. session_id: uint64
2. owner_id: 16 ASCII bytes
3. enable: uint8 boolean
4. emergency_stop: uint8 boolean
5. control_mode: uint8 (MODE_TWIST_RAW=0, MODE_ACKERMANN=1)
6. gear: int8 transport enum
7. command_validity_ms: uint16, 1–5000
8. target_speed_mps: float32
9. target_yaw_rate_rps: float32
10. target_steering_rad: float32

All numeric controls must be finite. MODE_TWIST_RAW copies /cmd_vel.linear.x to
target_speed_mps and /cmd_vel.angular.z to target_yaw_rate_rps. It sends
target_steering_rad=0 and does not infer wheelbase. MODE_ACKERMANN sends
linear.x plus a fresh explicit Float64 target from
/cleannav/vehicle/target_steering in radians; target_yaw_rate_rps is 0. No
Ackermann conversion is implemented. The steering topic currently has no
CleanNav publisher and must be supplied by a future approved adapter/controller
before selecting that mode.

V1 gear transport enum is UNSPECIFIED=0, PARK=1, REVERSE=2, NEUTRAL=3,
DRIVE=4, LOW=5. This is a new protocol enum; mapping to legacy Autoware Gear,
IVCU gear codes, reverse interlocks, and the real vehicle remains UNKNOWN.

The mock implements latest-valid-command-wins. A new valid command replaces
the prior target. Historical commands are never replayed. A command becomes
invalid at its deadline even if the UDP peer remains alive.

## State Schema

VEHICLE_STATE payload order:

1. session_id: uint64
2. owner_id: 16 ASCII bytes
3. speed_mps: float32
4. steering_rad: float32
5. gear: int8 transport enum
6. vehicle_mode: uint8 (UNKNOWN=0, MANUAL=1, AUTONOMOUS=2, ESTOP=3, FAULT=4)
7. emergency: uint8 boolean
8. gateway_alive: uint8 boolean
9. driver_alive: uint8 boolean
10. fault_code: uint32

V1 carries no GNSS or raw IMU. Source-to-frame mapping and actual units from
IVCU are **UNKNOWN / NEED RUNTIME VERIFICATION**. State is published only after
packet CRC, type, session/owner, sequence, and timestamp checks.

GATEWAY_STATUS payload is session_id, state enum, then uint32 values in order:
last_rx_age_ms, last_tx_age_ms, rx_sequence, tx_sequence, dropped_packets,
malformed_packets, stale_packets, out_of_order_packets.

## Timeouts

Every listed default is an **OFFLINE_DEFAULT**, not a real-vehicle calibration.
All are ROS parameters or CLI parameters.

| Timer | Offline default | Expiry behavior |
|---|---:|---|
| J6M /cmd_vel freshness | 350 ms | Do not transmit an old enabled target |
| SafetyStatus freshness | 1500 ms | Disable command output |
| J6M peer heartbeat | 450 ms | Mark link stale and disable |
| J6M vehicle-state freshness | 1000 ms | Mark link stale and disable |
| CONTROL_COMMAND validity | 300 ms | Peer rejects after deadline |
| Safe command burst | 300 ms | Send disabled zero command for a finite interval, then stop command TX |
| Peer command RX timeout | 450 ms | OWNER_J6M is released; target is cleared |
| HEARTBEAT interval | 100 ms | Peer liveness |
| HELLO interval | 500 ms | Session discovery |
| Control TX interval | 50 ms | Up to 20 Hz while all gates are valid |
| Mock state interval | 50 ms | Mock feedback cadence |

The gateway heartbeat continues while command TX is disabled. Peer heartbeat
alone never retains OWNER_J6M; both peer heartbeat and a fresh command are
required. If the J6M process exits, its heartbeat and command both stop. If the
mock process exits, J6M state/heartbeat age expires and diagnostics become
STALE. A real PC adapter must implement its own command RX timeout.

## Offline Demo and Fault Injection

After building and sourcing this workspace, start the complete loopback demo:

```bash
ROS_LOCALHOST_ONLY=1 ros2 launch cleannav_vehicle_gateway offline_demo.launch.py
```

In another terminal, enable the Safety demo lease and publish a low-speed test
candidate continuously:

```bash
ros2 service call /cleannav/safety/set_autonomous_enabled std_srvs/srv/SetBool "{data: true}"
ros2 topic pub --rate 5 /cleannav/cmd_vel_candidate geometry_msgs/msg/Twist "{linear: {x: 0.03}, angular: {z: 0.0}}"
```

Observe `/cleannav/vehicle/speed` and `/cleannav/vehicle/gateway_status` in a
third terminal. This profile starts Safety with `block_all=false` for the
explicit offline demo, but the gateway and mock are hard-bound to `127.0.0.1`.
It sends no packet beyond the local mock.

For custom fault runs, start the gateway and mock separately; the mock CLI
supports `--drop-rx`, `--drop-tx`, `--freeze-state`, `--duplicate-seq`,
`--out-of-order`, `--malformed`, `--stale`, and `--delay-ms N`. Its bind and
peer IPs must remain loopback. The packaged offline demo starts the mock with
no injected fault.

## Sequence Rules

Each sender maintains a uint32 sequence counter per message type. First sequence
in a new session is accepted. A later packet is newer when
delta=(new-old) mod 2^32 is in 1..2^31-1. delta=0 is duplicate; a delta at or
above 2^31 is duplicate/out-of-order and rejected. This permits
0xfffffffe, 0xffffffff, 0, 1. Receiving a new HELLO session resets windows.
Duplicate packets are included in out_of_order_packets and separately counted
as duplicate_packets in ROS diagnostics.

## CRC

V1 uses Python standard-library zlib.crc32 with the standard IEEE CRC-32
polynomial. CRC input is the exact big-endian 24-byte header followed by the
exact payload. CRC is serialized as a big-endian uint32 after the payload.
Python hash(), ROS serialization, native C structs, and implicit padding are
not used.

## Owner Arbitration

The mock and future ROS 1 adapter use OWNER_NONE, OWNER_LEGACY_AUTOWARE, and
OWNER_J6M:

- J6M can claim only from OWNER_NONE after a valid session, live heartbeat,
  fresh sequence/timestamp, enable=true, no E-stop, and autonomous vehicle mode.
- OWNER_LEGACY_AUTOWARE cannot be stolen by an arriving J6M packet.
- MANUAL, ESTOP, fault, bad driver/gateway health, or network/command timeout
  prevents or removes OWNER_J6M.
- enable=false releases J6M and clears its last nonzero command.
- E-stop latches and clears the active owner.
- Legacy-to-J6M and J6M-to-legacy changes require an explicit future operator
  or vehicle-mode decision. Disconnect alone never promotes another publisher.

Future j6m_vehicle_gateway_ros1 must be the unique /vehicle_cmd upstream
arbiter. Either it alone publishes /vehicle_cmd after selecting
OWNER_LEGACY_AUTOWARE or OWNER_J6M, or it publishes /j6m/vehicle_cmd and a
single arbiter is the only /vehicle_cmd publisher. Autoware twist_gate must not
publish concurrently with an unarbitrated J6M writer. This offline package
does not change twist_gate and does not build a ROS 1 node.

## Fail-safe Behavior

A CONTROL_COMMAND is actionable only after magic/version/length/CRC/type,
session/owner, timestamp/validity, sequence, enable, emergency, peer heartbeat,
and vehicle-mode checks. Timestamp validity is checked before advancing the
sequence window. Any failed check does not refresh command age or sequence
state and does not make an old nonzero command fresh. The mock clears the
accepted command at the remaining validity deadline, even while heartbeats stay
alive; peer RX timeout is an additional upper bound on ownership.

J6M also requires a fresh SafetyStatus with autonomous_enabled=true,
block_all=false, and emergency_stop_active=false. It requires fresh /cmd_vel.
At local timeout it sends disabled zero commands for 300 ms and then stops
control packets. The peer expires command ownership after 450 ms even if its
process remains alive.

block_all is now an unconditional zero-output interlock in Safety Supervisor.
SafetyStatus has the minimal block_all field and interface_version=1.1 so the
gateway can independently fail closed. The standalone simulator behavior is
unchanged. The future vehicle launch passes use_sim_time=false and starts with
block_all=true.

The offline demo uses block_all=false and an explicit temporary Safety enable;
it sends datagrams only to loopback mock. It cannot contact an Autoware PC or
vehicle. No hardware-ready conclusion follows from the demo.

## ROS2 Topics

Inputs:

| Topic | ROS type | Meaning |
|---|---|---|
| /cmd_vel | geometry_msgs/msg/Twist | Post-Safety speed/yaw-rate |
| /cleannav/safety_status | cleannav_interfaces/msg/SafetyStatus | Enable, estop, and block_all |
| /cleannav/safety/emergency_stop | std_msgs/msg/Bool | Immediate E-stop indication |
| /cleannav/vehicle/target_steering | std_msgs/msg/Float64 | Optional target steering in rad, required only in MODE_ACKERMANN |
| /cleannav/vehicle/target_gear | std_msgs/msg/Int8 | Optional V1 transport gear enum |

Outputs:

| Topic | ROS type | Meaning |
|---|---|---|
| /cleannav/vehicle/speed | std_msgs/msg/Float64 | Feedback speed, m/s |
| /cleannav/vehicle/steering | std_msgs/msg/Float64 | Feedback steering, rad |
| /cleannav/vehicle/gear | std_msgs/msg/Int8 | V1 transport gear enum |
| /cleannav/vehicle/mode | std_msgs/msg/String | V1 vehicle mode name |
| /cleannav/vehicle/gateway_status | diagnostic_msgs/msg/DiagnosticStatus | Link status and counters in KeyValue entries |

No network command maps to /vehicle_cmd in this package.

## Future ROS1 Adapter

Proposed node name: j6m_vehicle_gateway_ros1. This adapter is **NOT BUILT /
NEED AUTOWARE RUNTIME**. It needs the real Autoware PC ROS 1 distribution and
custom messages before it can compile.

The future adapter should:

1. bind one reviewed, parameterized new gateway endpoint;
2. validate V1 packets and enforce an independent 450 ms offline-default RX
   timeout;
3. expose vehicle state from existing Autoware topics only after validating
   source age, units, and frames;
4. publish J6M requests to a private /j6m/vehicle_cmd topic;
5. arbitrate with legacy autonomy and become the unique writer into
   /vehicle_cmd;
6. translate speed, steering, gear, mode, enable and emergency only after
   vehicle mapping is approved;
7. stop accepting J6M commands and clear output on timeout, E-stop, manual
   mode, invalid sequence, CRC failure, or state fault.

Legacy source evidence suggests /vehicle_cmd.ctrl_cmd.linear_velocity is m/s
and its steering_angle consumer expects degrees before multiplying by 100 for
the legacy 0.01-degree IVCU value. The protocol steering value is radians.
Conversion, sign, limits, brake behavior, gear mapping, source arbitration,
and actual topic graph need Autoware-runtime verification. The old
xsugv_interface remains the only intended IVCU driver.

## Runtime Unknowns

The following remain UNKNOWN and are intentionally not embedded in defaults:
Autoware PC IP, J6 hardware IP, real gateway port, real wheelbase, steering
ratio/sign/limit, IVCU watchdog, brake behavior, use of ports 4501/6667,
vehicle-mode mapping, final gear mapping, command rates, clock synchronization,
and physical link topology.

## Hardware Validation Checklist

This checklist is for a future NET-1 review; it was not run in this phase.

- Confirm both computers, physical interfaces, route, firewall and isolated
  control VLAN/point-to-point wiring.
- Assign and document new gateway addresses and ports; keep them separate from
  HIL and IVCU endpoints.
- Confirm peer identity, owner/session policy, clock synchronization, packet
  capture format, and sequence wrap behavior.
- Confirm Autoware PC is the unique /vehicle_cmd arbiter and xsugv_interface is
  the only IVCU owner.
- Establish measured steering/gear/brake semantics and manufacturer-approved
  speed/steering limits.
- Verify IVCU command watchdog and safe stop on packet loss, adapter crash,
  stale state, duplicate, CRC error, manual mode and E-stop.
- HIL fault-inject each condition before any supervised, low-speed, closed-area
  vehicle trial.
- Provide an explicit operator-controlled rollback to legacy Autoware.

