# CNVG to Legacy Autoware VehicleCmd mapping

Status: **SOURCE AUDITED / OFFLINE ONLY**. This specification is based on a
read-only inspection of the local legacy repository. It is not hardware or
runtime confirmation. The old repository was not modified.

Legacy source inspected at:

`/mnt/g/揭榜挂帅小挑战杯/11.小黄车代码xs-autowareai-v1.14.0-master/xs-autowareai-v1.14.0-master`

## Confirmed from source

| CNVG / gateway value | Legacy source field or topic | Source evidence | What the source establishes |
|---|---|---|---|
| `target_speed_mps` | `autoware_msgs/VehicleCmd.ctrl_cmd.linear_velocity` | `src/autoware/messages/autoware_msgs/msg/VehicleCmd.msg:9`; `ControlCommand.msg:1`; `xsugv_interface.cpp:157-165` | The driver reads this field as m/s, clamps at configured 5 km/h, then converts to its throttle representation. This confirms the field path and software conversion, not a safe J6M speed limit. |
| `target_steering_rad` | `VehicleCmd.ctrl_cmd.steering_angle` | `VehicleCmd.msg:9`; `ControlCommand.msg:3`; `xsugv_interface.cpp:166, 238` | The driver multiplies the field by 100, then converts the 0.01-degree value back by `* 0.01` before the IVCU packet. The adapter conversion is `radians * 180 / pi` to degrees. |
| `gear` | `VehicleCmd.gear_cmd.gear` | `VehicleCmd.msg:6`; `Gear.msg:1-7`; `xsugv_interface.cpp:179-187` | The legacy message declares `NONE=0`, `PARK=1`, `REVERSE=2`, `NEUTRAL=3`, `DRIVE=4`, `LOW=5`. The driver chooses its shift from this field and also from the sign of computed throttle. |
| `emergency_stop` | `VehicleCmd.emergency` | `VehicleCmd.msg:10`; `xsugv_interface.cpp:167, 235` | A positive integer is treated as an emergency flag, and the IVCU command's speed mode is set to its emergency value. This does not establish the physical stopping behavior. |
| `enable` | No direct `VehicleCmd` enable field | `VehicleCmd.msg:1-10`; `twist_gate.cpp:52, 58-68, 336` | Enable belongs to gateway owner arbitration and must require an explicit operator owner request plus all freshness and safety gates. It must not be guessed from `VehicleCmd.mode`. |
| Brake | `VehicleCmd.brake_cmd` exists | `VehicleCmd.msg:4`; `twist_gate.cpp:63, 97, 185, 263` | `twist_gate` handles and forwards brake data, but this audit does not establish a safe end-to-end brake mapping into the J6M vehicle path. **BRAKE = BLOCKED BY HARDWARE/RUNTIME VERIFICATION.** |

The source `twist_gate` advertises `/vehicle_cmd` and subscribes to the legacy
command topics `/twist_cmd`, `/mode_cmd`, `/gear_cmd`, `/accel_cmd`,
`/steer_cmd`, `/brake_cmd`, `/lamp_cmd`, `/ctrl_cmd`, `/decision_maker/state`,
and `emergency_velocity` (`twist_gate.cpp:52-68, 336`). A future deployment
must rewire that legacy output to `/vehicle_cmd_legacy`; this phase does not
edit its launch or source. The future adapter is intended to be the only
publisher of final `/vehicle_cmd`.

The intended minimum command mapping is:

| CNVG field | Future mapping rule |
|---|---|
| `target_speed_mps` | Copy to `ctrl_cmd.linear_velocity` after independent production limits are approved. |
| `target_steering_rad` | Convert radians to degrees and place in `ctrl_cmd.steering_angle`; do not add sign inversion, steering ratio, or saturation without hardware configuration. |
| `gear` | Use an explicit configured map. An absent entry means keep the current gear and make no gear change. No default mapping is installed. |
| `emergency_stop` | May map to integer `emergency` only after vehicle-owner review; actual IVCU response remains unknown. |
| `enable` | Ask the ROS-independent arbiter for explicit J6M ownership. Do not treat network reachability as authorization and do not overload `VehicleCmd.mode`. |
| brake | Do not map in this phase. Zero target plus disable is not physical braking. |

The ROS-independent production mapping core is in
`integration/cnvg_protocol/src/vehicle_mapping.cpp`; ROS message glue is in
`integration/legacy_autoware_gateway_ros1/src/vehicle_cmd_mapper.cpp`. Steering
sign, ratio, and limits are configuration-required, gear mapping is
configuration-only, and J6M brake/E-stop mapping remains disabled.

## Feedback evidence and limits

| Legacy feedback | Source evidence | Confirmed source behavior | CNVG scope |
|---|---|---|---|
| `/can_info.speed` | `CANInfo.msg:11`; `xsugv_interface.cpp:313-318` | Rear wheel speed magnitudes are scaled by 0.1 and averaged. The source values are km/h. | Vehicle-level speed only; conversion to m/s requires `/vehicle_velocity` or an explicit unit conversion. |
| `/can_info.angle` | `CANInfo.msg:21`; `xsugv_interface.cpp:318` | Steering integer is multiplied by 0.01; source labels the input as 0.01 degree. | Unit/sign and physical angle semantics still need runtime validation. |
| `/can_info.driveshift` | `CANInfo.msg:12`; `xsugv_interface.cpp:302-310` | Source shift values map to Parking, Reverse, Drive, or Neutral. | Values and feedback semantics are legacy-specific. |
| `/can_info.devmode`, `strmode` | `CANInfo.msg:3,15`; `xsugv_interface.cpp:311-312` | Both are set to 1 only when IVCU mode equals 3 (autonomous), otherwise 0. | Do not infer operator authorization from these flags. |
| `/driving_mode_viz` | `xsugv_interface.cpp:330-335, 438` | Mode labels are `None`, `Joystick`, `Remote`, `Auto`, or `Unknown`. | Mode mapping and transition timing require a running Autoware/vehicle setup. |
| `/vehicle_velocity` | `xsugv_interface.cpp:326-329, 437` | `linear.x` is wheel speed divided by 3.6; reverse shift negates it. | Candidate signed m/s feedback. Confirm the installed message type at runtime; adapter config requires `Twist` or `TwistStamped`. |
| `/imu_raw` | `xsugv_interface.cpp:351-361, 436` | Source scales accelerometer and gyro values by 0.01, forms orientation from scaled roll/pitch/heading, and publishes frame `/imu`. | Not bridged by CNVG. Sensor calibration, frame, and physical units require runtime review. |
| `/ublox_pose` | `xsugv_interface.cpp:364-377, 440` | Latitude/longitude are scaled by `1e-7`, altitude by `1e-2`; projection plane 19 is used and frame is `/map`. | Not bridged by CNVG. Datum, map alignment, and coordinate validity need runtime review. |

CNVG currently bridges only minimum vehicle-level command and state. It does
not carry IMU or GNSS. It also does not claim that zero speed plus `enable=false`
is equivalent to a brake command or physical stop.

## Unknown / runtime verification required

The source inspection cannot determine the active ROS graph, exact installed
message revisions, configured speed limit, effective steering sign, steering
ratio, maximum steering, wheel-angle meaning, brake actuation, gear interlocks,
E-stop physical behavior, watchdog behavior, or any safe operating envelope.
The `VehicleCmd.mode` values and their relationship to vehicle enable are not
fully established by this mapping. These remain **UNKNOWN / RUNTIME
VERIFICATION REQUIRED**.

CRC32 provides corruption detection, not authentication. A production network
must use an isolated vehicle Ethernet segment, explicit peer IP allowlisting,
firewall rules, source-address validation, and a dedicated port with no Internet
exposure. Cryptographic authentication is out of scope for Competition V1.
