# CleanNav × Legacy Autoware vehicle gateway V1.1

Status: **NET-OFFLINE-V1/V2 CHECKPOINTED; NET-OFFLINE-V3 PASS; NOT HARDWARE VERIFIED**. The CNVG
Protocol V1 wire layout uses V1.1 freshness semantics. Offline verification:
`colcon build` passed (9 ROS2 packages), and `colcon test-result --verbose`
reported 805 tests, 0 errors, 0 failures, 1 skipped. Python/C++14 interoperability
passed. This is **NOT HARDWARE VERIFIED**.

No code in this package sends the legacy IVCU protocol. It does not use UDP
4500, 4501, or 6667, and it does not publish ROS 1 /vehicle_cmd. The future
ROS1 production source is under `integration/legacy_autoware_gateway_ros1/`; it is
**SOURCE COMPLETE / NOT BUILT AGAINST TARGET AUTOWARE**.

### V1.1 peer capability negotiation

The wire version byte remains `1` and the fixed header/payload sizes do not change. HELLO alone uses the existing 16-bit header flags field as a capability mask: bit 0 is receiver-local monotonic validity, bit 1 is explicit owner arbitration, and bit 2 is V1.1 semantics. V1.1 peers must advertise all three bits (`0x0007`). Any missing bit or any unknown advertised bit is incompatible and cannot establish an active session. Flags on non-HELLO messages remain zero.

A legacy V1 peer with HELLO flags zero can be parsed for diagnosis but is never accepted for control. A strict old V1 parser will reject the V1.1 HELLO flags. Both cases fail closed without changing the 24-byte header or 25-byte HELLO payload. CRC32 remains error detection, not authentication; peer IP/port, role, owner ID, session, capability mask, and per-message sequence are checked separately.


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

All fields use network byte order (big endian). The Python codec uses `struct`
and the C++14 reference writes each field explicitly; no compiler ABI or padding
is used.
The fixed header is 24 bytes:

| Offset | Width | Field | V1 value / meaning |
|---:|---:|---|---|
| 0 | 4 | magic | ASCII CNVG |
| 4 | 1 | version | 1 |
| 5 | 1 | message_type | Message Types below |
| 6 | 2 | flags | HELLO V1.1 capability mask `0x0007`; zero elsewhere |
| 8 | 4 | sequence | uint32 per sender and message type |
| 12 | 8 | timestamp_ms | Unix epoch milliseconds |
| 20 | 2 | payload_length | Exact number of payload bytes |
| 22 | 2 | reserved | 0; other values rejected |
| 24 | variable | payload | Message-specific fixed layout |
| end-4 | 4 | crc32 | Big-endian IEEE CRC-32 |

CRC is zlib.crc32 over bytes 0 through the last payload byte. The trailing CRC
field is excluded from the CRC input. Empty payloads are legal at the framing
layer but are rejected for every defined message type. Maximum datagram size is
512 bytes. Wrong magic, version, type, non-HELLO flags, length, payload enum, or CRC is
rejected before it can update command/state. HELLO capability incompatibility
is rejected by session validation before session/heartbeat/command/state updates.

The header timestamp is Unix epoch milliseconds for packet-capture correlation
and diagnostics only. The wire version byte remains 1; the semantic revision
is CNVG Protocol V1.1. Control freshness does not compare sender and receiver
wall clocks. The header timestamp remains Unix epoch milliseconds for logs;
all expirations use receiver-local monotonic clocks. The command receiver timestamps each accepted datagram on its own
monotonic clock and expires that command after `command_validity_ms`. Session,
sequence, and heartbeat age are independent gates. Clock synchronization may
improve log correlation, but is not a control-safety requirement. V1.0 peers
that use sender wall-clock age checks are not guaranteed safe semantic
interoperation and must not be mixed silently with V1.1 peers. CRC detects
corruption; it is not authentication. Production requires isolated vehicle
Ethernet, explicit peer IP allowlisting, firewall rules, source-address
validation, a dedicated port, and no Internet exposure.

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

HELLO includes session_id, role, and owner_id. Each process creates a new
random 64-bit session ID with `secrets.randbits(64)` at startup. A new session
resets receive sequence windows and command state. Session IDs already seen in
the current process lifetime are retired and rejected, so a delayed old HELLO
cannot roll the peer back to its former sequence window. Roles are
J6M_GATEWAY=1 and AUTOWARE_MOCK=2.
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
packet CRC, type, active session/owner, and sequence checks. The header timestamp
is not an age gate.

GATEWAY_STATUS payload is session_id, state enum, then uint32 values in order:
last_rx_age_ms, last_tx_age_ms, rx_sequence, tx_sequence, dropped_packets,
malformed_packets, stale_packets, out_of_order_packets. `stale_packets` remains
in the V1 wire layout for diagnostics compatibility; V1.1 does not increment it
from sender timestamp age.

## Timeouts

Every listed default is an **OFFLINE_DEFAULT**, not a real-vehicle calibration.
All are ROS parameters or CLI parameters.

| Timer | Offline default | Expiry behavior |
|---|---:|---|
| J6M /cmd_vel freshness | 350 ms | Do not transmit an old enabled target |
| SafetyStatus freshness | 1500 ms | Disable command output |
| J6M peer heartbeat | 450 ms | Mark link stale and disable |
| J6M vehicle-state freshness | 1000 ms | Mark link stale and disable |
| CONTROL_COMMAND validity | 300 ms | Peer expires the locally received command after deadline |
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
`--out-of-order`, `--malformed`, `--timestamp-offset-ms N`, and `--delay-ms N`.
Sender timestamp offsets are diagnostic fault injection only. Its bind and
peer IPs must remain loopback. The packaged offline demo starts the mock with
no injected fault.

## Sequence Rules

Each sender maintains a uint32 sequence counter per message type. First sequence
in a new session is accepted. A later packet is newer when
delta=(new-old) mod 2^32 is in 1..2^31-1. delta=0 is duplicate; a delta at or
above 2^31 is duplicate/out-of-order and rejected. This permits
0xfffffffe, 0xffffffff, 0, 1. Receiving a new HELLO session resets windows
and clears prior command state; old session IDs seen by the process remain
rejected for that process lifetime.
Duplicate packets are included in out_of_order_packets and separately counted
as duplicate_packets in ROS diagnostics.

## CRC

V1 uses Python standard-library zlib.crc32 with the standard IEEE CRC-32
polynomial. CRC input is the exact big-endian 24-byte header followed by the
exact payload. CRC is serialized as a big-endian uint32 after the payload.
Python hash(), ROS serialization, native C structs, and implicit padding are
not used.

## Owner Arbitration

The offline Python mock models OWNER_NONE, OWNER_LEGACY_AUTOWARE, and
OWNER_J6M to exercise command acceptance. It is not the production arbitration
reference. The C++14 ROS-independent CommandArbiter below models explicit owner
selection and transition requirements for the future ROS1 adapter.

- The mock peer accepts J6M commands only with valid session, live heartbeat,
  fresh sequence, receiver-local command validity, enable=true, no E-stop, and
  autonomous vehicle mode. Unix timestamp is diagnostic-only.
- The production core selects J6M only after `request_owner(J6M)` and a
  complete safe-zero transition; packet arrival never selects control owner.
- OWNER_LEGACY_AUTOWARE cannot be stolen by an arriving J6M packet.
- MANUAL, ESTOP, fault, bad driver/gateway health, or network/command timeout
  prevents or removes OWNER_J6M.
- enable=false releases J6M and clears its last nonzero command.
- E-stop latches and clears the active owner.
- Legacy-to-J6M and J6M-to-legacy changes require an explicit operator request
  and a complete safe-zero transition. Disconnect alone never promotes another
  publisher.

CNVG V1.1 is a freeze candidate after Python/C++ golden-vector interop,
capability, session, sequence, monotonic freshness, and peer-source tests.
Hardware interop remains unverified. The C++14 ROS-independent core is in
`integration/cnvg_protocol/`: codec, HELLO
capability negotiation, source/session/sequence validation, local-monotonic
freshness, production config checks, owner arbiter, UDP transport, and mapping.
It clears ownership on timeout, E-stop, mode loss, or fault. Unix timestamps
never gate command freshness.

The ROS1 adapter source is now in
`integration/legacy_autoware_gateway_ros1/`; it is source-complete but has not
been built against the target ROS1/Autoware. It has one final `/vehicle_cmd`
publisher and checks ROS master publisher identities, failing closed on an
unknown graph or extra writer. The include template remaps legacy `twist_gate`
output to `/vehicle_cmd_legacy`; no old Autoware source is changed.

## Fail-safe Behavior

A CONTROL_COMMAND is actionable only after magic/version/length/CRC/type,
session/owner, sequence, enable, emergency, peer heartbeat, and vehicle-mode
checks. The Unix header timestamp is diagnostic-only. After acceptance, the
receiver records local monotonic arrival and expires the command after
command_validity_ms even while heartbeats stay alive; peer RX timeout is an
additional upper bound on ownership. Duplicate, old-sequence, invalid-session,
and malformed packets do not renew command age.

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

## ROS1 Production Adapter Source

`integration/legacy_autoware_gateway_ros1/` contains the source-complete ROS1
adapter layout and production configuration template. It has not been built
against the target ROS1 distribution or Autoware message revision. The launch
requires an explicit config file and fails closed on `UNSET` endpoints,
steering settings, owner identity, capability mask, or timeout values.

The input path is UDP -> CNVG codec -> expected peer IP/port, role, owner,
capabilities, session and sequence validation -> explicit owner arbiter ->
configured VehicleCmd mapper -> sole `/vehicle_cmd` publisher. ROS feedback
from parameterized `/vehicle_velocity`, `/can_info`, and `/driving_mode_viz`
feeds the state mapper and returns `VEHICLE_STATE` by UDP. Legacy command
freshness uses receiver-local monotonic time. Owner changes pass through
zero-target dwell; disconnect goes to NONE.

Speed maps directly in m/s. Steering uses configured sign, ratio, and radians
limit before conversion to degrees. Gear mapping is config-only; an unmapped
non-unspecified gear is rejected. No J6M brake mapping or physical E-stop
claim is made. State steering feedback defaults to `UNCONFIRMED`; unit
conversion does not validate closed-loop steering. The ROS master check reports
publisher identities and refuses J6M ownership when another `/vehicle_cmd`
writer exists or graph state cannot be read.

See [the adapter README](../integration/legacy_autoware_gateway_ros1/README.md),
[the mapping evidence](autoware_vehicle_mapping.md), and
[the NET-1 bring-up checklist](net1_hardware_bringup.md).

## Runtime Unknowns

The following remain UNKNOWN and are intentionally not embedded in defaults:
Autoware PC IP, J6 hardware IP, real gateway port, real wheelbase, steering
ratio/sign/limit, IVCU watchdog, brake behavior, vehicle-mode mapping, final
gear mapping, command rates, and physical link topology. Ports 4500, 4501, and
6667 remain reserved for the legacy path and are never used by CNVG.

## Hardware Validation Checklist

This checklist is for a future NET-1 review; it was not run in this phase.

- Confirm both computers, physical interfaces, route, firewall and isolated
  control VLAN/point-to-point wiring.
- Assign and document new gateway addresses and ports; keep them separate from
  HIL and IVCU endpoints.
- Confirm peer identity, explicit owner/session policy, packet capture format,
  and sequence wrap behavior. Clock sync may aid log correlation but is not a
  command freshness prerequisite.
- Confirm the gateway is the unique final `/vehicle_cmd` publisher and
  xsugv_interface is the only IVCU owner.
- Establish measured steering/gear/brake semantics and manufacturer-approved
  speed/steering limits.
- Verify IVCU command watchdog and safe stop on packet loss, adapter crash,
  stale state, duplicate, CRC error, manual mode and E-stop.
- HIL fault-inject each condition before any supervised, low-speed, closed-area
  vehicle trial.
- Provide an explicit operator-controlled rollback to legacy Autoware.

