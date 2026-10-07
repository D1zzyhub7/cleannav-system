#include "cnvg_protocol/protocol.hpp"

#include <cmath>
#include <cstdlib>
#include <cstring>
#include <limits>
#include <stdexcept>
#include <type_traits>

namespace cnvg {
namespace {
const std::size_t kHeaderSize = 24;
const std::size_t kCrcSize = 4;
const std::size_t kMaxDatagram = 512;
const std::uint8_t kMagic[4] = {'C', 'N', 'V', 'G'};
const std::uint8_t kVersion = 1;
static_assert(sizeof(float) == 4, "CNVG requires IEEE-754 binary32 float");
static_assert(std::numeric_limits<float>::is_iec559,
              "CNVG requires IEEE-754 binary32 float");

class Writer {
 public:
  void u8(std::uint8_t v) { bytes_.push_back(v); }
  void i8(std::int8_t v) { u8(static_cast<std::uint8_t>(v)); }
  void u16(std::uint16_t v) { u8(static_cast<std::uint8_t>(v >> 8)); u8(static_cast<std::uint8_t>(v)); }
  void u32(std::uint32_t v) { for (int s = 24; s >= 0; s -= 8) u8(static_cast<std::uint8_t>(v >> s)); }
  void u64(std::uint64_t v) { for (int s = 56; s >= 0; s -= 8) u8(static_cast<std::uint8_t>(v >> s)); }
  void f32(float v) {
    if (!std::isfinite(v)) throw ProtocolError("non-finite float");
    std::uint32_t bits = 0;
    std::memcpy(&bits, &v, sizeof(bits));
    u32(bits);
  }
  void owner(const std::string& value) {
    if (value.empty() || value.size() > 16) throw ProtocolError("owner_id width");
    for (std::string::const_iterator it = value.begin(); it != value.end(); ++it) {
      const unsigned char c = static_cast<unsigned char>(*it);
      if (c == 0 || c > 0x7f) throw ProtocolError("owner_id must be non-NUL ASCII");
      u8(c);
    }
    for (std::size_t i = value.size(); i < 16; ++i) u8(0);
  }
  const std::vector<std::uint8_t>& bytes() const { return bytes_; }
 private:
  std::vector<std::uint8_t> bytes_;
};

class Reader {
 public:
  Reader(const std::uint8_t* data, std::size_t size) : data_(data), size_(size), pos_(0) {}
  std::uint8_t u8() { need(1); return data_[pos_++]; }
  std::int8_t i8() { return static_cast<std::int8_t>(u8()); }
  std::uint16_t u16() { const std::uint16_t a = u8(); return static_cast<std::uint16_t>((a << 8) | u8()); }
  std::uint32_t u32() { std::uint32_t v = 0; for (int i = 0; i < 4; ++i) v = (v << 8) | u8(); return v; }
  std::uint64_t u64() { std::uint64_t v = 0; for (int i = 0; i < 8; ++i) v = (v << 8) | u8(); return v; }
  float f32() { const std::uint32_t bits = u32(); float value = 0; std::memcpy(&value, &bits, sizeof(value)); if (!std::isfinite(value)) throw ProtocolError("non-finite float"); return value; }
  std::string owner() {
    std::string value;
    bool padding = false;
    for (int i = 0; i < 16; ++i) {
      const std::uint8_t c = u8();
      if (c == 0) { padding = true; continue; }
      if (padding || c > 0x7f) throw ProtocolError("invalid owner_id padding/ASCII");
      value.push_back(static_cast<char>(c));
    }
    if (value.empty()) throw ProtocolError("empty owner_id");
    return value;
  }
  std::size_t remaining() const { return size_ - pos_; }
 private:
  void need(std::size_t n) { if (n > size_ - pos_) throw ProtocolError("truncated payload"); }
  const std::uint8_t* data_;
  std::size_t size_;
  std::size_t pos_;
};

bool valid_gear(std::int8_t v) { return v >= 0 && v <= 5; }
bool valid_mode(std::uint8_t v) { return v <= 4; }
bool valid_gateway_state(std::uint8_t v) { return v <= 5; }
bool valid_role(std::uint8_t v) { return v == 1 || v == 2; }
void require(bool ok, const char* reason) { if (!ok) throw ProtocolError(reason); }

std::vector<std::uint8_t> payload_for(MessageType type, const Message& m) {
  Writer w;
  switch (type) {
    case MessageType::HELLO:
      require(valid_role(static_cast<std::uint8_t>(m.role)), "invalid peer role");
      w.u64(m.session_id); w.u8(static_cast<std::uint8_t>(m.role)); w.owner(m.owner_id); break;
    case MessageType::HEARTBEAT:
      w.u64(m.session_id); w.owner(m.owner_id); break;
    case MessageType::CONTROL_COMMAND:
      require(m.validity_ms >= 1 && m.validity_ms <= 5000, "invalid validity_ms");
      require(static_cast<std::uint8_t>(m.control_mode) <= 1, "invalid control mode");
      require(valid_gear(static_cast<std::int8_t>(m.gear)), "invalid gear");
      w.u64(m.session_id); w.owner(m.owner_id); w.u8(m.enable ? 1 : 0);
      w.u8(m.emergency_stop ? 1 : 0); w.u8(static_cast<std::uint8_t>(m.control_mode));
      w.i8(static_cast<std::int8_t>(m.gear)); w.u16(m.validity_ms);
      w.f32(m.target_speed_mps); w.f32(m.target_yaw_rate_rps); w.f32(m.target_steering_rad); break;
    case MessageType::VEHICLE_STATE:
      require(valid_gear(static_cast<std::int8_t>(m.gear)), "invalid gear");
      require(valid_mode(static_cast<std::uint8_t>(m.vehicle_mode)), "invalid vehicle mode");
      w.u64(m.session_id); w.owner(m.owner_id); w.f32(m.speed_mps); w.f32(m.steering_rad);
      w.i8(static_cast<std::int8_t>(m.gear)); w.u8(static_cast<std::uint8_t>(m.vehicle_mode));
      w.u8(m.emergency ? 1 : 0); w.u8(m.gateway_alive ? 1 : 0); w.u8(m.driver_alive ? 1 : 0); w.u32(m.fault_code); break;
    case MessageType::GATEWAY_STATUS:
      require(valid_gateway_state(static_cast<std::uint8_t>(m.gateway_state)), "invalid gateway state");
      w.u64(m.session_id); w.u8(static_cast<std::uint8_t>(m.gateway_state));
      for (std::size_t i = 0; i < m.counters.size(); ++i) w.u32(m.counters[i]);
      break;
    default: throw ProtocolError("unknown message type");
  }
  return w.bytes();
}

}  // namespace

std::uint32_t crc32(const std::uint8_t* data, std::size_t size) {
  std::uint32_t crc = 0xffffffffu;
  for (std::size_t i = 0; i < size; ++i) {
    crc ^= data[i];
    for (int bit = 0; bit < 8; ++bit) crc = (crc >> 1) ^ (0xedb88320u & (0u - (crc & 1u)));
  }
  return crc ^ 0xffffffffu;
}

std::vector<std::uint8_t> encode(MessageType type, std::uint32_t sequence,
                                 std::uint64_t timestamp_ms, const Message& message) {
  const std::vector<std::uint8_t> payload = payload_for(type, message);
  if (kHeaderSize + payload.size() + kCrcSize > kMaxDatagram) throw ProtocolError("datagram too large");
  Writer w;
  for (int i = 0; i < 4; ++i) w.u8(kMagic[i]);
  w.u8(kVersion); w.u8(static_cast<std::uint8_t>(type)); w.u16(0);
  w.u32(sequence); w.u64(timestamp_ms); w.u16(static_cast<std::uint16_t>(payload.size())); w.u16(0);
  std::vector<std::uint8_t> result = w.bytes();
  result.insert(result.end(), payload.begin(), payload.end());
  const std::uint32_t crc = crc32(result.data(), result.size());
  result.push_back(static_cast<std::uint8_t>(crc >> 24));
  result.push_back(static_cast<std::uint8_t>(crc >> 16));
  result.push_back(static_cast<std::uint8_t>(crc >> 8));
  result.push_back(static_cast<std::uint8_t>(crc));
  return result;
}

Packet decode(const std::uint8_t* data, std::size_t size) {
  if (data == NULL || size < kHeaderSize + kCrcSize || size > kMaxDatagram) throw ProtocolError("invalid datagram size");
  for (int i = 0; i < 4; ++i) if (data[i] != kMagic[i]) throw ProtocolError("bad magic");
  if (data[4] != kVersion) throw ProtocolError("unsupported protocol version");
  const std::uint8_t raw_type = data[5];
  if (raw_type < 1 || raw_type > 5) throw ProtocolError("unknown message type");
  if (data[6] != 0 || data[7] != 0 || data[22] != 0 || data[23] != 0) throw ProtocolError("unsupported flags/reserved field");
  const std::uint16_t payload_len = static_cast<std::uint16_t>((static_cast<std::uint16_t>(data[20]) << 8) | data[21]);
  if (kHeaderSize + payload_len + kCrcSize != size) throw ProtocolError("payload length mismatch");
  const std::uint32_t expected_crc = crc32(data, size - kCrcSize);
  const std::uint32_t got_crc = (static_cast<std::uint32_t>(data[size - 4]) << 24) |
      (static_cast<std::uint32_t>(data[size - 3]) << 16) |
      (static_cast<std::uint32_t>(data[size - 2]) << 8) | data[size - 1];
  if (expected_crc != got_crc) throw ProtocolError("bad CRC32");

  Packet packet;
  packet.type = static_cast<MessageType>(raw_type);
  Reader header(data + 8, 16);
  packet.sequence = header.u32(); packet.timestamp_ms = header.u64();
  (void)header.u16(); (void)header.u16();
  Reader r(data + kHeaderSize, payload_len);
  Message& m = packet.message;
  switch (packet.type) {
    case MessageType::HELLO: {
      if (payload_len != 25) throw ProtocolError("wrong HELLO payload length");
      m.session_id = r.u64(); const std::uint8_t role = r.u8();
      if (!valid_role(role)) throw ProtocolError("invalid peer role");
      m.role = static_cast<PeerRole>(role); m.owner_id = r.owner(); break;
    }
    case MessageType::HEARTBEAT:
      if (payload_len != 24) throw ProtocolError("wrong HEARTBEAT payload length");
      m.session_id = r.u64(); m.owner_id = r.owner(); break;
    case MessageType::CONTROL_COMMAND: {
      if (payload_len != 42) throw ProtocolError("wrong CONTROL_COMMAND payload length");
      m.session_id = r.u64(); m.owner_id = r.owner();
      const std::uint8_t enable = r.u8(), estop = r.u8(), mode = r.u8();
      const std::int8_t gear = r.i8(); m.validity_ms = r.u16();
      if (enable > 1 || estop > 1 || mode > 1 || !valid_gear(gear) || m.validity_ms < 1 || m.validity_ms > 5000) throw ProtocolError("invalid CONTROL_COMMAND field");
      m.enable = enable != 0; m.emergency_stop = estop != 0; m.control_mode = static_cast<ControlMode>(mode); m.gear = static_cast<Gear>(gear);
      m.target_speed_mps = r.f32(); m.target_yaw_rate_rps = r.f32(); m.target_steering_rad = r.f32(); break;
    }
    case MessageType::VEHICLE_STATE: {
      if (payload_len != 41) throw ProtocolError("wrong VEHICLE_STATE payload length");
      m.session_id = r.u64(); m.owner_id = r.owner(); m.speed_mps = r.f32(); m.steering_rad = r.f32();
      const std::int8_t gear = r.i8(); const std::uint8_t mode = r.u8();
      const std::uint8_t emergency = r.u8(), gateway_alive = r.u8(), driver_alive = r.u8(); m.fault_code = r.u32();
      if (!valid_gear(gear) || !valid_mode(mode) || emergency > 1 || gateway_alive > 1 || driver_alive > 1) throw ProtocolError("invalid VEHICLE_STATE field");
      m.gear = static_cast<Gear>(gear); m.vehicle_mode = static_cast<VehicleMode>(mode); m.emergency = emergency != 0; m.gateway_alive = gateway_alive != 0; m.driver_alive = driver_alive != 0; break;
    }
    case MessageType::GATEWAY_STATUS: {
      if (payload_len != 41) throw ProtocolError("wrong GATEWAY_STATUS payload length");
      m.session_id = r.u64(); const std::uint8_t state = r.u8();
      if (!valid_gateway_state(state)) throw ProtocolError("invalid GATEWAY_STATUS state");
      m.gateway_state = static_cast<GatewayState>(state);
      for (std::size_t i = 0; i < m.counters.size(); ++i) {
        m.counters[i] = r.u32();
      }
      break;
    }
  }
  if (r.remaining() != 0) throw ProtocolError("trailing payload data");
  return packet;
}

std::string to_hex(const std::vector<std::uint8_t>& bytes) {
  static const char digits[] = "0123456789abcdef";
  std::string result; result.reserve(bytes.size() * 2);
  for (std::size_t i = 0; i < bytes.size(); ++i) { result.push_back(digits[bytes[i] >> 4]); result.push_back(digits[bytes[i] & 0x0f]); }
  return result;
}

std::vector<std::uint8_t> from_hex(const std::string& hex) {
  if (hex.size() % 2 != 0) throw ProtocolError("hex input length must be even");
  std::vector<std::uint8_t> out; out.reserve(hex.size() / 2);
  for (std::size_t i = 0; i < hex.size(); i += 2) {
    const std::string byte = hex.substr(i, 2);
    char* end = NULL; const unsigned long v = std::strtoul(byte.c_str(), &end, 16);
    if (end == NULL || *end != '\0' || v > 255) throw ProtocolError("invalid hex input");
    out.push_back(static_cast<std::uint8_t>(v));
  }
  return out;
}

SequenceDisposition SequenceWindow::accept(std::uint32_t sequence) {
  if (!initialized_) { initialized_ = true; last_ = sequence; return SequenceDisposition::ACCEPT; }
  const std::uint32_t delta = sequence - last_;
  if (delta == 0) return SequenceDisposition::DUPLICATE;
  if (delta >= 0x80000000u) return SequenceDisposition::OUT_OF_ORDER;
  last_ = sequence; return SequenceDisposition::ACCEPT;
}

}  // namespace cnvg
