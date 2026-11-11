# Legacy Autoware ROS1 production adapter

Status: **SOURCE COMPLETE / NEEDS BUILD ON THE TARGET ROS1 AUTOWARE PC**.
This package was not compiled against ROS1, launched, or connected to a vehicle.
The target ROS1 distribution and installed message revisions remain unconfirmed.

The ROS-independent C++14 core is in `../cnvg_protocol/` and builds without ROS.
The adapter source is split into:

- `src/main.cpp`: ROS1 process entry point.
- `src/gateway_node.cpp`: parameter loading, explicit UDP endpoints, source IP/port and CNVG session validation, local-monotonic freshness, ROS owner services, single output publisher, ROS master publisher conflict detection, diagnostics, and state UDP transmission.
- `src/vehicle_cmd_mapper.cpp`: configured `VehicleCmd` conversion; speed is copied in m/s, steering radians are multiplied by configured sign and ratio and converted to degrees. No brake mapping or physical E-stop mapping is present.
- `src/state_mapper.cpp`: parameterized `/vehicle_velocity`, `/can_info`, and `/driving_mode_viz` input mapping; the
`/vehicle_velocity` message type must be explicitly selected as `Twist` or
`TwistStamped`; autonomous mode requires both the visualization mode and CAN mode bits. Driver health is explicit-topic or inferred from fresh state. An unavailable
legacy fault-code source is sent as `0xffffffff` (unknown), not as a claim of no fault.
- `include/`: node and mapper interfaces.
- `../cnvg_protocol/`: wire codec, HELLO capability gate, peer/session/sequence manager, monotonic freshness helpers, explicit owner arbiter, config validation, UDP transport, and ROS-independent mapping.

## Topic ownership

Legacy `twist_gate` publishes `/vehicle_cmd` by default. Include
`launch/legacy_twist_gate_remap.include.xml` around the existing Autoware launch
to remap `/vehicle_cmd` to `/vehicle_cmd_legacy`; no old Autoware source edit is
needed. The gateway subscribes to `/vehicle_cmd_legacy` and is the only
intended publisher of `/vehicle_cmd`.

At startup and periodically, the node queries the ROS master system state for
publishers on the configured output topic. If it finds another publisher or
cannot establish the graph state, diagnostics report
`MULTIPLE_VEHICLE_CMD_PUBLISHERS`, publisher count, and publisher node identities, the arbiter latches FAULT, and the gateway
refuses J6M ownership and final output publication. Fix the graph and restart
the gateway after review.

## Production parameters and fail-closed behavior

`config/production_template.yaml` contains `UNSET` endpoints, steering values,
gear mappings, and timeout policy. Launch with
`launch/production_gateway.launch` and an explicitly completed config file.
Missing or invalid production values cause `CONFIG_ERROR` and node shutdown;
there is no wildcard peer, guessed endpoint, identity steering default, or
default gear enum. Expected peer IP, UDP port, role, owner ID, V1.1 capability
mask, session ID, and per-message sequence are validated before accepted
traffic updates state.

Only exact expected peer IP **and** configured source port are accepted. CRC32
checks corruption and does not authenticate the sender. The localhost mock is
separate and remains loopback-only.

A non-`UNSPECIFIED` gear request without a configured mapping is rejected; the
last command's gear is not changed. Brake remains blocked. The network software
E-stop latches software ownership and emits only a zero-target disabled output;
`PHYSICAL_ESTOP_CONFIRMED` is always `UNKNOWN`. A zero target is not a physical
brake.

`steering_feedback_unit` defaults to `UNCONFIRMED`. In that state the state
mapper emits no numeric steering feedback (wire value zero) and diagnostics
retain the unit status. Configuring `DEGREES` or `RADIANS` permits unit
conversion, but diagnostics still report
`steering_closed_loop_validated=false`; this does not validate steering sign,
ratio, or physical semantics.

Driver health supports `explicit_topic` and
`inferred_from_state_freshness`. Production validation rejects
`disabled_for_offline_test`. Inferred health is labeled `INFERRED` in
 diagnostics and requires a configured timeout.

## Owner and freshness policy

Owner selection is an explicit service request; peer packets never choose an
owner. Legacy and J6M commands use receiver-local monotonic arrival times and
expire to `OWNER_NONE`. Switching publishes a zero target for the configured
dwell before enabling the new owner. A J6M session/command loss goes to NONE,
never to Legacy automatically. Fresh vehicle state, confirmed autonomous
mode, fresh driver health, fresh peer/command, valid config, and a sole output
publisher are required before J6M can own output. Software E-stop and fault
states latch in the arbiter.

## Target verification still required

On the actual Autoware PC, build this package against the installed ROS1
message definitions, verify topic types and master API behavior, run the
publisher conflict and remap checks, validate the active driver health source,
and confirm runtime units and rates. Then perform the phased process in
[`docs/net1_hardware_bringup.md`](../../docs/net1_hardware_bringup.md).
Do not use control output until brake, watchdog, steering, gear, and physical
E-stop semantics are reviewed with the vehicle owner.
