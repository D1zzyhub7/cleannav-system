# j6m_vehicle_gateway_ros1 source skeleton

Status: **SOURCE PREPARED / NOT BUILT AGAINST TARGET AUTOWARE**. The ROS1
runtime and distribution are unknown in this environment. This directory is
outside the ROS2 `src/` tree and is not included in `colcon build` or tests.
No ROS1 installation or old Autoware source modification was performed.

The C++14 ROS-independent codec and arbiter live in
`../cnvg_protocol/`. The intended production path is:

```text
UDP receiver -> CNVG protocol validator -> J6M command state
             -> command arbiter -> VehicleCmd mapper -> one /vehicle_cmd publisher
/vehicle_cmd_legacy ------------------------------------^
```

Legacy Autoware must later be configured to route `twist_gate` to
`/vehicle_cmd_legacy`; this preparation stage does not edit the old launch or
`twist_gate`. Parameters are `legacy_input_topic` and
`output_vehicle_cmd_topic`. The package source caches legacy input and has one
publisher declaration, but intentionally publishes no `/vehicle_cmd` data.
UDP receiving, operator owner selection, production command conversion, and
publisher activation remain TODOs.

The empty `gear_map` is deliberate. Unknown gear mapping preserves the current
gear and cannot trigger a gear change. `rad_to_deg` is the only steering unit
conversion prepared here; sign, ratio, limit, and physical steering semantics
remain unknown. Brake is blocked pending runtime and hardware verification.

This package has **not** been compiled against a ROS1 distribution or the
specific Autoware message package. `CMakeLists.txt` is a conservative catkin
C++14 starting point, not build evidence. No launch was run. Do not set
`skeleton_enabled` true for a vehicle; the source still has no control publisher
behavior.
