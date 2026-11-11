#include "j6m_vehicle_gateway_ros1/vehicle_cmd_mapper.hpp"

namespace j6m_vehicle_gateway_ros1 {

bool map_j6m_command(const cnvg::Message& source,
                     const cnvg::VehicleMappingConfig& config,
                     const autoware_msgs::VehicleCmd& current,
                     autoware_msgs::VehicleCmd* output,
                     std::string* reason) {
  if (output == NULL) return false;
  cnvg::VehicleCommand mapped;
  const int current_gear = current.gear_cmd.gear;
  if (!cnvg::map_vehicle_command(source, config, current_gear, &mapped,
                                 reason)) {
    return false;
  }

  // Construct a fresh message so cached legacy brake fields cannot leak into
  // the J6M path. Brake and physical emergency behavior remain unmapped.
  autoware_msgs::VehicleCmd result;
  result.ctrl_cmd.linear_velocity = mapped.speed_mps;
  result.ctrl_cmd.steering_angle = mapped.steering_degrees;
  result.gear_cmd.gear = mapped.gear;
  result.emergency = mapped.emergency;
  *output = result;
  return true;
}

autoware_msgs::VehicleCmd safe_zero_command(int current_gear) {
  autoware_msgs::VehicleCmd result;
  result.ctrl_cmd.linear_velocity = 0.0;
  result.ctrl_cmd.steering_angle = 0.0;
  result.gear_cmd.gear = current_gear;
  result.emergency = 0;
  return result;
}

}  // namespace j6m_vehicle_gateway_ros1
