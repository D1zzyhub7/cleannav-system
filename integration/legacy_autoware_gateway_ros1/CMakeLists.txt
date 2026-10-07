cmake_minimum_required(VERSION 3.0.2)
project(j6m_vehicle_gateway_ros1)

add_compile_options(-std=c++14 -Wall -Wextra)
find_package(catkin REQUIRED COMPONENTS roscpp autoware_msgs)
catkin_package(INCLUDE_DIRS include CATKIN_DEPENDS roscpp autoware_msgs)
include_directories(include ../cnvg_protocol/include ${catkin_INCLUDE_DIRS})
add_executable(j6m_vehicle_gateway_ros1_node
  src/j6m_vehicle_gateway_ros1.cpp
  ../cnvg_protocol/src/protocol.cpp
  ../cnvg_protocol/src/command_arbiter.cpp)
target_link_libraries(j6m_vehicle_gateway_ros1_node ${catkin_LIBRARIES})
