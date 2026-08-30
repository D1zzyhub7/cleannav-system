# CleanNav System Component Versions

父仓库记录的 gitlink SHA 才真正决定系统版本；`Source branch/ref` 仅说明该 pin 的来源，不是运行时追踪规则。

| Component | Repository | Pinned SHA | Source branch/ref | Status / reason |
|---|---|---|---|---|
| `cleannav-interfaces` | `git@github.com:D1zzyhub7/cleannav-interfaces.git` | `404ce1443bdbb7e6795f90d088bbfebb1efe8841` | `main` | 公共 ROS 2 接口与跨模块合同基线 |
| `cleannav-navigation` | `git@github.com:D1zzyhub7/cleannav-navigation.git` | `ef5b602166c11b71862f8a54111ef0b67d16b4a3` | `feature/ackermann-hybrid-mppi-v1` | 系统集成选择 Ackermann feature；Navigation `main` 仍是 stable differential-drive baseline，feature 尚未声称 merge 到 `main` |
| `cleannav-mission-manager` | `git@github.com:D1zzyhub7/cleannav-mission-manager.git` | `e55ad6f3ede176bd51779e69ed5b16a359b2c959` | `main` | 任务生命周期与执行编排基线 |

## 更新规则

进入目标 submodule 后执行 `git fetch origin`，再 checkout 已审查确认的目标 SHA。回到 `cleannav-system` 根目录后执行：

```bash
git add src/<component>
git diff --cached --submodule=short
```

确认 gitlink 变化及验证依据后，再由父仓库提交。不要使用 `git submodule update --remote` 作为日常自动升级机制。

## Integration Validation

- Fresh recursive clone：`PASS`
- Pinned SHA restoration：`PASS`
- ROS 2 distribution：`Humble`
- Package discovery：`8 packages`
- `colcon build`：`PASS`（`8 packages finished`、`0 build failures`）
- `colcon test`：`PASS`
- Test result：`374 tests`、`0 errors`、`0 failures`、`1 skipped`
- Full-system runtime：`NOT YET VALIDATED`

这些结果仅证明当前 pinned component set 可精确恢复并在 ROS 2 Humble workspace 中联合 build/test；它们不代表 `cleannav-system` 层的 full-system runtime integration 已完成。
