cmake_minimum_required(VERSION 3.0.2)
project(j6m_vehicle_gateway_ros1)
add_compile_options(-std=c++14 -Wall -Wextra)
find_package(catkin REQUIRED COMPONENTS roscpp autoware_msgs autoware_can_msgs geometry_msgs std_msgs diagnostic_msgs std_srvs)
catkin_package(INCLUDE_DIRS include CATKIN_DEPENDS roscpp autoware_msgs autoware_can_msgs geometry_msgs std_msgs diagnostic_msgs std_srvs)
include_directories(include ../cnvg_protocol/include ${catkin_INCLUDE_DIRS})
add_executable(j6m_vehicle_gateway_ros1_node
  src/main.cpp src/gateway_node.cpp src/vehicle_cmd_mapper.cpp src/state_mapper.cpp
  ../cnvg_protocol/src/protocol.cpp ../cnvg_protocol/src/command_arbiter.cpp
  ../cnvg_protocol/src/session_manager.cpp ../cnvg_protocol/src/production_config.cpp
  ../cnvg_protocol/src/vehicle_mapping.cpp ../cnvg_protocol/src/udp_transport.cpp)
add_dependencies(j6m_vehicle_gateway_ros1_node ${catkin_EXPORTED_TARGETS})
target_link_libraries(j6m_vehicle_gateway_ros1_node ${catkin_LIBRARIES})
