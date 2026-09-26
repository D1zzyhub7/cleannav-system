# CleanNav System

`cleannav-system` 是 CleanNav 无人清扫车项目的系统级集成、版本固定和团队交接仓库。

它本身不复制 Navigation、Mission Manager 或 Interfaces 的业务源码，而是通过 Git submodule 固定经过审查的组件版本。

当前正式协作仓库共五个：

- `cleannav-interfaces`
- `cleannav-navigation`
- `cleannav-mission-manager`
- `cleannav-hmi`
- `cleannav-system`

Voice 已整合到 `cleannav-hmi/voice/`，不再新建独立 GitHub 仓库。

## 1. 当前系统结构

上层任务链：

    APP / Voice
        ↓
    TaskCommand
        ↓
    Mission Manager
        ↓
    Navigation
        ↓
    candidate control
        ↓
    Safety Supervisor
        ↓
    vehicle command

必须保持：

- APP 不直接发布 `/cmd_vel`；
- Voice 不直接发布 `/cmd_vel`；
- Mission Manager 不发布 `/cmd_vel`；
- Navigation 产生候选运动控制；
- Safety 保持最终运动安全门控职责。

## 2. 当前比赛 HIL 链路

当前已冻结并验证过的 Competition HIL operational path：

    Phone APP
        ↓
    PC HMI Gateway
        ↓
    HTTP/TCP
        ↓
    J6M Mission Manager
        ↓
    HTTP Navigation events/results
        ↓
    PC Navigation / Safety
        ↓
    Gazebo

Voice 历史验证链：

    PC microphone
        ↓
    SenseVoice
        ↓
    VoicePolicy
        ↓
    TaskCommand(source=VOICE)
        ↓
    J6M Mission Manager

跨机器 DDS 做过实验，但 WSL / Windows / Hyper-V UDP inbound 与 discovery 存在问题。

因此比赛冻结 HIL 不依赖跨机器 DDS，当前 operational transport 为 HTTP/TCP。

## 3. 当前目录

    cleannav-system/
    ├── README.md
    ├── .gitmodules
    ├── docs/
    │   ├── COMPONENT_VERSIONS.md
    │   └── J6M_HIL_ARCHITECTURE_BASELINE.md
    └── src/
        ├── cleannav-interfaces/
        ├── cleannav-navigation/
        └── cleannav-mission-manager/

HMI / Voice 当前没有作为 System submodule 管理。

HMI 需要单独 clone：

    https://github.com/D1zzyhub7/cleannav-hmi.git

Voice 位于：

    cleannav-hmi/voice/

## 4. 推荐 clone

推荐：

    git clone --recurse-submodules git@github.com:D1zzyhub7/cleannav-system.git

如果已经普通 clone：

    git submodule update --init --recursive

Submodule 出现在 detached HEAD 是正常现象，因为 System 固定的是 exact commit，而不是自动追踪某个分支。

不要为了消除 detached HEAD 随意切换 submodule 到最新 main。

## 5. 当前组件版本

当前团队交接版本和历史比赛冻结版本见：

`docs/COMPONENT_VERSIONS.md`

当前 System submodule pin：

- Interfaces：`64c14d31f5863f208fe502466c1f25cbd01e2b29`
- Navigation：`501a3f0fdc5aa39731f274d7ffcbbd5dcccf01f5`
- Mission Manager：`9a71e74216488fc043d40f37c6189e3a2df943d7`

Navigation 当前实际比赛开发线：

`feature/pc-demo-mcity`

其功能冻结点：

`2e6b3225d9d6c571f04aab90c7bb8d94d7901709`

## 6. Competition HIL Baseline

历史统一标签：

`competition-hil-baseline-20260921`

该 tag 用于回滚比赛 HIL 冻结状态。

禁止移动、删除或重写该 tag。

后续 README、协作和开发提交可以继续前进，但不改变历史冻结点。

## 7. 当前组件状态

### Interfaces

负责：

- TaskCommand；
- TaskStatus；
- RobotStatus；
- SafetyStatus；
- SafetyLease；
- CleaningTarget；
- Task Catalog。

### Navigation

当前比赛线包含：

- RTAB-Map；
- Nav2；
- Smac Hybrid-A*；
- FollowPath；
- MPPI Ackermann；
- Navigation Facade；
- Safety Lease；
- Safety Supervisor；
- Gazebo MCity Showcase；
- PC ↔ J6M Navigation HIL。

### Mission Manager

负责：

- command validation；
- idempotency；
- Task Catalog；
- Mission Queue；
- execution；
- generation；
- stale callback gate；
- Navigation / Safety adapters；
- Visual Target；
- Task 30；
- PC Showcase；
- J6 HTTP HIL。

Mission Manager 不发布 `/cmd_vel`。

### HMI + Voice

当前 `cleannav-hmi` 包含：

- Flutter APP；
- PC HMI Gateway；
- Occupancy Grid 地图显示；
- Task 30 APP；
- Voice 子项目；
- SenseVoice PC runtime；
- Voice Policy；
- Competition HTTP HIL bridge。

## 8. 已完成验证

Competition HIL 冻结阶段已经完成大量组件级验证。

后续 APP M1 还完成：

- Flutter analyze；
- Flutter test；
- Android debug APK build；
- 真机安装；
- 真机离线 UI；
- Phone → PC Gateway。

详细测试范围见各组件 README 与 `docs/COMPONENT_VERSIONS.md`。

## 9. 当前已知限制

目前仍需要继续完成：

- 真实车辆最终闭环；
- J6M Vehicle Adapter / Arbiter；
- 实车 Ackermann 标定；
- dedicated dynamic obstacle runtime；
- Coverage Cleaning；
- SenseVoice J6M BPU/HBM；
- VLM Shadow Decision；
- 最终异常工况和长期运行测试。

PC Showcase 中的动态行人等元素不能单独作为动态障碍算法已经完成验证的证据。

## 10. 决赛下一阶段

当前主要工作流：

    Interface contract
        ↓
    APP / Voice
        ↓
    Mission Manager
        ↓
    Navigation / Coverage
        ↓
    Safety
        ↓
    Vehicle Adapter
        ↓
    Real Vehicle

并行开展：

- J6M / ECU / sensor integration；
- SenseVoice BPU；
- VLM Shadow Decision；
- Coverage Planner；
- Dynamic Obstacle Behavior；
- APP / Voice / HIL；
- 最终系统集成与演示。

## 11. System 更新规则

修改 submodule pin 前必须明确：

- 目标 branch；
- exact SHA；
- 验证证据；
- 是否影响接口；
- 是否影响当前 Competition baseline。

更新方法：

    cd src/<component>
    git fetch origin
    git checkout --detach <reviewed-sha>
    cd ../..

然后：

    git add src/<component>
    git diff --cached --submodule=short

禁止使用自动追踪远端最新版本的方式替代人工审查。

## 12. HIL 架构文档

J6M HIL 的详细设计、历史实验和当前架构见：

`docs/J6M_HIL_ARCHITECTURE_BASELINE.md`

其中历史 DDS 实验属于技术记录，不代表比赛当前必须采用 DDS。

当前比赛冻结链路仍以 HTTP/TCP HIL 为准。
