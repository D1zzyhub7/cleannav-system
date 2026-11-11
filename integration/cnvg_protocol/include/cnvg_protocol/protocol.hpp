#ifndef CNVG_PROTOCOL_PROTOCOL_HPP_
#define CNVG_PROTOCOL_PROTOCOL_HPP_

#include <array>
#include <cstddef>
#include <cstdint>
#include <string>
#include <stdexcept>
#include <vector>

namespace cnvg {

enum class MessageType : std::uint8_t {
  HELLO = 1, HEARTBEAT = 2, CONTROL_COMMAND = 3,
  VEHICLE_STATE = 4, GATEWAY_STATUS = 5
};
enum class PeerRole : std::uint8_t { J6M_GATEWAY = 1, AUTOWARE_PC = 2 };
enum class ControlMode : std::uint8_t { TWIST_RAW = 0, ACKERMANN = 1 };
enum class Gear : std::int8_t {
  UNSPECIFIED = 0, PARK = 1, REVERSE = 2, NEUTRAL = 3, DRIVE = 4, LOW = 5
};
enum class VehicleMode : std::uint8_t {
  UNKNOWN = 0, MANUAL = 1, AUTONOMOUS = 2, ESTOP = 3, FAULT = 4
};
static const std::uint32_t FAULT_CODE_UNKNOWN = 0xffffffffu;
enum class GatewayState : std::uint8_t {
  DISCONNECTED = 0, WAITING = 1, ACTIVE = 2, STALE = 3, FAULT = 4, ESTOP = 5
};

enum class SequenceDisposition { ACCEPT, DUPLICATE, OUT_OF_ORDER };
static const std::uint16_t CAP_RX_MONOTONIC_VALIDITY = 1u << 0;
static const std::uint16_t CAP_EXPLICIT_OWNER_ARBITRATION = 1u << 1;
static const std::uint16_t CAP_V11_SEMANTICS = 1u << 2;
static const std::uint16_t REQUIRED_CAPABILITIES =
    CAP_RX_MONOTONIC_VALIDITY | CAP_EXPLICIT_OWNER_ARBITRATION | CAP_V11_SEMANTICS;
static const std::uint16_t SUPPORTED_CAPABILITIES = REQUIRED_CAPABILITIES;
inline bool capabilities_compatible(std::uint16_t capabilities) {
  return (capabilities & REQUIRED_CAPABILITIES) == REQUIRED_CAPABILITIES &&
         (capabilities & static_cast<std::uint16_t>(~SUPPORTED_CAPABILITIES)) == 0;
}

struct Message {
  std::uint64_t session_id = 0;
  std::uint16_t capabilities = REQUIRED_CAPABILITIES;
  std::string owner_id;
  PeerRole role = PeerRole::J6M_GATEWAY;
  bool enable = false;
  bool emergency_stop = false;
  ControlMode control_mode = ControlMode::TWIST_RAW;
  Gear gear = Gear::UNSPECIFIED;
  std::uint16_t validity_ms = 0;
  float target_speed_mps = 0.0f;
  float target_yaw_rate_rps = 0.0f;
  float target_steering_rad = 0.0f;
  float speed_mps = 0.0f;
  float steering_rad = 0.0f;
  VehicleMode vehicle_mode = VehicleMode::UNKNOWN;
  bool emergency = false;
  bool gateway_alive = false;
  bool driver_alive = false;
  std::uint32_t fault_code = 0;
  GatewayState gateway_state = GatewayState::DISCONNECTED;
  std::array<std::uint32_t, 8> counters{};
};

struct Packet {
  MessageType type = MessageType::HELLO;
  std::uint32_t sequence = 0;
  std::uint64_t timestamp_ms = 0;
  std::uint16_t flags = 0;
  Message message;
};

class ProtocolError : public std::runtime_error {
 public:
  explicit ProtocolError(const std::string& what) : std::runtime_error(what) {}
};

std::vector<std::uint8_t> encode(MessageType type, std::uint32_t sequence,
                                 std::uint64_t timestamp_ms,
                                 const Message& message);
Packet decode(const std::uint8_t* data, std::size_t size);
inline Packet decode(const std::vector<std::uint8_t>& data) {
  return decode(data.data(), data.size());
}
std::uint32_t crc32(const std::uint8_t* data, std::size_t size);
std::uint64_t unix_time_ms();
std::string to_hex(const std::vector<std::uint8_t>& bytes);
std::vector<std::uint8_t> from_hex(const std::string& hex);

class SequenceWindow {
 public:
  SequenceWindow() : initialized_(false), last_(0) {}
  void reset() { initialized_ = false; last_ = 0; }
  SequenceDisposition accept(std::uint32_t sequence);
  bool initialized() const { return initialized_; }
  std::uint32_t last_sequence() const { return last_; }
 private:
  bool initialized_;
  std::uint32_t last_;
};

}  // namespace cnvg

#endif  // CNVG_PROTOCOL_PROTOCOL_HPP_
