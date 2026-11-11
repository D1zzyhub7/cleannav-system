# NET-1 hardware bring-up checklist

This checklist begins only after authorized hardware access. Each phase has a
review gate. Record the observed ROS graph, packet captures, configuration,
operator, and safety setup before progressing.

## Phase 1: physical network only

Connect the approved Autoware PC and J6M gateway Ethernet links with vehicle
control disabled. Run `tools/net1_runtime_audit.sh` on the Autoware PC. Confirm
interface names, addresses, routes, neighbors, link state, and UDP sockets.
Apply only the network configuration approved for the bench; this project
script does not change it. Confirm the peer IP and dedicated UDP port on both
ends. Do not use UDP 4500, 4501, or 6667.

## Phase 2: Autoware runtime observation

Start the existing Autoware stack using its approved operator procedure, with
vehicle control inhibited. Record `rosnode list`, `rostopic list`, publisher
identity for `/vehicle_cmd`, message types and update rates for
`/vehicle_velocity`, `/can_info`, and `/driving_mode_viz`, plus the active
`xsugv_interface` parameters. Confirm the legacy remap sends `twist_gate` to
`/vehicle_cmd_legacy` and leaves the gateway as the sole `/vehicle_cmd`
publisher.

## Phase 3: passive IVCU observation

With controls disabled, use an approved passive capture point and filter to
record idle traffic. Do not transmit probes or commands. Document the capture
interface and all filters. Save the original capture as `ivcu_idle.pcap`.

## Phase 4: vehicle-state-only bridge

Start a state-only bridge with command output disabled. Confirm source and
units for velocity, CAN steering angle, gear, driving mode, emergency, and
fault indications. `steering_feedback_unit` must remain `UNCONFIRMED` until
runtime evidence and review establish its unit and meaning. Check freshness,
sequence, peer identity, and diagnostics.

## Phase 5: J6M heartbeat only

Enable HELLO and heartbeat exchange only. Confirm both peers advertise V1.1
capabilities, expected peer IP/port/role/owner/session checks pass, and an
incompatible peer cannot establish ACTIVE. Record loss and recovery behavior.

## Phase 6: disabled zero-control packets

If explicitly approved, send disabled zero-target packets only. These packets
are not a physical brake and do not prove a stop. Confirm the gateway reports
owner NONE and never forwards an enabled command. Observe watchdog behavior
passively.

## Phase 7: owner-transition HIL

On an immobilized bench, with the wheels unable to move and a separate approved
inhibit available, test explicit LEGACY/NONE/J6M requests, safe-zero output,
transition dwell, stale legacy command, stale J6M command, disconnect, wrong
peer, duplicate sequence, multiple `/vehicle_cmd` publishers, fault lock, and
software E-stop latch. Verify disconnect goes to NONE and never falls back to
Legacy automatically.

## Phase 8: wheels-off-ground or bench test

Only if an approved fixture exists, verify steering sign, ratio, configured
limit, gear mapping, watchdog timeout, and driver health. Confirm brake path,
physical E-stop behavior, and zero-target behavior with the vehicle owner.
Do not infer them from software messages or packet fields.

## Phase 9: closed-area minimum-speed test

Proceed only with the vehicle owner's written approval, a closed area,
spotters, an independent stop method, a confirmed brake path, confirmed
watchdog behavior, and validated steering semantics. Start at the lowest
approved speed and stop after each measured change. Preserve captures and
configuration for review.

## Hard gate

Normal driving tests are prohibited until brake behavior, watchdog behavior,
steering sign/ratio/limits, gear interlocks, and physical E-stop behavior are
confirmed by the vehicle owner. `BRAKE` remains blocked pending verification;
`PHYSICAL_ESTOP_CONFIRMED` remains `UNKNOWN` until independently established.
