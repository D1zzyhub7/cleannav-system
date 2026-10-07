#include "cnvg_protocol/command_arbiter.hpp"

namespace cnvg {

CommandArbiter::CommandArbiter()
    : owner_(Owner::NONE), requested_owner_(Owner::NONE),
      transition_target_(Owner::NONE), transitioning_(false) {}

void CommandArbiter::request_owner(Owner owner) {
  requested_owner_ = owner;
  transitioning_ = false;
  transition_target_ = Owner::NONE;
}

void CommandArbiter::clear_request() { request_owner(Owner::NONE); }

ArbiterOutput CommandArbiter::zero_output(bool transition) const {
  ArbiterOutput out;
  out.owner = owner_;
  out.requested_owner = requested_owner_;
  out.transitioning = transition;
  out.safe_zero = true;
  out.enabled = false;
  return out;
}

ArbiterOutput CommandArbiter::tick(const ArbiterInputs& in) {
  const bool globally_unsafe = in.estop || in.vehicle_fault ||
      in.vehicle_mode != VehicleMode::AUTONOMOUS;
  if (globally_unsafe) {
    owner_ = Owner::NONE;
    requested_owner_ = Owner::NONE;
    transition_target_ = Owner::NONE;
    transitioning_ = false;
    return zero_output(false);
  }

  // Any loss while J6M owns control clears the selection. It cannot silently
  // fall back to a still-fresh legacy command.
  if (owner_ == Owner::J6M &&
      (!in.j6m_session_alive || !in.j6m_command_fresh || !in.j6m_enable)) {
    owner_ = Owner::NONE;
    requested_owner_ = Owner::NONE;
    transition_target_ = Owner::NONE;
    transitioning_ = false;
    return zero_output(false);
  }
  if (owner_ == Owner::LEGACY_AUTOWARE && !in.legacy_command_fresh) {
    owner_ = Owner::NONE;
    requested_owner_ = Owner::NONE;
    transition_target_ = Owner::NONE;
    transitioning_ = false;
    return zero_output(false);
  }

  const Owner target = requested_owner_;
  if (target == Owner::NONE) {
    owner_ = Owner::NONE;
    transition_target_ = Owner::NONE;
    transitioning_ = false;
    return zero_output(false);
  }
  const bool target_ready = target == Owner::J6M
      ? in.j6m_session_alive && in.j6m_command_fresh && in.j6m_enable
      : in.legacy_command_fresh;
  if (!target_ready) {
    if (owner_ == target || (transitioning_ && transition_target_ == target)) {
      owner_ = Owner::NONE;
      requested_owner_ = Owner::NONE;
      transition_target_ = Owner::NONE;
      transitioning_ = false;
    }
    return zero_output(false);
  }

  if (owner_ == target && !transitioning_) {
    ArbiterOutput out;
    out.owner = owner_;
    out.requested_owner = requested_owner_;
    out.transitioning = false;
    out.safe_zero = false;
    out.enabled = true;
    return out;
  }

  if (!transitioning_ || transition_target_ != target) {
    owner_ = Owner::NONE;
    transition_target_ = target;
    transitioning_ = true;
    return zero_output(true);
  }
  if (!in.safe_zero_confirmed) return zero_output(true);

  owner_ = target;
  transitioning_ = false;
  transition_target_ = Owner::NONE;
  // The transition completion tick remains zero. Enable begins on the next
  // tick, after the downstream publisher has observed the owner change.
  return zero_output(false);
}

}  // namespace cnvg
