#ifndef J6M_VEHICLE_GATEWAY_ROS1_STATE_MAPPER_HPP_
#define J6M_VEHICLE_GATEWAY_ROS1_STATE_MAPPER_HPP_

#include "cnvg_protocol/freshness.hpp"
#include "cnvg_protocol/vehicle_mapping.hpp"

#include <autoware_can_msgs/CANInfo.h>
#include <geometry_msgs/Twist.h>
#include <geometry_msgs/TwistStamped.h>
#include <ros/ros.h>
#include <std_msgs/String.h>

#include <cstdint>
#include <string>

namespace j6m_vehicle_gateway_ros1 {

class StateMapper {
 public:
  explicit StateMapper(const std::string& steering_unit);
  void velocity(const geometry_msgs::TwistStamped::ConstPtr& message);
  void velocity(const geometry_msgs::Twist::ConstPtr& message);
  void can(const autoware_can_msgs::CANInfo::ConstPtr& message);
  void driving_mode(const std_msgs::String::ConstPtr& message);
  bool fresh(std::uint64_t now_ms, std::uint32_t timeout_ms) const;
  bool map(std::uint64_t now_ms,
           bool driver_alive,
           cnvg::Message* output,
           bool* steering_unit_confirmed) const;
  std::uint64_t age_ms(std::uint64_t now_ms) const;
  cnvg::VehicleMode vehicle_mode() const;

 private:
  cnvg::StateInput input_;
  std::uint64_t velocity_rx_ms_;
  std::uint64_t can_rx_ms_;
  std::uint64_t mode_rx_ms_;
  bool have_velocity_;
  bool have_can_;
  bool have_mode_;
  bool autonomous_confirmed_;
  bool driving_auto_viz_;
  bool can_auto_confirmed_;
};

std::uint64_t monotonic_ms();

}  // namespace j6m_vehicle_gateway_ros1
#endif  // J6M_VEHICLE_GATEWAY_ROS1_STATE_MAPPER_HPP_
