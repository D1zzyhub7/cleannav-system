#ifndef J6M_VEHICLE_GATEWAY_ROS1_GATEWAY_NODE_HPP_
#define J6M_VEHICLE_GATEWAY_ROS1_GATEWAY_NODE_HPP_

#include "cnvg_protocol/command_arbiter.hpp"
#include "cnvg_protocol/production_config.hpp"
#include "cnvg_protocol/session_manager.hpp"
#include "cnvg_protocol/udp_transport.hpp"
#include "cnvg_protocol/vehicle_mapping.hpp"
#include "j6m_vehicle_gateway_ros1/state_mapper.hpp"

#include <autoware_msgs/VehicleCmd.h>
#include <diagnostic_msgs/DiagnosticArray.h>
#include <geometry_msgs/Twist.h>
#include <geometry_msgs/TwistStamped.h>
#include <ros/ros.h>
#include <std_msgs/Bool.h>
#include <std_msgs/String.h>
#include <std_srvs/SetBool.h>
#include <std_srvs/Trigger.h>
#include <autoware_can_msgs/CANInfo.h>

#include <cstdint>
#include <memory>
#include <string>

namespace j6m_vehicle_gateway_ros1 {

class GatewayNode {
 public:
  GatewayNode();

 private:
  bool load_config();
  bool request_owner(std_srvs::SetBool::Request& request,
                     std_srvs::SetBool::Response& response);
  bool release_owner(std_srvs::Trigger::Request& request,
                     std_srvs::Trigger::Response& response);
  bool driver_health_alive(std::uint64_t now_ms) const;
  bool other_vehicle_cmd_publishers();
  void legacy_cb(const autoware_msgs::VehicleCmd::ConstPtr& message);
  void velocity_cb(const geometry_msgs::TwistStamped::ConstPtr& message);
  void velocity_twist_cb(const geometry_msgs::Twist::ConstPtr& message);
  void can_cb(const autoware_can_msgs::CANInfo::ConstPtr& message);
  void mode_cb(const std_msgs::String::ConstPtr& message);
  void driver_cb(const std_msgs::Bool::ConstPtr& message);
  void receive_udp(std::uint64_t now_ms);
  void send_hello(std::uint64_t now_ms);
  void send_state(std::uint64_t now_ms);
  void timer_cb(const ros::TimerEvent& event);
  void publish_diagnostics(std::uint64_t now_ms,
                           const std::string& state,
                           const std::string& detail);

  ros::NodeHandle nh_;
  ros::NodeHandle pnh_;
  ros::Publisher final_pub_;
  ros::Publisher diagnostic_pub_;
  ros::Subscriber legacy_sub_;
  ros::Subscriber velocity_sub_;
  ros::Subscriber can_sub_;
  ros::Subscriber mode_sub_;
  ros::Subscriber driver_sub_;
  ros::ServiceServer owner_service_;
  ros::ServiceServer release_service_;
  ros::Timer timer_;

  cnvg::ProductionConfig config_;
  cnvg::VehicleMappingConfig mapping_;
  cnvg::PeerPolicy peer_policy_;
  std::unique_ptr<cnvg::SessionManager> session_;
  cnvg::CommandArbiter arbiter_;
  cnvg::UdpTransport udp_;
  StateMapper state_mapper_;

  autoware_msgs::VehicleCmd legacy_command_;
  autoware_msgs::VehicleCmd last_output_;
  cnvg::Message j6m_command_;
  bool have_legacy_;
  bool have_j6m_command_;
  bool have_driver_topic_;
  bool driver_value_;
  bool valid_config_;
  bool publisher_conflict_;
  bool software_estop_latched_;
  bool output_safe_zero_;
  std::uint64_t legacy_rx_ms_;
  std::uint64_t command_rx_ms_;
  std::uint64_t heartbeat_rx_ms_;
  std::uint64_t driver_rx_ms_;
  std::uint64_t local_session_id_;
  std::uint64_t last_hello_tx_ms_;
  std::uint32_t tx_sequence_;
  std::uint32_t rx_sequence_;
  std::uint32_t crc_errors_;
  std::uint32_t malformed_packets_;
  std::uint32_t sequence_errors_;
  std::uint32_t identity_errors_;
  std::uint32_t capability_errors_;
  std::uint32_t session_errors_;
  std::uint32_t wrong_peer_packets_;
  std::uint32_t tx_errors_;
  int publisher_count_;
  std::string legacy_topic_;
  std::string velocity_topic_;
  std::string can_topic_;
  std::string mode_topic_;
  std::string driver_topic_;
  std::string output_topic_;
  std::string detail_;
  std::string publisher_identities_;
  std::string driver_health_mode_;
  std::string steering_feedback_unit_;
  std::string vehicle_velocity_type_;
};

}  // namespace j6m_vehicle_gateway_ros1
#endif
