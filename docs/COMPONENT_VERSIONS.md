# CleanNav System Component Versions

父仓库记录的 gitlink SHA 才真正决定历史系统版本；`Source branch/ref` 仅说明该 pin 的来源，不是运行时追踪规则。

本表记录 `competition-hil-baseline-20260921` 的五个 component exact SHA。
这些 SHA 是本轮已经审查、测试并提交的 component baseline；branch 仅记录来源，
不表示运行时追踪远端分支。

| Component | Repository | Branch | Frozen component SHA | Role |
|---|---|---|---|---|
| `cleannav-interfaces-filtered` | `git@github.com:D1zzyhub7/cleannav-interfaces.git` | `main` | `e3405138c081e500850ee991f5fa53aece71e1b4` | ROS 2 interface contract / TaskCommand / TaskStatus / CleaningTarget / Safety interfaces |
| `cleannav-navigation-filtered` | `git@github.com:D1zzyhub7/cleannav-navigation.git` | `feature/pc-demo-mcity` | `2e6b3225d9d6c571f04aab90c7bb8d94d7901709` | RTAB-Map / Nav2 / Smac Hybrid-A* / MPPI / Safety / Gazebo Competition Showcase |
| `cleannav-mission-manager-filtered` | `git@github.com:D1zzyhub7/cleannav-mission-manager.git` | `main` | `ed519714f2da4cb0e006cdc9fd27d0a80a769927` | Mission Manager / runtime adapters / PC Showcase / J6 HTTP HIL |
| `cleannav-voice` | `git@github.com:D1zzyhub7/cleannav-voice.git` | `main` | `c4e09c8a8cfa897ab85d4bbeff9b808125b410b4` | offline Voice pipeline / SenseVoice PC runtime / Voice TaskCommand / J6 HTTP HIL bridge |
| `cleannav-hmi` | `git@github.com:D1zzyhub7/cleannav-hmi.git` | `main` | `0da76cf6b9c432c815d5572074188f1dfab71de5` | Flutter APP / PC HMI Gateway / J6 relay / state aggregation / occupancy map |

`cleannav-voice` 和 `cleannav-hmi` 是 external component repositories，不是当前
`cleannav-system` submodule。System 自身版本由它自己的 Git commit 与
`competition-hil-baseline-20260921` tag 确定；本表不自引用 `SYSTEM_SHA`。

## 更新规则

进入目标 submodule 后执行 `git fetch origin`，再 checkout 已审查确认的目标 SHA。回到 `cleannav-system` 根目录后执行：

```bash
git add src/<component>
git diff --cached --submodule=short
```

确认 gitlink 变化及验证依据后，再由父仓库提交。不要使用 `git submodule update --remote` 作为日常自动升级机制。

## M0 Competition HIL Verification

- Interfaces：build/interface verification `PASS`
- Navigation：config + scene `49 passed`；NavigationFacade `26 passed`；Scene `43 passed`；independent `6-package build PASS`
- Navigation RTAB：portable `38-line` config，machine path `0`
- Mission Manager：`584 passed`、`1 skipped`
- Voice：`51 passed`
- HMI Python：`19 passed`
- HMI Flutter：`UNVERIFIED`（当前环境没有 Flutter/Dart SDK）
- Full-system runtime integration：`NOT YET VALIDATED`

验证环境：ROS 2 `Humble`。以上结果证明冻结的 component commit 和 M0 HIL contract
已分别通过组件级验证；它们不代表 `cleannav-system` 层的 full-system runtime
integration 已完成，也不声称 Flutter、real vehicle、dedicated dynamic obstacle
runtime 或 J6M BPU/HBM 已验证。
