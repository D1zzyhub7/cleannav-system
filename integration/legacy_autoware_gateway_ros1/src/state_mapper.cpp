#include "j6m_vehicle_gateway_ros1/state_mapper.hpp"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <limits>

namespace j6m_vehicle_gateway_ros1 {

std::uint64_t monotonic_ms() {
  return static_cast<std::uint64_t>(
      std::chrono::duration_cast<std::chrono::milliseconds>(
          std::chrono::steady_clock::now().time_since_epoch()).count());
}

StateMapper::StateMapper(const std::string& steering_unit)
    : velocity_rx_ms_(0),
      can_rx_ms_(0),
      mode_rx_ms_(0),
      have_velocity_(false),
      have_can_(false),
      have_mode_(false),
      autonomous_confirmed_(false),
      driving_auto_viz_(false),
      can_auto_confirmed_(false) {
  if (steering_unit == "DEGREES") {
    input_.steering_unit = cnvg::SteeringFeedbackUnit::DEGREES;
  } else if (steering_unit == "RADIANS") {
    input_.steering_unit = cnvg::SteeringFeedbackUnit::RADIANS;
  } else {
    input_.steering_unit = cnvg::SteeringFeedbackUnit::UNCONFIRMED;
  }
}

void StateMapper::velocity(const geometry_msgs::TwistStamped::ConstPtr& message) {
  input_.speed_mps = message->twist.linear.x;
  velocity_rx_ms_ = monotonic_ms();
  have_velocity_ = std::isfinite(input_.speed_mps);
}

void StateMapper::velocity(const geometry_msgs::Twist::ConstPtr& message) {
  input_.speed_mps = message->linear.x;
  velocity_rx_ms_ = monotonic_ms();
  have_velocity_ = std::isfinite(input_.speed_mps);
}

void StateMapper::can(const autoware_can_msgs::CANInfo::ConstPtr& message) {
  // CANInfo source code labels angle as 0.01 degree. The configured unit must
  // be confirmed at runtime; UNCONFIRMED feedback is never used as a number.
  input_.steering_value =
      input_.steering_unit == cnvg::SteeringFeedbackUnit::DEGREES
          ? static_cast<double>(message->angle) * 0.01
          : static_cast<double>(message->angle);
  input_.driver_alive = true;
  can_auto_confirmed_ = message->devmode == 1 && message->strmode == 1;
  autonomous_confirmed_ = driving_auto_viz_ && can_auto_confirmed_;
  input_.mode = autonomous_confirmed_ ? cnvg::VehicleMode::AUTONOMOUS
                                      : cnvg::VehicleMode::MANUAL;
  can_rx_ms_ = monotonic_ms();
  have_can_ = true;
}

void StateMapper::driving_mode(const std_msgs::String::ConstPtr& message) {
  driving_auto_viz_ = message->data == "Auto";
  autonomous_confirmed_ = driving_auto_viz_ && can_auto_confirmed_;
  input_.mode = autonomous_confirmed_ ? cnvg::VehicleMode::AUTONOMOUS
                                      : cnvg::VehicleMode::MANUAL;
  mode_rx_ms_ = monotonic_ms();
  have_mode_ = true;
}

bool StateMapper::fresh(std::uint64_t now_ms,
                        std::uint32_t timeout_ms) const {
  return have_velocity_ && have_can_ && have_mode_ &&
         cnvg::monotonic_fresh(now_ms, velocity_rx_ms_, timeout_ms) &&
         cnvg::monotonic_fresh(now_ms, can_rx_ms_, timeout_ms) &&
         cnvg::monotonic_fresh(now_ms, mode_rx_ms_, timeout_ms);
}

cnvg::VehicleMode StateMapper::vehicle_mode() const {
  return autonomous_confirmed_ ? cnvg::VehicleMode::AUTONOMOUS
                               : cnvg::VehicleMode::MANUAL;
}

std::uint64_t StateMapper::age_ms(std::uint64_t now_ms) const {
  if (!have_velocity_ || !have_can_ || !have_mode_) return UINT64_MAX;
  const std::uint64_t velocity_age = now_ms - velocity_rx_ms_;
  const std::uint64_t can_age = now_ms - can_rx_ms_;
  const std::uint64_t mode_age = now_ms - mode_rx_ms_;
  return std::max(velocity_age, std::max(can_age, mode_age));
}

bool StateMapper::map(std::uint64_t now_ms,
                      bool driver_alive,
                      cnvg::Message* output,
                      bool* steering_unit_confirmed) const {
  if (output == NULL || !fresh(now_ms, std::numeric_limits<std::uint32_t>::max())) return false;
  cnvg::StateInput input = input_;
  input.mode = vehicle_mode();
  input.driver_alive = driver_alive;

  cnvg::MappedState mapped;
  if (!cnvg::map_vehicle_state(input, &mapped)) return false;
  output->speed_mps = static_cast<float>(mapped.speed_mps);
  output->steering_rad = static_cast<float>(mapped.steering_rad);
  output->gear = mapped.gear;
  output->vehicle_mode = mapped.mode;
  output->emergency = mapped.emergency;
  output->driver_alive = mapped.driver_alive;
  output->fault_code = mapped.fault_code;
  output->gateway_alive = true;
  if (steering_unit_confirmed != NULL) {
    *steering_unit_confirmed = mapped.steering_unit_confirmed;
  }
  return true;
}

}  // namespace j6m_vehicle_gateway_ros1
