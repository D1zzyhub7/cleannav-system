# CleanNav × Legacy Autoware 通信审查报告

日期：2026-10-08。范围：J6M ROS2 gateway ↔ CNVG UDP ↔ production ROS1 adapter ↔ legacy xsugv 接口。未审计 HMI、语音或工程全部 DDS 通信。

审查基线：`feature/j6m-autoware-gateway-v1`，HEAD `176304992933355afa91dca046133bb51a55f617`，包含当前未提交 V3 工作区。此次只新增本报告；未修复实现、未提交、未安装 ROS1、未编译目标 ROS1 包、未连接实车或发布真实控制。测试网络仅 loopback。

## 结论

有明确问题。协议/core 已有良好基础，但 production adapter 尚未形成可用、可验收的端到端闭环。以前的离线测试 PASS 不能代表 production 链路 PASS，也不能据此认定主要只剩现场构建与参数配置。

建议当前状态：

- NET-OFFLINE-V3：PARTIAL。
- ROS1 PRODUCTION ADAPTER：PARTIAL。
- CNVG V1.1：暂缓正式冻结，先解决状态未知值、控制模式和会话授权语义；现有 wire 是否需要变化另行决定。
- 下一步：离线修复与生产路径验收；NET-1 只读现场审计可以单独开展，实际控制联调须等待缺陷关闭。

## 发现与证据

P0 表示生产联调前必须解决；P1 表示控制安全验收前必须解决。以下行号对应当前工作区。

### F1 / P0：ROS1 API 参数类型错误，存在编译阻塞

`integration/legacy_autoware_gateway_ros1/src/gateway_node.cpp:355` 将 `payload` 声明成 `std::string`，随后传给 `ros::master::execute` 第四参数。标准 ROS1 API 需要 `XmlRpc::XmlRpcValue&`。

这是静态 API 对照发现，本次没有构建目标 ROS1 包。应修正类型并在已确认的目标 distro/Autoware 消息版本上构建整个 adapter，不能用 standalone core 编译替代。

官方 API 签名证据：[ROS 官方文档中的 execute 定义](https://docs.ros.org/kinetic/api/naoqi_driver/html/publishers_2camera_8cpp_source.html)；官方 roscpp 使用示例：[param.cpp](https://docs.ros.org/en/jade/api/roscpp/html/param_8cpp_source.html)。

### F2 / P0：ROS1 没有发送 HEARTBEAT，J6M 永远不能通过就绪检查

`gateway_node.cpp:383`、`:471`、`:498` 的发送路径只有 HELLO 与 VEHICLE_STATE。HEARTBEAT 仅在接收路径出现。

`src/cleannav-vehicle-gateway/cleannav_vehicle_gateway/j6m_gateway_node.py:522` 明确要求 `_peer_heartbeat_rx` 存在且新鲜。因此，即使所有其他条件满足，当前 production 对端也不能让 J6M 正常使能。

修复：增加有明确周期的反向 HEARTBEAT；补双向丢心跳、恢复、重启测试。ROS1 同时缺少 GATEWAY_STATUS 发送，应补齐远端可见的 owner/故障诊断，但它不是这里的直接 ready 阻塞条件。

### F3 / P0：故障未知状态与 J6M 放行条件没有闭合

`integration/cnvg_protocol/include/cnvg_protocol/vehicle_mapping.hpp` 中 StateInput 默认为 `FAULT_CODE_UNKNOWN`；ROS1 StateMapper 没有接入实际 fault 字段，`state_mapper.cpp:110` 将这个值发出。

`j6m_gateway_node.py:551` 只允许 `fault_code == 0`。所以即使补齐心跳，正常控制仍然不能使能。

这也是合理保守默认值暴露出的集成缺口，不能直接把未知值改成 0。应定义未知/已知正常/已知故障及其数据来源、时效和控制策略；没有可信故障反馈时明确保持禁止使能。ROS1 的 `vehicle_fault` 只由 VehicleMode::FAULT 推导，而 StateMapper 仅给出 AUTO/MANUAL，也未形成实际故障输入路径。

### F4 / P0：TWIST_RAW 的转弯指令被静默丢弃

J6M 默认模式为 TWIST_RAW（`j6m_gateway_node.py:77`），该模式只填 yaw rate，steering 保持 0（`:586`）。

`integration/cnvg_protocol/src/vehicle_mapping.cpp:7` 没有检查 control_mode，也不读取 yaw rate，直接用 steering 映射 VehicleCmd。结果是带转弯意图的命令可以被接受为直行命令。当前 F2/F3 会阻止正常使能，但修复它们后将暴露此缺陷。

纯 core 复现结果：输入 speed=1 m/s、yaw_rate=0.4 rad/s、steering=0，得到 accepted=1、speed=1、steering_degrees=0。

修复：生产适配器明确只接受已支持模式；优先要求 ACKERMANN 并拒绝 TWIST_RAW，或在有已确认车辆几何参数、低速/倒车/限幅策略后实现转换。禁止猜测轴距等参数。

### F5 / P1：转角反馈重复缩放，缩小 100 倍

已读取旧仓库真实源码：

`/mnt/g/揭榜挂帅小挑战杯/11.小黄车代码xs-autowareai-v1.14.0-master/xs-autowareai-v1.14.0-master/src/autoware/utilities/xsugv_interface/nodes/xsugv_interface/xsugv_interface.cpp:318`

生产者执行 `can_msg.angle = ivcu_state1.steering * 0.01`。新 `state_mapper.cpp:52` 在 DEGREES 配置下又乘 `0.01`。

例如原始 1000 对应上游 10 度，新适配器会按 0.1 度编码。应按 ROS 消息字段的实际单位转换一次，增加上游原始值→CANInfo→CNVG 的链路测试。物理转角定义和正负方向仍须现场确认。

### F6 / P1：反馈映射覆盖软件急停锁存

`gateway_node.cpp:475` 先将软件急停写入 state.emergency；随后 `state_mapper.cpp:108` 用 mapped.emergency 覆盖。StateInput.emergency 默认 false，当前回调没有更新它。

状态输入齐全、映射成功时，可能出现本地 ESTOP 锁存却向 J6M 回报 emergency=false。此发现不代表本地急停锁存失效；本地 arbiter 仍读取 software_estop_latched。

修复：区分车辆急停与网关软件急停，定义合成规则，并在映射之后设置最终反馈；验证进入、持续锁存、断联及人工复位全过程。

### F7 / P1：会话更新没有撤销旧控制权

`gateway_node.cpp:453` 在 SESSION_CHANGED 时只清除命令/心跳缓存，未清除 arbiter owner/request。接收循环可以在同一轮继续接受新会话的 heartbeat 和 command。随后 arbiter 看到条件齐全，直接维持 OWNER_J6M（`command_arbiter.cpp:122`）。

纯 core 按适配器事件顺序复现：session_changed=1、before_enabled=1、after_enabled=1、after_transitioning=0，期间没有新 owner request。

这是条件性缺陷，不代表每次真实 J6M 重启都会触发。修复：授权绑定会话，切换会话时立即撤销旧授权/待执行命令，保留故障和急停锁存，要求显式重新申请并经历过渡。新增同批次 HELLO+HEARTBEAT+COMMAND 测试。

### F8 / P1：超时失效保护依赖可能阻塞的同一控制回调

`gateway_node.cpp:503` 每个 20 ms timer 回调先同步查询 ROS master，再在 `:399` 无包数/时间预算地排空 UDP，之后才计算 freshness 和执行零输出。整个过程还使用进入回调时读取的 now_ms。定时器本身采用 ROS 时间（`:148`）。

master 响应缓慢、持续收包或 ROS 仿真时钟暂停时，可能推迟超时处理；耗时后旧 now_ms 也会低估当前命令年龄。本次没有测量目标机延迟，因此这是由结构确认的风险，不是已测得的停机时间。

修复：控制 watchdog 使用单调时钟驱动；拓扑查询移到独立低频路径且结果带时效；限制每轮收包工作量；决策前重新取时间；独立验证驱动/IVCU 的失联停车机制。测试 master 停顿、收包压力、时钟暂停、进程挂起下的行为。零目标输出不能代替物理制动验证。

## 本轮验证结果与覆盖限制

- 新建 `/tmp/cnvg_communication_audit`，Debug 模式独立构建成功，CTest **2/2 PASS**，assert 未被 Release 宏关闭。
- 网关现有 Python 测试目录 **51 PASS**（其中协议/跨语言/golden vectors 子集 26 PASS，包含在 51 内，不重复计数）。
- `git diff --check` 通过。
- 临时纯 C++ 复现程序 `/tmp/cnvg_communication_audit/probe.cpp` 证实 F4、F7；同时输出默认 fault_code=4294967295、emergency=0。
- C++ standalone CMake 只构建 core 及测试，不构建 ROS1 gateway_node/state_mapper。现有 Python mock 与真实 ROS1 production adapter 不是同一实现，所以 mock 集成通过不能覆盖 F1/F2/F5/F6。
- 未重跑全仓库回归；未将历史 807 项测试计为本轮结果。没有 ROS1 target build、真实网络或实车验证结论。

## 后续实施方案及验收门槛

1. **离线修复 P0**：修正 ROS API；补反向 heartbeat；明确 fault 数据质量和 ready 契约；拒绝不支持控制模式。验收：测试对端能在合法完整状态下进入 ready，缺任何必要条件均不放行；转弯意图不会被静默转为直行。
2. **修复 P1**：转角只缩放一次；急停反馈保留锁存；session 更换撤销授权；控制 watchdog 与阻塞工作隔离。验收：为 F5–F8 各提供失败复现和通过结果，并给出配置超时与实际最坏响应时间的对应关系。
3. **补生产路径自动化**：将调度/状态合成逻辑抽成可独立运行的生产核心，建立 Python J6M ↔ production C++ 核心的 loopback harness，复用真实发送调度、会话和映射，避免仅测试另写 mock；补丢包、重复、乱序、会话重启、未知故障、转角单位、急停等场景。用独立 CI job 明确区分 codec、production 核心和 ROS1 adapter 构建结果。
4. **目标环境验收**：得到真实 Autoware PC 后先执行 NET-1 只读审计，确认 distro、消息定义、话题类型、发布者、频率和实际配置；再在获准的目标环境完整构建 ROS1 adapter。继续禁止绕过故障未知/配置未知的保护来“跑通”。
5. **现场控制验收**：前述项关闭后，在受控条件下依次验证双向状态、控制权切换、低速转向、心跳断开、进程停止与物理制动。确认 xsugv/IVCU 独立 watchdog 和急停后，才给生产链路 PASS。

优先顺序：先解决构建和两端契约，再关闭模式/映射/会话/调度缺陷，最后做现场控制。此次报告不包含实施修复。
