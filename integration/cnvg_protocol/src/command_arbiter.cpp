#include "cnvg_protocol/command_arbiter.hpp"

namespace cnvg {

CommandArbiter::CommandArbiter()
    : owner_(Owner::NONE),
      requested_owner_(Owner::NONE),
      transition_target_(Owner::NONE),
      state_(ArbiterState::OWNER_NONE),
      transition_zero_seen_(false),
      transition_zero_at_ms_(0) {}

void CommandArbiter::request_owner(Owner owner) {
  if (state_ == ArbiterState::ESTOP_LOCKED ||
      state_ == ArbiterState::FAULT_LOCKED) {
    return;
  }
  requested_owner_ = owner;
  transition_target_ = Owner::NONE;
  transition_zero_seen_ = false;
}

void CommandArbiter::clear_request() {
  if (state_ == ArbiterState::ESTOP_LOCKED ||
      state_ == ArbiterState::FAULT_LOCKED) {
    return;
  }
  requested_owner_ = Owner::NONE;
  owner_ = Owner::NONE;
  state_ = ArbiterState::OWNER_NONE;
  transition_target_ = Owner::NONE;
  transition_zero_seen_ = false;
}

void CommandArbiter::reset_locks(bool operator_reset,
                                 bool physical_estop_clear_confirmed,
                                 bool fault_clear_confirmed) {
  if (!operator_reset) return;
  if (state_ == ArbiterState::ESTOP_LOCKED &&
      physical_estop_clear_confirmed) {
    state_ = ArbiterState::OWNER_NONE;
    requested_owner_ = Owner::NONE;
    owner_ = Owner::NONE;
  }
  if (state_ == ArbiterState::FAULT_LOCKED && fault_clear_confirmed) {
    state_ = ArbiterState::OWNER_NONE;
    requested_owner_ = Owner::NONE;
    owner_ = Owner::NONE;
  }
}

ArbiterOutput CommandArbiter::zero_output(bool transitioning) const {
  ArbiterOutput output;
  output.owner = owner_;
  output.requested_owner = requested_owner_;
  output.state = state_;
  output.transitioning = transitioning;
  output.safe_zero = true;
  output.enabled = false;
  return output;
}

ArbiterOutput CommandArbiter::tick(const ArbiterInputs& inputs) {
  if (inputs.estop) {
    owner_ = Owner::NONE;
    requested_owner_ = Owner::NONE;
    state_ = ArbiterState::ESTOP_LOCKED;
    transition_target_ = Owner::NONE;
    return zero_output(false);
  }
  if (inputs.vehicle_fault || inputs.multiple_publishers) {
    owner_ = Owner::NONE;
    requested_owner_ = Owner::NONE;
    state_ = ArbiterState::FAULT_LOCKED;
    transition_target_ = Owner::NONE;
    return zero_output(false);
  }
  if (state_ == ArbiterState::ESTOP_LOCKED ||
      state_ == ArbiterState::FAULT_LOCKED) {
    return zero_output(false);
  }
  if (inputs.vehicle_mode != VehicleMode::AUTONOMOUS) {
    clear_request();
    return zero_output(false);
  }
  if ((owner_ == Owner::J6M &&
       (!inputs.j6m_session_alive || !inputs.j6m_command_fresh ||
        !inputs.j6m_enable)) ||
      (owner_ == Owner::LEGACY_AUTOWARE &&
       !inputs.legacy_command_fresh)) {
    clear_request();
    return zero_output(false);
  }

  const Owner target = requested_owner_;
  if (target == Owner::NONE) {
    clear_request();
    return zero_output(false);
  }
  const bool target_ready = target == Owner::J6M
      ? inputs.j6m_session_alive && inputs.j6m_command_fresh &&
            inputs.j6m_enable
      : inputs.legacy_command_fresh;
  if (!target_ready) {
    const ArbiterState requested_transition = target == Owner::J6M
        ? ArbiterState::TRANSITION_TO_J6M
        : ArbiterState::TRANSITION_TO_LEGACY;
    if (owner_ != Owner::NONE && owner_ != target) {
      // An explicit switch relinquishes the current owner first. If the new
      // source is not ready, output remains zero and state reports NONE.
      owner_ = Owner::NONE;
      state_ = ArbiterState::OWNER_NONE;
      transition_target_ = Owner::NONE;
      transition_zero_seen_ = false;
    } else if (state_ == requested_transition &&
               transition_target_ == target) {
      clear_request();
    }
    return zero_output(false);
  }

  if (owner_ == target &&
      ((target == Owner::J6M && state_ == ArbiterState::OWNER_J6M) ||
       (target == Owner::LEGACY_AUTOWARE &&
        state_ == ArbiterState::OWNER_LEGACY))) {
    ArbiterOutput output;
    output.owner = owner_;
    output.requested_owner = requested_owner_;
    output.state = state_;
    output.safe_zero = false;
    output.enabled = true;
    return output;
  }

  const ArbiterState transition_state = target == Owner::J6M
      ? ArbiterState::TRANSITION_TO_J6M
      : ArbiterState::TRANSITION_TO_LEGACY;
  if (transition_target_ != target || state_ != transition_state) {
    owner_ = Owner::NONE;
    transition_target_ = target;
    state_ = transition_state;
    transition_zero_seen_ = false;
  }
  if (!inputs.safe_zero_confirmed) {
    transition_zero_seen_ = false;
    return zero_output(true);
  }
  if (!transition_zero_seen_) {
    transition_zero_seen_ = true;
    transition_zero_at_ms_ = inputs.monotonic_ms;
  }
  if (inputs.monotonic_ms - transition_zero_at_ms_ <
      inputs.transition_dwell_ms) {
    return zero_output(true);
  }

  owner_ = target;
  state_ = target == Owner::J6M ? ArbiterState::OWNER_J6M
                                : ArbiterState::OWNER_LEGACY;
  transition_target_ = Owner::NONE;
  transition_zero_seen_ = false;
  return zero_output(false);
}

}  // namespace cnvg
