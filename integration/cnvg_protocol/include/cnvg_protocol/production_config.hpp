#ifndef CNVG_PROTOCOL_PRODUCTION_CONFIG_HPP_
#define CNVG_PROTOCOL_PRODUCTION_CONFIG_HPP_
#include "cnvg_protocol/protocol.hpp"
#include <cstdint>
#include <map>
#include <string>
#include <vector>
namespace cnvg {
enum class DriverHealthMode { EXPLICIT_TOPIC, INFERRED_FROM_STATE_FRESHNESS, DISABLED_FOR_OFFLINE_TEST };
struct ProductionConfig {
  std::string local_ip, peer_ip, owner_id, expected_peer_owner_id, driver_health_topic;
  std::uint32_t local_port = 0, peer_port = 0;
  PeerRole expected_peer_role = PeerRole::AUTOWARE_PC;
  std::uint16_t required_capabilities = REQUIRED_CAPABILITIES;
  bool steering_configured = false;
  double steering_sign = 0.0, steering_ratio = 0.0, steering_limit_rad = 0.0;
  std::map<Gear, std::int32_t> gear_map;
  std::uint32_t legacy_command_timeout_ms = 0, j6m_command_timeout_ms = 0;
  std::uint32_t state_timeout_ms = 0, transition_dwell_ms = 0;
  DriverHealthMode driver_health_mode = DriverHealthMode::INFERRED_FROM_STATE_FRESHNESS;
  std::uint32_t driver_health_timeout_ms = 0;
};
std::vector<std::string> validate_production_config(const ProductionConfig& config);
bool valid_ipv4(const std::string& ip);
bool valid_owner_id(const std::string& owner_id);
}  // namespace cnvg
#endif
