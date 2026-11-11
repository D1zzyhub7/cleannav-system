#include "j6m_vehicle_gateway_ros1/gateway_node.hpp"
int main(int argc,char** argv){ros::init(argc,argv,"j6m_vehicle_gateway_ros1");j6m_vehicle_gateway_ros1::GatewayNode node;if(!ros::ok())return 2;ros::spin();return 0;}
