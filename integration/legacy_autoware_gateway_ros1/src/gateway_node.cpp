#include "j6m_vehicle_gateway_ros1/gateway_node.hpp"

#include "cnvg_protocol/freshness.hpp"
#include "j6m_vehicle_gateway_ros1/vehicle_cmd_mapper.hpp"

#include <XmlRpcValue.h>
#include <ros/master.h>

#include <cmath>
#include <cstdlib>
#include <sstream>
#include <stdexcept>
#include <unistd.h>
#include <vector>

namespace j6m_vehicle_gateway_ros1 {
namespace {

bool read_number(ros::NodeHandle& node,
                 const std::string& key,
                 double* output) {
  XmlRpc::XmlRpcValue raw;
  if (output == NULL || !node.getParam(key, raw)) return false;
  if (raw.getType() == XmlRpc::XmlRpcValue::TypeInt) {
    *output = static_cast<int>(raw);
    return true;
  }
  if (raw.getType() == XmlRpc::XmlRpcValue::TypeDouble) {
    *output = static_cast<double>(raw);
    return true;
  }
  if (raw.getType() != XmlRpc::XmlRpcValue::TypeString) return false;
  const std::string text = static_cast<std::string>(raw);
  if (text.empty() || text == "UNSET") return false;
  char* end = NULL;
  const double value = std::strtod(text.c_str(), &end);
  if (end == text.c_str() || *end != '\0') return false;
  *output = value;
  return true;
}

bool read_port(ros::NodeHandle& node,
               const std::string& key,
               std::uint32_t* output) {
  double value = 0.0;
  if (output == NULL || !read_number(node, key, &value) || value < 1.0 ||
      value > 65535.0 || std::floor(value) != value) {
    return false;
  }
  *output = static_cast<std::uint32_t>(value);
  return true;
}

std::uint64_t new_session_id() {
  return (monotonic_ms() << 16) ^ static_cast<std::uint64_t>(::getpid());
}

}  // namespace

GatewayNode::GatewayNode()
    : nh_(),
      pnh_("~"),
      state_mapper_("UNCONFIRMED"),
      have_legacy_(false),
      have_j6m_command_(false),
      have_driver_topic_(false),
      driver_value_(false),
      valid_config_(false),
      publisher_conflict_(false),
      software_estop_latched_(false),
      output_safe_zero_(true),
      legacy_rx_ms_(0),
      command_rx_ms_(0),
      heartbeat_rx_ms_(0),
      driver_rx_ms_(0),
      local_session_id_(new_session_id()),
      last_hello_tx_ms_(0),
      tx_sequence_(0),
      rx_sequence_(0),
      crc_errors_(0),
      malformed_packets_(0),
      sequence_errors_(0),
      identity_errors_(0),
      capability_errors_(0),
      session_errors_(0),
      wrong_peer_packets_(0),
      tx_errors_(0),
      publisher_count_(-1),
      legacy_topic_("/vehicle_cmd_legacy"),
      velocity_topic_("/vehicle_velocity"),
      can_topic_("/can_info"),
      mode_topic_("/driving_mode_viz"),
      output_topic_("/vehicle_cmd"),
      publisher_identities_("UNKNOWN"),
      driver_health_mode_("inferred_from_state_freshness"),
      steering_feedback_unit_("UNCONFIRMED"),
      vehicle_velocity_type_("UNSET") {
  diagnostic_pub_ = nh_.advertise<diagnostic_msgs::DiagnosticArray>(
      "/diagnostics", 10);
  publish_diagnostics(monotonic_ms(), "INIT", "initializing");

  pnh_.param<std::string>("topics/legacy_input", legacy_topic_, legacy_topic_);
  pnh_.param<std::string>("topics/vehicle_velocity", velocity_topic_,
                          velocity_topic_);
  pnh_.param<std::string>("topics/can_info", can_topic_, can_topic_);
  pnh_.param<std::string>("topics/driving_mode_viz", mode_topic_, mode_topic_);
  pnh_.param<std::string>("topics/vehicle_cmd_output", output_topic_,
                          output_topic_);
  if (!load_config()) {
    publish_diagnostics(monotonic_ms(), "CONFIG_ERROR", detail_);
    ROS_FATAL_STREAM("production gateway config invalid: " << detail_);
    ros::shutdown();
    return;
  }

  final_pub_ = nh_.advertise<autoware_msgs::VehicleCmd>(output_topic_, 1);
  legacy_sub_ = nh_.subscribe(legacy_topic_, 1, &GatewayNode::legacy_cb, this);
  if (vehicle_velocity_type_ == "TwistStamped") {
    velocity_sub_ = nh_.subscribe(velocity_topic_, 1,
                                  &GatewayNode::velocity_cb, this);
  } else {
    velocity_sub_ = nh_.subscribe(velocity_topic_, 1,
                                  &GatewayNode::velocity_twist_cb, this);
  }
  can_sub_ = nh_.subscribe(can_topic_, 1, &GatewayNode::can_cb, this);
  mode_sub_ = nh_.subscribe(mode_topic_, 1, &GatewayNode::mode_cb, this);
  if (config_.driver_health_mode == cnvg::DriverHealthMode::EXPLICIT_TOPIC) {
    pnh_.param<std::string>("driver_health_topic", driver_topic_, std::string());
    if (driver_topic_.empty() || driver_topic_ == "UNSET") {
      throw std::runtime_error(
          "explicit driver health requires driver_health_topic");
    }
    driver_sub_ = nh_.subscribe(driver_topic_, 1, &GatewayNode::driver_cb, this);
    have_driver_topic_ = true;
  }

  owner_service_ = pnh_.advertiseService(
      "request_owner", &GatewayNode::request_owner, this);
  release_service_ = pnh_.advertiseService(
      "release_owner", &GatewayNode::release_owner, this);

  std::string error;
  if (!udp_.open(config_.local_ip,
                 static_cast<std::uint16_t>(config_.local_port), &error)) {
    throw std::runtime_error("UDP bind failed: " + error);
  }
  send_hello(monotonic_ms());
  timer_ = nh_.createTimer(ros::Duration(0.02), &GatewayNode::timer_cb, this);
  valid_config_ = true;
}

bool GatewayNode::load_config() {
  pnh_.param<std::string>("network/local_ip", config_.local_ip,
                          std::string("UNSET"));
  pnh_.param<std::string>("network/peer_ip", config_.peer_ip,
                          std::string("UNSET"));
  pnh_.param<std::string>("owner_id", config_.owner_id,
                          std::string("UNSET"));
  pnh_.param<std::string>("expected_peer_owner_id",
                          config_.expected_peer_owner_id,
                          std::string("UNSET"));
  read_port(pnh_, "network/local_port", &config_.local_port);
  read_port(pnh_, "network/peer_port", &config_.peer_port);

  int capabilities = 0;
  pnh_.param("network/required_capabilities", capabilities, 0);
  if (capabilities >= 0 && capabilities <= 65535) {
    config_.required_capabilities =
        static_cast<std::uint16_t>(capabilities);
  } else {
    config_.required_capabilities = 0;
  }

  std::string expected_role("UNSET");
  pnh_.param<std::string>("network/expected_peer_role", expected_role,
                          expected_role);
  if (expected_role == "J6M_GATEWAY") {
    config_.expected_peer_role = cnvg::PeerRole::J6M_GATEWAY;
  } else if (expected_role == "AUTOWARE_PC") {
    config_.expected_peer_role = cnvg::PeerRole::AUTOWARE_PC;
  } else {
    detail_ = "network.expected_peer_role must be J6M_GATEWAY or AUTOWARE_PC";
    return false;
  }

  config_.steering_configured =
      read_number(pnh_, "vehicle/steering_sign", &config_.steering_sign) &&
      read_number(pnh_, "vehicle/steering_ratio", &config_.steering_ratio) &&
      read_number(pnh_, "vehicle/steering_limit_rad",
                  &config_.steering_limit_rad);

  int legacy_timeout = 0;
  int j6m_timeout = 0;
  int state_timeout = 0;
  int transition_dwell = 0;
  int driver_timeout = 0;
  pnh_.param("safety/legacy_command_timeout_ms", legacy_timeout, 0);
  pnh_.param("safety/j6m_command_timeout_ms", j6m_timeout, 0);
  pnh_.param("safety/state_timeout_ms", state_timeout, 0);
  pnh_.param("safety/transition_dwell_ms", transition_dwell, 0);
  pnh_.param("safety/driver_health_timeout_ms", driver_timeout, 0);
  config_.legacy_command_timeout_ms = legacy_timeout > 0 ? legacy_timeout : 0;
  config_.j6m_command_timeout_ms = j6m_timeout > 0 ? j6m_timeout : 0;
  config_.state_timeout_ms = state_timeout > 0 ? state_timeout : 0;
  config_.transition_dwell_ms = transition_dwell > 0 ? transition_dwell : 0;
  config_.driver_health_timeout_ms = driver_timeout > 0 ? driver_timeout : 0;

  pnh_.param<std::string>("driver_health_mode", driver_health_mode_,
                          driver_health_mode_);
  pnh_.param<std::string>("driver_health_topic", config_.driver_health_topic,
                          std::string("UNSET"));
  if (driver_health_mode_ == "explicit_topic") {
    config_.driver_health_mode = cnvg::DriverHealthMode::EXPLICIT_TOPIC;
  } else if (driver_health_mode_ == "inferred_from_state_freshness") {
    config_.driver_health_mode =
        cnvg::DriverHealthMode::INFERRED_FROM_STATE_FRESHNESS;
  } else if (driver_health_mode_ == "disabled_for_offline_test") {
    config_.driver_health_mode =
        cnvg::DriverHealthMode::DISABLED_FOR_OFFLINE_TEST;
  } else {
    detail_ = "driver_health_mode is not a supported value";
    return false;
  }

  pnh_.param<std::string>("state/steering_feedback_unit",
                          steering_feedback_unit_, steering_feedback_unit_);
  pnh_.param<std::string>("state/vehicle_velocity_type",
                          vehicle_velocity_type_, vehicle_velocity_type_);
  if (vehicle_velocity_type_ != "TwistStamped" &&
      vehicle_velocity_type_ != "Twist") {
    detail_ = "state.vehicle_velocity_type must be Twist or TwistStamped";
    return false;
  }
  if (steering_feedback_unit_ != "UNCONFIRMED" &&
      steering_feedback_unit_ != "DEGREES" &&
      steering_feedback_unit_ != "RADIANS") {
    detail_ = "state.steering_feedback_unit must be UNCONFIRMED, DEGREES, or RADIANS";
    return false;
  }
  state_mapper_ = StateMapper(steering_feedback_unit_);

  const char* gear_names[] = {"park", "reverse", "neutral", "drive", "low"};
  const cnvg::Gear gears[] = {cnvg::Gear::PARK, cnvg::Gear::REVERSE,
                              cnvg::Gear::NEUTRAL, cnvg::Gear::DRIVE,
                              cnvg::Gear::LOW};
  for (std::size_t i = 0; i < 5; ++i) {
    int gear_value = 0;
    if (pnh_.getParam(std::string("gear_map/") + gear_names[i], gear_value)) {
      mapping_.gear_map[gears[i]] = gear_value;
      config_.gear_map[gears[i]] = gear_value;
    }
  }

  peer_policy_.expected_ip = config_.peer_ip;
  peer_policy_.expected_port =
      static_cast<std::uint16_t>(config_.peer_port);
  peer_policy_.expected_owner_id = config_.expected_peer_owner_id;
  peer_policy_.expected_role = config_.expected_peer_role;
  peer_policy_.required_capabilities = config_.required_capabilities;
  mapping_.steering_configured = config_.steering_configured;
  mapping_.steering_sign = config_.steering_sign;
  mapping_.steering_ratio = config_.steering_ratio;
  mapping_.steering_limit_rad = config_.steering_limit_rad;

  const std::vector<std::string> errors =
      cnvg::validate_production_config(config_);
  if (!errors.empty()) {
    std::ostringstream detail;
    for (std::size_t i = 0; i < errors.size(); ++i) {
      if (i != 0) detail << "; ";
      detail << errors[i];
    }
    detail_ = detail.str();
    return false;
  }
  session_.reset(new cnvg::SessionManager(peer_policy_));
  return true;
}

bool GatewayNode::driver_health_alive(std::uint64_t now_ms) const {
  if (config_.driver_health_mode == cnvg::DriverHealthMode::EXPLICIT_TOPIC) {
    return driver_value_ && cnvg::monotonic_fresh(
        now_ms, driver_rx_ms_, config_.driver_health_timeout_ms);
  }
  if (config_.driver_health_mode ==
      cnvg::DriverHealthMode::INFERRED_FROM_STATE_FRESHNESS) {
    return state_mapper_.fresh(now_ms, config_.driver_health_timeout_ms);
  }
  return false;
}

void GatewayNode::legacy_cb(
    const autoware_msgs::VehicleCmd::ConstPtr& message) {
  legacy_command_ = *message;
  legacy_rx_ms_ = monotonic_ms();
  have_legacy_ = true;
}

void GatewayNode::velocity_cb(
    const geometry_msgs::TwistStamped::ConstPtr& message) {
  state_mapper_.velocity(message);
}

void GatewayNode::velocity_twist_cb(
    const geometry_msgs::Twist::ConstPtr& message) {
  state_mapper_.velocity(message);
}

void GatewayNode::can_cb(
    const autoware_can_msgs::CANInfo::ConstPtr& message) {
  state_mapper_.can(message);
}

void GatewayNode::mode_cb(const std_msgs::String::ConstPtr& message) {
  state_mapper_.driving_mode(message);
}

void GatewayNode::driver_cb(const std_msgs::Bool::ConstPtr& message) {
  driver_value_ = message->data;
  driver_rx_ms_ = monotonic_ms();
}

bool GatewayNode::request_owner(std_srvs::SetBool::Request& request,
                                std_srvs::SetBool::Response& response) {
  if (!valid_config_ || publisher_conflict_) {
    response.success = false;
    response.message =
        "gateway inactive: config error or multiple /vehicle_cmd publishers";
    return true;
  }
  arbiter_.request_owner(request.data ? cnvg::Owner::J6M
                                      : cnvg::Owner::LEGACY_AUTOWARE);
  response.success = true;
  response.message = request.data ? "explicit J6M owner request"
                                  : "explicit legacy owner request";
  return true;
}

bool GatewayNode::release_owner(std_srvs::Trigger::Request&,
                                std_srvs::Trigger::Response& response) {
  arbiter_.clear_request();
  response.success = arbiter_.owner() == cnvg::Owner::NONE &&
      arbiter_.state() != cnvg::ArbiterState::ESTOP_LOCKED &&
      arbiter_.state() != cnvg::ArbiterState::FAULT_LOCKED;
  response.message = response.success ? "owner released to NONE"
                                      : "owner remains latched by E-stop/fault";
  return true;
}

bool GatewayNode::other_vehicle_cmd_publishers() {
  XmlRpc::XmlRpcValue request;
  XmlRpc::XmlRpcValue response;
  request.setSize(1);
  request[0] = ros::this_node::getName();
  std::string payload;
  publisher_count_ = -1;
  publisher_identities_ = "UNKNOWN";
  if (!ros::master::execute("getSystemState", request, response, payload,
                            false) ||
      response.getType() != XmlRpc::XmlRpcValue::TypeArray ||
      response.size() < 3 || static_cast<int>(response[0]) != 1) {
    return true;
  }

  XmlRpc::XmlRpcValue publishers = response[2][0];
  for (int i = 0; i < publishers.size(); ++i) {
    if (static_cast<std::string>(publishers[i][0]) != output_topic_) continue;
    XmlRpc::XmlRpcValue nodes = publishers[i][1];
    publisher_count_ = nodes.size();
    std::ostringstream identities;
    for (int j = 0; j < nodes.size(); ++j) {
      if (j != 0) identities << ",";
      identities << static_cast<std::string>(nodes[j]);
    }
    publisher_identities_ = identities.str();
    return publisher_count_ != 1 ||
           publisher_identities_.find(ros::this_node::getName()) ==
               std::string::npos;
  }
  return true;  // The ROS master did not confirm exactly one gateway writer.
}

void GatewayNode::send_hello(std::uint64_t now_ms) {
  cnvg::Message hello;
  hello.session_id = local_session_id_;
  hello.owner_id = config_.owner_id;
  hello.role = cnvg::PeerRole::AUTOWARE_PC;
  const std::vector<std::uint8_t> wire = cnvg::encode(
      cnvg::MessageType::HELLO, tx_sequence_++, cnvg::unix_time_ms(), hello);
  std::string error;
  if (!udp_.send_to(wire.data(), wire.size(), config_.peer_ip,
                    static_cast<std::uint16_t>(config_.peer_port), &error)) {
    ++tx_errors_;
  }
  last_hello_tx_ms_ = now_ms;
}

void GatewayNode::receive_udp(std::uint64_t now_ms) {
  for (;;) {
    cnvg::Datagram datagram;
    bool source_valid = false;
    std::string error;
    if (!udp_.receive(&datagram, 0, config_.peer_ip,
                      static_cast<std::uint16_t>(config_.peer_port),
                      &source_valid, &error)) {
      break;
    }
    if (!source_valid) {
      ++wrong_peer_packets_;
      continue;
    }

    cnvg::Packet packet;
    try {
      packet = cnvg::decode(datagram.bytes.data(), datagram.size);
    } catch (const std::exception& exception) {
      const std::string reason(exception.what());
      if (reason.find("CRC") != std::string::npos) {
        ++crc_errors_;
      } else {
        ++malformed_packets_;
      }
      continue;
    }

    const cnvg::SessionResult result = session_->accept(
        datagram.bytes.data(), datagram.size, datagram.source_ip,
        datagram.source_port, now_ms);
    if (result == cnvg::SessionResult::WRONG_SOURCE) {
      ++wrong_peer_packets_;
      continue;
    }
    if (result == cnvg::SessionResult::BAD_PACKET) {
      ++malformed_packets_;
      continue;
    }
    if (result == cnvg::SessionResult::BAD_SEQUENCE) {
      ++sequence_errors_;
      continue;
    }
    if (result == cnvg::SessionResult::WRONG_IDENTITY) {
      ++identity_errors_;
      continue;
    }
    if (result == cnvg::SessionResult::INCOMPATIBLE) {
      ++capability_errors_;
      continue;
    }
    if (result == cnvg::SessionResult::WRONG_SESSION) {
      ++session_errors_;
      continue;
    }
    if (result == cnvg::SessionResult::SESSION_CHANGED) {
      have_j6m_command_ = false;
      command_rx_ms_ = 0;
      heartbeat_rx_ms_ = 0;
    }

    rx_sequence_ = packet.sequence;
    if (packet.type == cnvg::MessageType::HEARTBEAT) {
      heartbeat_rx_ms_ = now_ms;
    } else if (packet.type == cnvg::MessageType::CONTROL_COMMAND) {
      j6m_command_ = packet.message;
      command_rx_ms_ = now_ms;
      have_j6m_command_ = true;
      if (packet.message.emergency_stop) software_estop_latched_ = true;
    }
  }
}

void GatewayNode::send_state(std::uint64_t now_ms) {
  cnvg::Message state;
  state.session_id = local_session_id_;
  state.owner_id = config_.owner_id;
  state.emergency = software_estop_latched_;
  state.gateway_alive = true;
  state.fault_code = cnvg::FAULT_CODE_UNKNOWN;
  const bool driver_alive = driver_health_alive(now_ms);
  bool steering_unit_confirmed = false;
  const bool mapped = state_mapper_.map(
      now_ms, driver_alive, &state, &steering_unit_confirmed);
  const bool state_fresh = state_mapper_.fresh(now_ms, config_.state_timeout_ms);
  if (!mapped || !state_fresh) {
    state.vehicle_mode = cnvg::VehicleMode::UNKNOWN;
    state.driver_alive = false;
  }
  if (!steering_unit_confirmed) state.steering_rad = 0.0f;

  const std::vector<std::uint8_t> wire = cnvg::encode(
      cnvg::MessageType::VEHICLE_STATE, tx_sequence_++, cnvg::unix_time_ms(), state);
  std::string error;
  if (!udp_.send_to(wire.data(), wire.size(), config_.peer_ip,
                    static_cast<std::uint16_t>(config_.peer_port), &error)) {
    ++tx_errors_;
  }
}

void GatewayNode::timer_cb(const ros::TimerEvent&) {
  if (!valid_config_) return;
  const std::uint64_t now_ms = monotonic_ms();
  if (now_ms - last_hello_tx_ms_ >= 500) send_hello(now_ms);

  publisher_conflict_ = other_vehicle_cmd_publishers();
  receive_udp(now_ms);
  send_state(now_ms);

  const bool state_fresh = state_mapper_.fresh(
      now_ms, config_.state_timeout_ms);
  const bool driver_alive = driver_health_alive(now_ms);
  const bool legacy_fresh = have_legacy_ && cnvg::monotonic_fresh(
      now_ms, legacy_rx_ms_, config_.legacy_command_timeout_ms);
  const std::uint32_t command_timeout_ms = cnvg::effective_command_timeout_ms(
      j6m_command_.validity_ms, config_.j6m_command_timeout_ms);
  const bool command_fresh = have_j6m_command_ && command_timeout_ms > 0 &&
      cnvg::monotonic_fresh(now_ms, command_rx_ms_, command_timeout_ms);
  const bool peer_alive = session_->active() && cnvg::monotonic_fresh(
      now_ms, heartbeat_rx_ms_, config_.j6m_command_timeout_ms);

  cnvg::VehicleCommand mapped_command;
  std::string mapping_error;
  const bool mapping_valid = command_fresh && cnvg::map_vehicle_command(
      j6m_command_, mapping_, last_output_.gear_cmd.gear,
      &mapped_command, &mapping_error);

  cnvg::ArbiterInputs inputs;
  inputs.legacy_command_fresh = legacy_fresh;
  inputs.j6m_session_alive = peer_alive;
  inputs.j6m_command_fresh = command_fresh && mapping_valid;
  inputs.j6m_enable = have_j6m_command_ && j6m_command_.enable;
  inputs.vehicle_mode = state_fresh && driver_alive
      ? state_mapper_.vehicle_mode() : cnvg::VehicleMode::UNKNOWN;
  inputs.vehicle_fault = inputs.vehicle_mode == cnvg::VehicleMode::FAULT;
  inputs.estop = software_estop_latched_;
  inputs.multiple_publishers = publisher_conflict_;
  inputs.safe_zero_confirmed = output_safe_zero_;
  inputs.monotonic_ms = now_ms;
  inputs.transition_dwell_ms = config_.transition_dwell_ms;
  const cnvg::ArbiterOutput selected = arbiter_.tick(inputs);

  autoware_msgs::VehicleCmd output;
  if (selected.enabled && selected.owner == cnvg::Owner::LEGACY_AUTOWARE) {
    output = legacy_command_;
  } else if (selected.enabled && selected.owner == cnvg::Owner::J6M) {
    if (!map_j6m_command(j6m_command_, mapping_, last_output_, &output,
                         &mapping_error)) {
      output = safe_zero_command(last_output_.gear_cmd.gear);
    }
  } else {
    output = safe_zero_command(last_output_.gear_cmd.gear);
  }

  if (!publisher_conflict_) {
    final_pub_.publish(output);
    last_output_ = output;
    output_safe_zero_ = !selected.enabled;
  } else {
    output_safe_zero_ = false;
  }

  std::string status;
  if (publisher_conflict_) {
    status = "MULTIPLE_VEHICLE_CMD_PUBLISHERS";
  } else if (software_estop_latched_) {
    status = "ESTOP";
  } else if (arbiter_.state() == cnvg::ArbiterState::FAULT_LOCKED) {
    status = "FAULT";
  } else if (selected.transitioning) {
    status = "TRANSITION";
  } else if (selected.owner == cnvg::Owner::J6M) {
    status = "ACTIVE_J6M";
  } else if (selected.owner == cnvg::Owner::LEGACY_AUTOWARE) {
    status = "ACTIVE_LEGACY";
  } else if (command_fresh && !mapping_valid) {
    status = "CONFIG_ERROR";
  } else if (!session_->active()) {
    status = "WAITING_FOR_PEER";
  } else if (!state_fresh || !driver_alive) {
    status = "WAITING_FOR_VEHICLE_STATE";
  } else if (!legacy_fresh && !command_fresh) {
    status = "STALE";
  } else {
    status = "WAITING_FOR_OPERATOR";
  }
  publish_diagnostics(now_ms, status, mapping_error);
}

void GatewayNode::publish_diagnostics(std::uint64_t now_ms,
                                      const std::string& state,
                                      const std::string& detail) {
  diagnostic_msgs::DiagnosticArray array;
  array.header.stamp = ros::Time::now();
  diagnostic_msgs::DiagnosticStatus status;
  status.name = "j6m_vehicle_gateway";
  status.hardware_id = "legacy-autoware";
  status.message = detail.empty() ? state : detail;
  if (state == "ACTIVE_J6M" || state == "ACTIVE_LEGACY" ||
      state == "WAITING_FOR_PEER" || state == "WAITING_FOR_VEHICLE_STATE" ||
      state == "WAITING_FOR_OPERATOR") {
    status.level = diagnostic_msgs::DiagnosticStatus::OK;
  } else if (state == "INIT" || state == "TRANSITION" || state == "STALE") {
    status.level = diagnostic_msgs::DiagnosticStatus::WARN;
  } else {
    status.level = diagnostic_msgs::DiagnosticStatus::ERROR;
  }

  const std::string owner = arbiter_.owner() == cnvg::Owner::J6M
      ? "J6M" : arbiter_.owner() == cnvg::Owner::LEGACY_AUTOWARE
          ? "LEGACY" : "NONE";
  const std::uint64_t raw_state_age = state_mapper_.age_ms(now_ms);
  const std::string state_age = raw_state_age == UINT64_MAX
      ? "STALE" : std::to_string(raw_state_age);
  const std::string keys[] = {
      "status", "owner", "peer_ip", "peer_port", "peer_role", "session",
      "rx_sequence", "command_age_ms", "state_age_ms",
      "legacy_command_age_ms", "crc_errors", "malformed_packets",
      "sequence_errors", "identity_errors", "capability_errors",
      "session_errors", "wrong_peer_packets", "tx_errors", "config_valid",
      "software_estop", "physical_estop", "steering_feedback_unit",
      "steering_closed_loop_validated", "driver_health_source",
      "vehicle_cmd_publisher_count", "vehicle_cmd_publisher_identities"};
  const std::string values[] = {
      state, owner, config_.peer_ip, std::to_string(config_.peer_port),
      config_.expected_peer_role == cnvg::PeerRole::J6M_GATEWAY
          ? "J6M_GATEWAY" : "AUTOWARE_PC",
      session_ ? std::to_string(session_->session_id()) : "0",
      std::to_string(rx_sequence_),
      have_j6m_command_ ? std::to_string(cnvg::monotonic_age_ms(
          now_ms, command_rx_ms_)) : "STALE",
      state_age,
      have_legacy_ ? std::to_string(cnvg::monotonic_age_ms(
          now_ms, legacy_rx_ms_)) : "STALE",
      std::to_string(crc_errors_), std::to_string(malformed_packets_),
      std::to_string(sequence_errors_), std::to_string(identity_errors_),
      std::to_string(capability_errors_), std::to_string(session_errors_),
      std::to_string(wrong_peer_packets_), std::to_string(tx_errors_),
      valid_config_ ? "true" : "false",
      software_estop_latched_ ? "SOFTWARE_ESTOP_LATCHED" : "clear",
      "UNKNOWN", steering_feedback_unit_, "false",
      have_driver_topic_ ? "EXPLICIT" : "INFERRED",
      std::to_string(publisher_count_), publisher_identities_};
  for (std::size_t i = 0; i < sizeof(keys) / sizeof(keys[0]); ++i) {
    diagnostic_msgs::KeyValue value;
    value.key = keys[i];
    value.value = values[i];
    status.values.push_back(value);
  }
  array.status.push_back(status);
  diagnostic_pub_.publish(array);
}

}  // namespace j6m_vehicle_gateway_ros1
