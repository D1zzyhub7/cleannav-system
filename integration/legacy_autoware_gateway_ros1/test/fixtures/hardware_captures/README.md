# Hardware capture fixtures

This directory is intentionally empty apart from this workflow note. Do not
create synthetic or guessed captures. After authorized hardware access, save
separate, timestamped captures here and record the interface, capture filter,
vehicle mode, operator, and safety setup in a companion note:

- `ivcu_idle.pcap`
- `ivcu_autoware_zero.pcap`
- `ivcu_forward_low_speed.pcap`
- `ivcu_steering_left.pcap`
- `ivcu_steering_right.pcap`
- `ivcu_stop.pcap`
- `ivcu_estop_if_safe.pcap`

Capture only after a written safety review. Never probe UDP 4500, 4501, or 6667
in this offline stage. The E-stop capture is conditional on an approved safe
procedure and must not be induced for this preparation work.
