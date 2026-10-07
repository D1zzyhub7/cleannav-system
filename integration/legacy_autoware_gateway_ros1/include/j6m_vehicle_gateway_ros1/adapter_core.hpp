#ifndef J6M_VEHICLE_GATEWAY_ROS1_ADAPTER_CORE_HPP_
#define J6M_VEHICLE_GATEWAY_ROS1_ADAPTER_CORE_HPP_

#include "cnvg_protocol/command_arbiter.hpp"
#include "j6m_vehicle_gateway_ros1/autoware_mapping.hpp"

#include <autoware_msgs/VehicleCmd.h>
#include <ros/ros.h>

#include <map>
#include <string>

namespace j6m_vehicle_gateway_ros1 {

class AdapterNode {
 public:
  AdapterNode();
 private:
  void legacy_command_cb(const autoware_msgs::VehicleCmd::ConstPtr& message);
  void timer_cb(const ros::TimerEvent& event);

  ros::NodeHandle nh_;
  ros::NodeHandle private_nh_;
  ros::Subscriber legacy_command_sub_;
  // This is the only final VehicleCmd publisher in this adapter package.
  ros::Publisher final_vehicle_cmd_pub_;
  ros::Timer timer_;
  cnvg::CommandArbiter arbiter_;
  autoware_msgs::VehicleCmd legacy_command_;
  std::map<cnvg::Gear, std::int32_t> configured_gear_map_;
  std::string legacy_input_topic_;
  std::string output_vehicle_cmd_topic_;
  bool skeleton_enabled_;
};

}  // namespace j6m_vehicle_gateway_ros1

#endif  // J6M_VEHICLE_GATEWAY_ROS1_ADAPTER_CORE_HPP_
