#ifndef CNVG_PROTOCOL_UDP_TRANSPORT_HPP_
#define CNVG_PROTOCOL_UDP_TRANSPORT_HPP_
#include <array>
#include <cstddef>
#include <cstdint>
#include <string>
namespace cnvg {
struct Datagram { std::array<std::uint8_t,512> bytes{}; std::size_t size=0; std::string source_ip; std::uint16_t source_port=0; };
class UdpTransport {
 public: UdpTransport(); ~UdpTransport(); UdpTransport(const UdpTransport&)=delete; UdpTransport& operator=(const UdpTransport&)=delete;
  bool open(const std::string& bind_ip,std::uint16_t bind_port,std::string* error);
  void close(); bool is_open() const;
  // timeout is bounded to 1000 ms; false means timeout/error and leaves out untouched.
  bool receive(Datagram* out,int timeout_ms,const std::string& expected_ip,std::uint16_t expected_port,bool* source_valid,std::string* error);
  bool send_to(const std::uint8_t* data,std::size_t size,const std::string& ip,std::uint16_t port,std::string* error);
  std::uint16_t bound_port() const;
 private: int fd_;
};
}  // namespace cnvg
#endif
