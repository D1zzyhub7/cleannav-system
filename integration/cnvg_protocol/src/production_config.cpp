#include "cnvg_protocol/production_config.hpp"

#include <arpa/inet.h>
#include <cmath>

namespace cnvg {

bool valid_ipv4(const std::string& ip) {
  in_addr address;
  return !ip.empty() && ip != "UNSET" &&
         inet_pton(AF_INET, ip.c_str(), &address) == 1;
}

bool valid_owner_id(const std::string& owner_id) {
  if (owner_id.empty() || owner_id == "UNSET" || owner_id.size() > 16) {
    return false;
  }
  for (std::string::const_iterator it = owner_id.begin();
       it != owner_id.end(); ++it) {
    if (*it < 0x21 || *it > 0x7e) return false;
  }
  return true;
}

std::vector<std::string> validate_production_config(
    const ProductionConfig& config) {
  std::vector<std::string> errors;
  if (!valid_ipv4(config.local_ip) || config.local_ip == "0.0.0.0") {
    errors.push_back("network.local_ip must be an explicit, non-wildcard IPv4 address");
  }
  if (!valid_ipv4(config.peer_ip) || config.peer_ip == "0.0.0.0") {
    errors.push_back("network.peer_ip must be an explicit, non-wildcard IPv4 address");
  }
  if (config.local_port == 0 || config.local_port > 65535) {
    errors.push_back("network.local_port must be 1..65535");
  }
  if (config.peer_port == 0 || config.peer_port > 65535) {
    errors.push_back("network.peer_port must be 1..65535");
  }
  if (config.local_ip == config.peer_ip &&
      config.local_port == config.peer_port) {
    errors.push_back("local and peer endpoints must differ");
  }
  const std::uint32_t forbidden_ports[] = {4500, 4501, 6667};
  for (std::size_t i = 0; i < 3; ++i) {
    if (config.local_port == forbidden_ports[i] ||
        config.peer_port == forbidden_ports[i]) {
      errors.push_back("reserved IVCU UDP port is forbidden");
    }
  }
  if (!valid_owner_id(config.owner_id) ||
      !valid_owner_id(config.expected_peer_owner_id)) {
    errors.push_back("owner IDs must be 1..16 printable ASCII bytes");
  }
  if (!capabilities_compatible(config.required_capabilities) ||
      config.required_capabilities != REQUIRED_CAPABILITIES) {
    errors.push_back("required capability mask must match supported V1.1 capabilities");
  }
  if (!config.steering_configured ||
      !std::isfinite(config.steering_sign) ||
      std::abs(config.steering_sign) != 1.0 ||
      !std::isfinite(config.steering_ratio) ||
      config.steering_ratio <= 0.0 ||
      !std::isfinite(config.steering_limit_rad) ||
      config.steering_limit_rad <= 0.0) {
    errors.push_back("steering sign, ratio, and limit must be explicitly configured");
  }
  if (config.legacy_command_timeout_ms == 0) {
    errors.push_back("legacy command timeout must be positive");
  }
  if (config.j6m_command_timeout_ms == 0) {
    errors.push_back("J6M command timeout must be positive");
  }
  if (config.state_timeout_ms == 0) {
    errors.push_back("state timeout must be positive");
  }
  if (config.transition_dwell_ms == 0) {
    errors.push_back("transition dwell must be positive");
  }
  if (config.driver_health_timeout_ms == 0) {
    errors.push_back("driver health timeout must be positive");
  }
  if (config.driver_health_mode == DriverHealthMode::DISABLED_FOR_OFFLINE_TEST) {
    errors.push_back("disabled driver health is offline-test only");
  }
  if (config.driver_health_mode == DriverHealthMode::EXPLICIT_TOPIC &&
      (config.driver_health_topic.empty() ||
       config.driver_health_topic == "UNSET")) {
    errors.push_back("explicit driver health requires a configured topic");
  }
  const std::uint8_t role = static_cast<std::uint8_t>(config.expected_peer_role);
  if (role != static_cast<std::uint8_t>(PeerRole::AUTOWARE_PC) &&
      role != static_cast<std::uint8_t>(PeerRole::J6M_GATEWAY)) {
    errors.push_back("expected peer role is invalid");
  }
  for (std::map<Gear, std::int32_t>::const_iterator it =
           config.gear_map.begin(); it != config.gear_map.end(); ++it) {
    if (it->second < 0 || it->second > 255) {
      errors.push_back("configured gear values must be 0..255");
    }
  }
  return errors;
}

}  // namespace cnvg
