# CleanNav System

`cleannav-system` 是 CleanNav 的系统级集成与版本固定仓库。它本身不承载 Navigation、Mission Manager 或 Interfaces 的业务源码，而是通过 Git submodule 固定一套已知组件 commit，作为统一 clone、build 和 integration 的入口。

当前已冻结的 M0 Competition HIL operational path 为：

```text
Phone APP
    -> PC HMI Gateway
    -> HTTP/TCP
    -> J6M Mission Manager
    -> HTTP navigation event/result
    -> PC Navigation / Safety execution
    -> Gazebo
```

Voice path：

```text
PC microphone
    -> SenseVoice / VoicePolicy
    -> TaskCommand(source=VOICE)
    -> HTTP HIL
    -> J6M Mission Manager
```

当前 baseline 不是最终实车架构：APP 仍经 PC Gateway，Voice 仍在 PC 侧，
Navigation/Safety 仍在 PC simulation 执行。统一 tag 为
`competition-hil-baseline-20260921`。

跨机 DDS 已做过真实实验，但受到 WSL/Windows/Hyper-V UDP inbound 与发现问题影响，
不属于当前 M0 operational path。DDS 实验记录保留在 HIL 文档中，并标记为
`DEFERRED / EXPERIMENTAL`。

## 当前目录

```text
cleannav-system/
├── README.md
├── LICENSE
├── CONTRIBUTING.md
├── .gitignore
├── .gitmodules
├── docs/
│   └── COMPONENT_VERSIONS.md
└── src/
    ├── cleannav-interfaces/
    ├── cleannav-navigation/
    └── cleannav-mission-manager/
```

`cleannav-voice` 和 `cleannav-hmi` 当前是外部 component repositories，不作为本仓库
submodule 管理；它们通过 M0 HIL HTTP contract 与 system 集成。未来是否加入
`cleannav-perception` 或 HMI submodule，另行决策。

## 推荐 clone

```bash
git clone --recurse-submodules \
  git@github.com:D1zzyhub7/cleannav-system.git
```

普通 clone 后补齐 submodule：

```bash
git submodule update --init --recursive
```

Submodule 默认可能处于 detached HEAD，这是固定版本的正常状态。不要为了“修复 detached HEAD”而随意切换各子模块到最新 `main`。

## ROS 2 workspace

`src/` 是多个独立 ROS 2 repository 的组合。依赖准备完成后，可以从 system 根目录按 ROS 2 / colcon workspace 方式构建：

```bash
source /opt/ros/humble/setup.bash
colcon build
```

## Integration validation

- Git / submodule reproducibility：`PASS`
- Fresh clone 方法：

  ```bash
  git clone --recurse-submodules \
    git@github.com:D1zzyhub7/cleannav-system.git
  ```

- Fresh clone 验证：`PASS`（针对历史 pinned component set）
- Interfaces build/interface verification：`PASS`
- Navigation：config + scene `49 passed`、NavigationFacade `26 passed`、Scene `43 passed`
- Navigation independent build：`6 packages finished`
- Mission Manager：`584 passed`、`1 skipped`
- Voice：`51 passed`
- HMI Python：`19 passed`
- HMI Flutter analyze/test/build：`UNVERIFIED`（Flutter/Dart SDK unavailable）

以上结果是 `competition-hil-baseline-20260921` 的 component-level verification；
`skipped` 是测试结果的一部分，不是 failure。

`full-system runtime integration` 尚未在 `cleannav-system` 层完成验证。上述结果不等同于 Mission Manager、Navigation、Safety、HMI、Voice 已完成真实全系统闭环。

## 当前组件状态

- `cleannav-interfaces`：公共 ROS 2 接口与跨模块合同。
- `cleannav-mission-manager`：任务生命周期与执行编排，不发布 `/cmd_vel`。
- `cleannav-navigation`：冻结于 `feature/pc-demo-mcity` 的 `2e6b3225d9d6c571f04aab90c7bb8d94d7901709`，包含 Ackermann Nav2、Smac Hybrid-A*、MPPI、Safety 和 Gazebo Competition Showcase。
- `cleannav-voice`：外部 Voice pipeline；当前 PC microphone/SenseVoice 输出正式 `TaskCommand`，再通过 Competition HIL HTTP adapter 到 J6。
- `cleannav-hmi`：外部 Flutter APP 与 PC HMI Gateway；当前通过 HTTP relay 到 J6，不发布 `/cmd_vel`。

Navigation 的 Ackermann feature 已在组件仓库内部验证 Smac Hybrid-A*、MPPI Ackermann、Safety final `/cmd_vel` gate 和 Gazebo closed-loop movement，但这不表示 full CleanNav system integration 已完成，也不表示该 feature 已 merge 到 Navigation `main`。

Mission Manager 不发布 `/cmd_vel`；Safety Supervisor 保持最终速度门控职责。Task Catalog 与 interfaces 合同由 `cleannav-interfaces` 管理，不在本仓库重新定义组件内部业务。

完整组件 pin、来源和理由见 [`docs/COMPONENT_VERSIONS.md`](docs/COMPONENT_VERSIONS.md)。

五个 component 的 branch、role 和 exact SHA 见 [`docs/COMPONENT_VERSIONS.md`](docs/COMPONENT_VERSIONS.md)。
System 自身不在该表中自引用 SHA；它由自己的 commit 和统一 annotated tag 标识。

## M0 Known Limitations

- Flutter analyze/test/build：`UNVERIFIED`，当前 WSL 环境没有 Flutter/Dart SDK；
- dedicated dynamic obstacle runtime：尚未单独验证；
- near-goal MPPI behavior：留给 navigation hardening；
- real vehicle calibration：尚未执行；
- physical leaf completion：仅为 Competition Demo semantics；
- SenseVoice：当前仍在 PC-side；
- J6M BPU/HBM：M0 未实现；
- cross-machine DDS：`DEFERRED / EXPERIMENTAL`；当前 operational transport 为 HTTP/TCP。

## Future Direction

- M1：APP HIL runtime completion；
- M2：SenseVoice / ASR -> J6M BPU / HBM；
- M3：APP Gateway + Voice runtime J6-native；
- M4：real vehicle integration；
- M5：navigation hardening。

以上是 future work，不应解释为当前 M0 capability。

## 更新 component pin

正确流程：

```bash
cd src/<component>
git fetch origin
git checkout <reviewed-commit-sha>
cd ../..
git add src/<component>
git diff --cached --submodule=short
```

确认后由父仓库 commit 新 gitlink。不要把 `git submodule update --remote` 作为日常自动升级机制；system 必须精确固定已审查、已验证的 SHA，不能默默追踪远端最新提交。
