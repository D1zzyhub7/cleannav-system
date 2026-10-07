#ifndef CNVG_PROTOCOL_COMMAND_ARBITER_HPP_
#define CNVG_PROTOCOL_COMMAND_ARBITER_HPP_

#include "cnvg_protocol/protocol.hpp"

namespace cnvg {

enum class Owner { NONE, LEGACY_AUTOWARE, J6M };

struct ArbiterInputs {
  bool legacy_command_fresh = false;
  bool j6m_session_alive = false;
  bool j6m_command_fresh = false;
  bool j6m_enable = false;
  VehicleMode vehicle_mode = VehicleMode::UNKNOWN;
  bool vehicle_fault = false;
  bool estop = false;
  // Set only after the output path has applied a complete safe-zero cycle.
  bool safe_zero_confirmed = false;
};

struct ArbiterOutput {
  Owner owner = Owner::NONE;
  Owner requested_owner = Owner::NONE;
  bool transitioning = false;
  bool safe_zero = true;
  bool enabled = false;
};

// ROS-independent owner arbitration for a future ROS1 adapter.
// Selection changes are operator requests; packet arrival never selects J6M.
class CommandArbiter {
 public:
  CommandArbiter();
  void request_owner(Owner owner);
  void clear_request();
  ArbiterOutput tick(const ArbiterInputs& inputs);
  Owner owner() const { return owner_; }
  Owner requested_owner() const { return requested_owner_; }
 private:
  ArbiterOutput zero_output(bool transition) const;
  Owner owner_;
  Owner requested_owner_;
  Owner transition_target_;
  bool transitioning_;
};

}  // namespace cnvg

#endif  // CNVG_PROTOCOL_COMMAND_ARBITER_HPP_
