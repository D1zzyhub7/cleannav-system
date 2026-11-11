#ifndef CNVG_PROTOCOL_COMMAND_ARBITER_HPP_
#define CNVG_PROTOCOL_COMMAND_ARBITER_HPP_
#include "cnvg_protocol/protocol.hpp"
#include <cstdint>
namespace cnvg {
enum class Owner { NONE, LEGACY_AUTOWARE, J6M };
enum class ArbiterState { OWNER_NONE, TRANSITION_TO_LEGACY, OWNER_LEGACY, TRANSITION_TO_J6M, OWNER_J6M, ESTOP_LOCKED, FAULT_LOCKED };
struct ArbiterInputs {
  bool legacy_command_fresh=false, j6m_session_alive=false, j6m_command_fresh=false, j6m_enable=false;
  VehicleMode vehicle_mode=VehicleMode::UNKNOWN;
  bool vehicle_fault=false, estop=false, safe_zero_confirmed=false, multiple_publishers=false;
  std::uint64_t monotonic_ms=0;
  std::uint32_t transition_dwell_ms=0;
};
struct ArbiterOutput { Owner owner=Owner::NONE, requested_owner=Owner::NONE; ArbiterState state=ArbiterState::OWNER_NONE; bool transitioning=false,safe_zero=true,enabled=false; };
class CommandArbiter {
 public:
  CommandArbiter();
  void request_owner(Owner owner); void clear_request();
  void reset_locks(bool operator_reset,bool physical_estop_clear_confirmed,bool fault_clear_confirmed);
  ArbiterOutput tick(const ArbiterInputs& inputs);
  Owner owner() const{return owner_;} Owner requested_owner() const{return requested_owner_;} ArbiterState state()const{return state_;}
 private:
  ArbiterOutput zero_output(bool transition)const;
  Owner owner_,requested_owner_,transition_target_; ArbiterState state_;
  bool transition_zero_seen_; std::uint64_t transition_zero_at_ms_;
};
}  // namespace cnvg
#endif
