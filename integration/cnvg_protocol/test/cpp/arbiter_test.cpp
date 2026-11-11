#include "cnvg_protocol/command_arbiter.hpp"
#include "j6m_vehicle_gateway_ros1/autoware_mapping.hpp"

#include <cassert>
#include <iostream>
#include <cmath>
#include <map>

using cnvg::ArbiterInputs;
using cnvg::ArbiterOutput;
using cnvg::CommandArbiter;
using cnvg::Owner;
using cnvg::VehicleMode;

ArbiterInputs base() {
  ArbiterInputs in; in.vehicle_mode = VehicleMode::AUTONOMOUS;
  in.legacy_command_fresh = true; in.j6m_session_alive = true;
  in.j6m_command_fresh = true; in.j6m_enable = true; return in;
}
void complete_transition(CommandArbiter& arbiter, ArbiterInputs in, Owner expected) {
  ArbiterOutput out = arbiter.tick(in);
  assert(out.safe_zero && out.transitioning && !out.enabled);
  in.safe_zero_confirmed = false;
  out = arbiter.tick(in);
  assert(out.safe_zero && out.transitioning && !out.enabled);
  in.safe_zero_confirmed = true;
  out = arbiter.tick(in);
  assert(out.owner == expected && out.safe_zero && !out.enabled);
  in.safe_zero_confirmed = false;
  out = arbiter.tick(in);
  assert(out.owner == expected && out.enabled && !out.safe_zero);
}
int main() {
  {
    cnvg::SequenceWindow window;
    assert(window.accept(0xfffffffeu) == cnvg::SequenceDisposition::ACCEPT);
    assert(window.accept(0xffffffffu) == cnvg::SequenceDisposition::ACCEPT);
    assert(window.accept(0u) == cnvg::SequenceDisposition::ACCEPT);
    assert(window.accept(0u) == cnvg::SequenceDisposition::DUPLICATE);
    assert(window.accept(0xffffffffu) == cnvg::SequenceDisposition::OUT_OF_ORDER);
    window.reset();
    assert(!window.initialized());
    assert(window.accept(0u) == cnvg::SequenceDisposition::ACCEPT);
  }
  {
    assert(std::abs(j6m_vehicle_gateway_ros1::radians_to_degrees(1.0) -
                    57.29577951308232) < 1e-10);
    std::map<cnvg::Gear, std::int32_t> empty_map;
    std::int32_t destination = 123;
    assert(!j6m_vehicle_gateway_ros1::map_gear(cnvg::Gear::DRIVE, empty_map,
                                               &destination));
    assert(destination == 123);  // Missing configuration never changes gear.
    empty_map[cnvg::Gear::DRIVE] = 4;
    assert(j6m_vehicle_gateway_ros1::map_gear(cnvg::Gear::DRIVE, empty_map,
                                               &destination));
    assert(destination == 4);
    empty_map[cnvg::Gear::PARK] = 256;
    assert(!j6m_vehicle_gateway_ros1::map_gear(cnvg::Gear::PARK, empty_map,
                                               &destination));
    assert(destination == 4);
  }
  {
    CommandArbiter a; ArbiterInputs in = base(); a.request_owner(Owner::LEGACY_AUTOWARE);
    complete_transition(a, in, Owner::LEGACY_AUTOWARE);
  }
  {
    CommandArbiter a; ArbiterInputs in = base(); a.request_owner(Owner::J6M);
    complete_transition(a, in, Owner::J6M);
  }
  {
    CommandArbiter a; ArbiterInputs in = base(); a.request_owner(Owner::LEGACY_AUTOWARE);
    complete_transition(a, in, Owner::LEGACY_AUTOWARE);
    in = base(); a.tick(in);  // A live J6M packet cannot change the selection.
    assert(a.owner() == Owner::LEGACY_AUTOWARE);
  }
  {
    CommandArbiter a; ArbiterInputs in = base(); a.request_owner(Owner::LEGACY_AUTOWARE);
    complete_transition(a, in, Owner::LEGACY_AUTOWARE);
    a.request_owner(Owner::J6M); in = base();
    complete_transition(a, in, Owner::J6M);  // Explicit switch passes through zero.
  }
  {
    CommandArbiter a; ArbiterInputs in = base(); a.request_owner(Owner::J6M);
    complete_transition(a, in, Owner::J6M);
    in = base(); in.j6m_session_alive = false;
    const ArbiterOutput out = a.tick(in);
    assert(out.owner == Owner::NONE && out.requested_owner == Owner::NONE && out.safe_zero);
  }
  {
    for (int reason = 0; reason < 3; ++reason) {
      CommandArbiter a; ArbiterInputs in = base(); a.request_owner(Owner::J6M);
      complete_transition(a, in, Owner::J6M); in = base();
      if (reason == 0) in.estop = true;
      if (reason == 1) in.vehicle_mode = VehicleMode::MANUAL;
      if (reason == 2) in.vehicle_fault = true;
      const ArbiterOutput out = a.tick(in);
      assert(out.owner == Owner::NONE && out.requested_owner == Owner::NONE && out.safe_zero);
    }
  }
  {
    CommandArbiter a; ArbiterInputs in = base(); a.request_owner(Owner::LEGACY_AUTOWARE);
    complete_transition(a, in, Owner::LEGACY_AUTOWARE);
    a.request_owner(Owner::J6M); in = base(); complete_transition(a, in, Owner::J6M);
    in = base(); in.j6m_session_alive = false;
    a.tick(in); assert(a.owner() == Owner::NONE);
    // Still-fresh legacy input is never promoted without a new request.
    in = base(); const ArbiterOutput out = a.tick(in);
    assert(out.owner == Owner::NONE && !out.enabled);
  }
  {
    CommandArbiter a; ArbiterInputs in = base(); a.request_owner(Owner::J6M);
    complete_transition(a, in, Owner::J6M);
    a.request_owner(Owner::LEGACY_AUTOWARE); in = base();
    complete_transition(a, in, Owner::LEGACY_AUTOWARE);
  }
  {
    CommandArbiter a; ArbiterInputs in = base(); a.request_owner(Owner::LEGACY_AUTOWARE);
    complete_transition(a, in, Owner::LEGACY_AUTOWARE);
    in = base(); in.legacy_command_fresh = false;
    const ArbiterOutput out = a.tick(in);
    assert(out.owner == Owner::NONE && out.safe_zero && !out.enabled);
    // A live J6M peer cannot inherit a stale legacy owner's request.
    in = base(); assert(a.tick(in).owner == Owner::NONE);
  }
  {
    CommandArbiter a; ArbiterInputs in = base(); a.request_owner(Owner::J6M);
    complete_transition(a, in, Owner::J6M);
    in = base(); in.multiple_publishers = true;
    assert(a.tick(in).state == cnvg::ArbiterState::FAULT_LOCKED);
    in.multiple_publishers = false;
    assert(a.tick(in).state == cnvg::ArbiterState::FAULT_LOCKED);
  }
  {
    CommandArbiter a; ArbiterInputs in = base();
    a.request_owner(Owner::LEGACY_AUTOWARE);
    complete_transition(a, in, Owner::LEGACY_AUTOWARE);
    a.request_owner(Owner::J6M);
    in = base(); in.j6m_session_alive = false;
    const ArbiterOutput out = a.tick(in);
    assert(out.owner == Owner::NONE && out.safe_zero && !out.enabled);
    assert(a.requested_owner() == Owner::J6M);
    // The current owner is relinquished while J6M is not ready; there is no
    // silent Legacy output or automatic fallback.
  }
  std::cout << "arbiter, sequence, and mapping cases passed\n";
  return 0;
}
