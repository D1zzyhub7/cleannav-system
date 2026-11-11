#include "cnvg_protocol/vehicle_mapping.hpp"

#include <cmath>

namespace cnvg {

bool map_vehicle_command(const Message& command,
                         const VehicleMappingConfig& config,
                         int current_gear,
                         VehicleCommand* output,
                         std::string* reason) {
  const char* generic_error = "invalid mapping configuration or command";
  if (output == NULL || !std::isfinite(command.target_speed_mps) ||
      !std::isfinite(command.target_steering_rad)) {
    if (reason != NULL) *reason = generic_error;
    return false;
  }
  if (!config.steering_configured ||
      !std::isfinite(config.steering_sign) ||
      std::abs(config.steering_sign) != 1.0 ||
      !std::isfinite(config.steering_ratio) || config.steering_ratio <= 0.0 ||
      !std::isfinite(config.steering_limit_rad) ||
      config.steering_limit_rad <= 0.0 ||
      std::abs(command.target_steering_rad) > config.steering_limit_rad) {
    if (reason != NULL) {
      *reason = "steering configuration missing or target exceeds configured limit";
    }
    return false;
  }

  VehicleCommand mapped;
  mapped.speed_mps = command.target_speed_mps;
  mapped.steering_degrees = command.target_steering_rad *
      config.steering_sign * config.steering_ratio *
      (180.0 / 3.14159265358979323846);
  mapped.gear = current_gear;
  if (command.gear != Gear::UNSPECIFIED) {
    const std::map<Gear, int>::const_iterator gear =
        config.gear_map.find(command.gear);
    if (gear == config.gear_map.end()) {
      if (reason != NULL) *reason = "requested gear has no configured mapping";
      return false;
    }
    if (gear->second < 0 || gear->second > 255) {
      if (reason != NULL) {
        *reason = "configured gear value is outside 0..255";
      }
      return false;
    }
    mapped.gear = gear->second;
    mapped.change_gear = true;
  }

  // Neither emergency nor brake is mapped from a network command here.
  mapped.emergency = 0;
  *output = mapped;
  if (reason != NULL) reason->clear();
  return true;
}

bool map_vehicle_state(const StateInput& input, MappedState* output) {
  if (output == NULL || !std::isfinite(input.speed_mps) ||
      !std::isfinite(input.steering_value)) {
    return false;
  }
  MappedState mapped;
  mapped.speed_mps = input.speed_mps;
  mapped.gear = input.gear;
  mapped.mode = input.mode;
  mapped.emergency = input.emergency;
  mapped.driver_alive = input.driver_alive;
  mapped.fault_code = input.fault_code;
  switch (input.steering_unit) {
    case SteeringFeedbackUnit::DEGREES:
      mapped.steering_rad = input.steering_value *
          (3.14159265358979323846 / 180.0);
      mapped.steering_unit_confirmed = true;
      break;
    case SteeringFeedbackUnit::RADIANS:
      mapped.steering_rad = input.steering_value;
      mapped.steering_unit_confirmed = true;
      break;
    case SteeringFeedbackUnit::UNCONFIRMED:
      mapped.steering_rad = 0.0;
      mapped.steering_unit_confirmed = false;
      break;
  }
  *output = mapped;
  return true;
}

}  // namespace cnvg
