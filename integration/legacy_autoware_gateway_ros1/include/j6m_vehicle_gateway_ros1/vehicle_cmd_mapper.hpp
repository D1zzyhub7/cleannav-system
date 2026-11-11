#ifndef J6M_VEHICLE_GATEWAY_ROS1_VEHICLE_CMD_MAPPER_HPP_
#define J6M_VEHICLE_GATEWAY_ROS1_VEHICLE_CMD_MAPPER_HPP_
#include "cnvg_protocol/vehicle_mapping.hpp"
#include <autoware_msgs/VehicleCmd.h>
namespace j6m_vehicle_gateway_ros1 {
bool map_j6m_command(const cnvg::Message& source,const cnvg::VehicleMappingConfig& config,const autoware_msgs::VehicleCmd& current,autoware_msgs::VehicleCmd* output,std::string* reason);
autoware_msgs::VehicleCmd safe_zero_command(int current_gear = 0);
}
#endif
