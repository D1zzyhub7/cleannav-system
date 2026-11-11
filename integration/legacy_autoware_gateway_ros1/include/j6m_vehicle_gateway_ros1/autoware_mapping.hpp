#ifndef J6M_VEHICLE_GATEWAY_ROS1_AUTOWARE_MAPPING_HPP_
#define J6M_VEHICLE_GATEWAY_ROS1_AUTOWARE_MAPPING_HPP_

#include "cnvg_protocol/protocol.hpp"

#include <cmath>
#include <cstdint>
#include <map>

namespace j6m_vehicle_gateway_ros1 {

inline double radians_to_degrees(double radians) {
  return radians * (180.0 / 3.14159265358979323846);
}

// No enum assumptions are installed in code. A missing or invalid configured
// entry means preserve the current VehicleCmd gear; it never guesses a value.
inline bool map_gear(cnvg::Gear source,
                     const std::map<cnvg::Gear, std::int32_t>& configured,
                     std::int32_t* destination) {
  if (destination == NULL) return false;
  const std::map<cnvg::Gear, std::int32_t>::const_iterator found =
      configured.find(source);
  if (found == configured.end() || found->second < 0 || found->second > 255) {
    return false;
  }
  *destination = found->second;
  return true;
}

}  // namespace j6m_vehicle_gateway_ros1

#endif  // J6M_VEHICLE_GATEWAY_ROS1_AUTOWARE_MAPPING_HPP_
