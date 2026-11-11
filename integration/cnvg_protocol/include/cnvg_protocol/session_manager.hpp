#ifndef CNVG_PROTOCOL_SESSION_MANAGER_HPP_
#define CNVG_PROTOCOL_SESSION_MANAGER_HPP_
#include "cnvg_protocol/protocol.hpp"
#include <cstdint>
#include <set>
#include <string>
#include <map>
namespace cnvg {
enum class SessionResult { ACCEPTED, SESSION_CHANGED, WRONG_SOURCE, INCOMPATIBLE, WRONG_IDENTITY, WRONG_SESSION, BAD_PACKET, BAD_SEQUENCE };
struct PeerPolicy { std::string expected_ip, expected_owner_id; std::uint16_t expected_port=0, required_capabilities=REQUIRED_CAPABILITIES; PeerRole expected_role=PeerRole::AUTOWARE_PC; };
class SessionManager {
 public:
  explicit SessionManager(const PeerPolicy& policy);
  SessionResult accept(const std::uint8_t* data, std::size_t size, const std::string& source_ip, std::uint16_t source_port, std::uint64_t local_monotonic_ms);
  bool active() const { return active_; }
  std::uint64_t session_id() const { return session_id_; }
  std::uint64_t last_arrival_ms() const { return last_arrival_ms_; }
  std::uint32_t last_sequence(MessageType type) const;
  std::uint64_t wrong_peer_count() const { return wrong_peer_count_; }
 private:
  PeerPolicy policy_; bool active_; std::uint64_t session_id_, last_arrival_ms_, wrong_peer_count_;
  std::set<std::uint64_t> retired_; std::map<MessageType, SequenceWindow> windows_;
};
}  // namespace cnvg
#endif
