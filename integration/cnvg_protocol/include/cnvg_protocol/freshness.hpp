#ifndef CNVG_PROTOCOL_FRESHNESS_HPP_
#define CNVG_PROTOCOL_FRESHNESS_HPP_
#include <cstdint>
namespace cnvg {
inline bool monotonic_fresh(std::uint64_t now_ms,std::uint64_t received_ms,std::uint32_t timeout_ms){return received_ms!=0&&now_ms>=received_ms&&now_ms-received_ms<=timeout_ms;}
inline std::uint32_t effective_command_timeout_ms(std::uint16_t validity_ms,std::uint32_t configured_timeout_ms){return validity_ms==0?0:(validity_ms<configured_timeout_ms?validity_ms:configured_timeout_ms);}
inline std::uint64_t monotonic_age_ms(std::uint64_t now_ms,std::uint64_t received_ms){return received_ms==0||now_ms<received_ms?UINT64_MAX:now_ms-received_ms;}
}
#endif
