#include "j6m_vehicle_gateway_ros1/adapter_core.hpp"

namespace j6m_vehicle_gateway_ros1 {

AdapterNode::AdapterNode() : nh_(), private_nh_("~"), skeleton_enabled_(false) {
  private_nh_.param<std::string>("legacy_input_topic", legacy_input_topic_,
                                 "/vehicle_cmd_legacy");
  private_nh_.param<std::string>("output_vehicle_cmd_topic",
                                 output_vehicle_cmd_topic_, "/vehicle_cmd");
  private_nh_.param<bool>("skeleton_enabled", skeleton_enabled_, false);

  legacy_command_sub_ = nh_.subscribe(
      legacy_input_topic_, 1, &AdapterNode::legacy_command_cb, this);
  final_vehicle_cmd_pub_ = nh_.advertise<autoware_msgs::VehicleCmd>(
      output_vehicle_cmd_topic_, 1);
  timer_ = nh_.createTimer(ros::Duration(0.02), &AdapterNode::timer_cb, this);

  ROS_WARN("ROS1 gateway source skeleton is inert: UDP receive, operator "
           "selection, and final command publication are not implemented");
}

void AdapterNode::legacy_command_cb(
    const autoware_msgs::VehicleCmd::ConstPtr& message) {
  // Legacy input is cached behind the arbiter. Never republish this callback
  // directly; the final topic must have one publisher after production work.
  legacy_command_ = *message;
}

void AdapterNode::timer_cb(const ros::TimerEvent&) {
  (void)arbiter_;
  (void)configured_gear_map_;
  (void)legacy_command_;
  if (skeleton_enabled_) {
    // Intentionally no /vehicle_cmd publication in this preparation skeleton.
    // Future flow: UDP receiver -> cnvg::decode -> J6M command state ->
    // cnvg::CommandArbiter -> VehicleCmd mapper -> this single publisher.
    // twist_gate must be configured to publish /vehicle_cmd_legacy first.
  }
}

}  // namespace j6m_vehicle_gateway_ros1

int main(int argc, char** argv) {
  ros::init(argc, argv, "j6m_vehicle_gateway_ros1");
  j6m_vehicle_gateway_ros1::AdapterNode node;
  ros::spin();
  return 0;
}
