#include "cnvg_protocol/udp_transport.hpp"

#include <arpa/inet.h>
#include <cerrno>
#include <cstring>
#include <fcntl.h>
#include <poll.h>
#include <sys/socket.h>
#include <unistd.h>

namespace cnvg {

UdpTransport::UdpTransport() : fd_(-1) {}
UdpTransport::~UdpTransport() { close(); }

bool UdpTransport::is_open() const { return fd_ >= 0; }

void UdpTransport::close() {
  if (fd_ >= 0) {
    ::close(fd_);
    fd_ = -1;
  }
}

bool UdpTransport::open(const std::string& bind_ip,
                        std::uint16_t bind_port,
                        std::string* error) {
  close();
  in_addr address;
  if (inet_pton(AF_INET, bind_ip.c_str(), &address) != 1) {
    if (error != NULL) *error = "invalid bind IPv4";
    return false;
  }

  const int fd = socket(AF_INET, SOCK_DGRAM, 0);
  if (fd < 0) {
    if (error != NULL) *error = std::strerror(errno);
    return false;
  }
  const int flags = fcntl(fd, F_GETFL, 0);
  if (flags < 0 || fcntl(fd, F_SETFL, flags | O_NONBLOCK) < 0) {
    if (error != NULL) *error = std::strerror(errno);
    ::close(fd);
    return false;
  }

  sockaddr_in endpoint = {};
  endpoint.sin_family = AF_INET;
  endpoint.sin_addr = address;
  endpoint.sin_port = htons(bind_port);
  if (::bind(fd, reinterpret_cast<sockaddr*>(&endpoint), sizeof(endpoint)) < 0) {
    if (error != NULL) *error = std::strerror(errno);
    ::close(fd);
    return false;
  }
  fd_ = fd;
  if (error != NULL) error->clear();
  return true;
}

bool UdpTransport::receive(Datagram* output,
                           int timeout_ms,
                           const std::string& expected_ip,
                           std::uint16_t expected_port,
                           bool* source_valid,
                           std::string* error) {
  if (output == NULL || fd_ < 0) {
    if (error != NULL) *error = "transport is closed";
    return false;
  }
  if (timeout_ms < 0) timeout_ms = 0;
  if (timeout_ms > 1000) timeout_ms = 1000;

  pollfd descriptor = {};
  descriptor.fd = fd_;
  descriptor.events = POLLIN;
  const int ready = poll(&descriptor, 1, timeout_ms);
  if (ready <= 0) {
    if (ready < 0 && error != NULL) *error = std::strerror(errno);
    return false;
  }

  Datagram datagram;
  sockaddr_in source = {};
  socklen_t source_size = sizeof(source);
  const ssize_t received = recvfrom(
      fd_, datagram.bytes.data(), datagram.bytes.size(), 0,
      reinterpret_cast<sockaddr*>(&source), &source_size);
  if (received < 0) {
    if (error != NULL) *error = std::strerror(errno);
    return false;
  }
  datagram.size = static_cast<std::size_t>(received);
  char source_text[INET_ADDRSTRLEN] = {};
  inet_ntop(AF_INET, &source.sin_addr, source_text, sizeof(source_text));
  datagram.source_ip = source_text;
  datagram.source_port = ntohs(source.sin_port);
  const bool matches = datagram.source_ip == expected_ip &&
                       datagram.source_port == expected_port;
  if (source_valid != NULL) *source_valid = matches;
  *output = datagram;
  if (error != NULL) error->clear();
  return true;
}

bool UdpTransport::send_to(const std::uint8_t* data,
                           std::size_t size,
                           const std::string& ip,
                           std::uint16_t port,
                           std::string* error) {
  if (fd_ < 0 || data == NULL || size == 0 || size > 512 || port == 0) {
    if (error != NULL) *error = "invalid send request";
    return false;
  }
  sockaddr_in destination = {};
  destination.sin_family = AF_INET;
  destination.sin_port = htons(port);
  if (inet_pton(AF_INET, ip.c_str(), &destination.sin_addr) != 1) {
    if (error != NULL) *error = "invalid peer IPv4";
    return false;
  }
  const ssize_t sent = sendto(
      fd_, data, size, 0, reinterpret_cast<sockaddr*>(&destination),
      sizeof(destination));
  if (sent != static_cast<ssize_t>(size)) {
    if (error != NULL) *error = std::strerror(errno);
    return false;
  }
  if (error != NULL) error->clear();
  return true;
}

std::uint16_t UdpTransport::bound_port() const {
  if (fd_ < 0) return 0;
  sockaddr_in endpoint = {};
  socklen_t endpoint_size = sizeof(endpoint);
  if (getsockname(fd_, reinterpret_cast<sockaddr*>(&endpoint),
                  &endpoint_size) < 0) {
    return 0;
  }
  return ntohs(endpoint.sin_port);
}

}  // namespace cnvg
