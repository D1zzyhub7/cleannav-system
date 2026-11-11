#ifndef CNVG_PROTOCOL_VEHICLE_MAPPING_HPP_
#define CNVG_PROTOCOL_VEHICLE_MAPPING_HPP_

#include "cnvg_protocol/protocol.hpp"

#include <map>
#include <string>

namespace cnvg {

struct VehicleMappingConfig {
  bool steering_configured = false;
  double steering_sign = 0.0;
  double steering_ratio = 0.0;
  double steering_limit_rad = 0.0;
  std::map<Gear, int> gear_map;
};

struct VehicleCommand {
  double speed_mps = 0.0;
  double steering_degrees = 0.0;
  int gear = 0;
  int emergency = 0;
  bool change_gear = false;
};

bool map_vehicle_command(const Message& command,
                         const VehicleMappingConfig& config,
                         int current_gear,
                         VehicleCommand* output,
                         std::string* reason);

enum class SteeringFeedbackUnit { UNCONFIRMED, DEGREES, RADIANS };

struct StateInput {
  double speed_mps = 0.0;
  double steering_value = 0.0;
  SteeringFeedbackUnit steering_unit = SteeringFeedbackUnit::UNCONFIRMED;
  Gear gear = Gear::UNSPECIFIED;
  VehicleMode mode = VehicleMode::UNKNOWN;
  bool emergency = false;
  bool driver_alive = false;
  std::uint32_t fault_code = FAULT_CODE_UNKNOWN;
};

struct MappedState {
  double speed_mps = 0.0;
  double steering_rad = 0.0;
  Gear gear = Gear::UNSPECIFIED;
  VehicleMode mode = VehicleMode::UNKNOWN;
  bool steering_unit_confirmed = false;
  bool emergency = false;
  bool driver_alive = false;
  std::uint32_t fault_code = FAULT_CODE_UNKNOWN;
};

bool map_vehicle_state(const StateInput& input, MappedState* output);

}  // namespace cnvg
#endif  // CNVG_PROTOCOL_VEHICLE_MAPPING_HPP_
