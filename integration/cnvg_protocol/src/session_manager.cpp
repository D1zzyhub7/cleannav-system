#include "cnvg_protocol/session_manager.hpp"

namespace cnvg {

SessionManager::SessionManager(const PeerPolicy& policy)
    : policy_(policy),
      active_(false),
      session_id_(0),
      last_arrival_ms_(0),
      wrong_peer_count_(0) {}

SessionResult SessionManager::accept(const std::uint8_t* data,
                                     std::size_t size,
                                     const std::string& source_ip,
                                     std::uint16_t source_port,
                                     std::uint64_t local_monotonic_ms) {
  if (source_ip != policy_.expected_ip ||
      source_port != policy_.expected_port) {
    ++wrong_peer_count_;
    return SessionResult::WRONG_SOURCE;
  }

  Packet packet;
  try {
    packet = decode(data, size);
  } catch (...) {
    return SessionResult::BAD_PACKET;
  }

  if (packet.type == MessageType::HELLO) {
    if (packet.message.role != policy_.expected_role ||
        packet.message.owner_id != policy_.expected_owner_id) {
      return SessionResult::WRONG_IDENTITY;
    }
    if (!capabilities_compatible(packet.message.capabilities) ||
        packet.message.capabilities != policy_.required_capabilities) {
      return SessionResult::INCOMPATIBLE;
    }
    if (active_ && packet.message.session_id == session_id_) {
      last_arrival_ms_ = local_monotonic_ms;
      return SessionResult::ACCEPTED;
    }
    if (retired_.count(packet.message.session_id) != 0) {
      return SessionResult::WRONG_SESSION;
    }
    if (active_) retired_.insert(session_id_);
    active_ = true;
    session_id_ = packet.message.session_id;
    windows_.clear();
    last_arrival_ms_ = local_monotonic_ms;
    return SessionResult::SESSION_CHANGED;
  }

  if (!active_) return SessionResult::WRONG_SESSION;
  if (packet.message.session_id != session_id_) {
    return SessionResult::WRONG_SESSION;
  }
  if (packet.type != MessageType::GATEWAY_STATUS &&
      packet.message.owner_id != policy_.expected_owner_id) {
    return SessionResult::WRONG_IDENTITY;
  }
  if (windows_[packet.type].accept(packet.sequence) !=
      SequenceDisposition::ACCEPT) {
    return SessionResult::BAD_SEQUENCE;
  }
  last_arrival_ms_ = local_monotonic_ms;
  return SessionResult::ACCEPTED;
}

std::uint32_t SessionManager::last_sequence(MessageType type) const {
  const std::map<MessageType, SequenceWindow>::const_iterator it =
      windows_.find(type);
  return it == windows_.end() ? 0 : it->second.last_sequence();
}

}  // namespace cnvg
