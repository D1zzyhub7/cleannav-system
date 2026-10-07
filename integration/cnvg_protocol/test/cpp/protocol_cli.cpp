#include "cnvg_protocol/protocol.hpp"

#include <cstdlib>
#include <iostream>
#include <string>
#include <vector>

namespace {
cnvg::Message hello() {
  cnvg::Message m; m.session_id = 0x0102030405060708ULL;
  m.role = cnvg::PeerRole::J6M_GATEWAY; m.owner_id = "J6M-GATEWAY"; return m;
}
cnvg::Message heartbeat() {
  cnvg::Message m; m.session_id = 0x0102030405060708ULL; m.owner_id = "J6M-GATEWAY"; return m;
}
cnvg::Message control_zero() {
  cnvg::Message m; m.session_id = 0x1112131415161718ULL; m.owner_id = "J6M-GATEWAY";
  m.validity_ms = 300; return m;
}
cnvg::Message control_nonzero() {
  cnvg::Message m = control_zero(); m.enable = true; m.gear = cnvg::Gear::DRIVE;
  m.validity_ms = 250; m.target_speed_mps = 1.25f; m.target_yaw_rate_rps = -0.5f;
  m.target_steering_rad = 0.125f; return m;
}
cnvg::Message control_estop() {
  cnvg::Message m = control_zero(); m.emergency_stop = true; return m;
}
cnvg::Message vehicle_state() {
  cnvg::Message m; m.session_id = 0x2122232425262728ULL; m.owner_id = "MOCK-AUTOWARE";
  m.speed_mps = 1.5f; m.steering_rad = 0.25f; m.gear = cnvg::Gear::DRIVE;
  m.vehicle_mode = cnvg::VehicleMode::AUTONOMOUS; m.gateway_alive = true;
  m.driver_alive = true; return m;
}
cnvg::Message gateway_status() {
  cnvg::Message m; m.session_id = 0x0102030405060708ULL;
  m.gateway_state = cnvg::GatewayState::ACTIVE;
  m.counters = {{10, 20, 30, 40, 1, 2, 3, 4}}; return m;
}
struct Vector { const char* name; cnvg::MessageType type; std::uint32_t seq; std::uint64_t ts; cnvg::Message (*message)(); };
const Vector vectors[] = {
  {"hello", cnvg::MessageType::HELLO, 1, 1700000000123ULL, hello},
  {"heartbeat", cnvg::MessageType::HEARTBEAT, 2, 1700000000124ULL, heartbeat},
  {"control_zero", cnvg::MessageType::CONTROL_COMMAND, 10, 1700000000125ULL, control_zero},
  {"control_nonzero", cnvg::MessageType::CONTROL_COMMAND, 11, 1700000000126ULL, control_nonzero},
  {"control_estop", cnvg::MessageType::CONTROL_COMMAND, 12, 1700000000127ULL, control_estop},
  {"vehicle_state", cnvg::MessageType::VEHICLE_STATE, 13, 1700000000128ULL, vehicle_state},
  {"gateway_status", cnvg::MessageType::GATEWAY_STATUS, 14, 1700000000129ULL, gateway_status},
};
}

int main(int argc, char** argv) {
  try {
    if (argc == 2 && std::string(argv[1]) == "emit") {
      for (std::size_t i = 0; i < sizeof(vectors) / sizeof(vectors[0]); ++i) {
        const Vector& v = vectors[i];
        std::cout << v.name << " " << cnvg::to_hex(cnvg::encode(v.type, v.seq, v.ts, v.message())) << "\n";
      }
      return 0;
    }
    if (argc == 3 && std::string(argv[1]) == "roundtrip") {
      const std::vector<std::uint8_t> bytes = cnvg::from_hex(argv[2]);
      const cnvg::Packet packet = cnvg::decode(bytes);
      const std::vector<std::uint8_t> encoded = cnvg::encode(packet.type, packet.sequence, packet.timestamp_ms, packet.message);
      std::cout << static_cast<unsigned int>(packet.type) << " " << packet.sequence << " "
                << packet.timestamp_ms << " " << cnvg::to_hex(encoded) << "\n";
      return 0;
    }
    std::cerr << "usage: protocol_cli emit | roundtrip HEX\n";
    return 2;
  } catch (const std::exception& e) {
    std::cerr << e.what() << "\n";
    return 1;
  }
}
