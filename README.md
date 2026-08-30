# CleanNav System

`cleannav-system` 是 CleanNav 的系统级集成与版本固定仓库。它本身不承载 Navigation、Mission Manager 或 Interfaces 的业务源码，而是通过 Git submodule 固定一套已知组件 commit，作为统一 clone、build 和 integration 的入口。

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

未来可能加入 `cleannav-perception` 和 `cleannav-hmi`，但它们当前尚未加入本仓库。

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

- Fresh clone 验证：`PASS`
- Fresh ROS 2 Humble workspace package discovery：`8 packages`
- System-level `colcon build`：`PASS`
- 构建结果：`8 packages finished`、`0 build failures`
- System-level `colcon test`：`PASS`
- 测试结果：`374 tests`、`0 errors`、`0 failures`、`1 skipped`

这证明当前 pinned component set 可以从 GitHub 精确恢复，可以在 ROS 2 Humble workspace 中联合 build，并可以联合 test。`skipped` 是测试结果的一部分，不是 failure。

`full-system runtime integration` 尚未在 `cleannav-system` 层完成验证。上述结果不等同于 Mission Manager、Navigation、Safety、HMI、Perception 已完成真实全系统闭环；当前 system repo 也尚未纳入 `cleannav-perception` 或 `cleannav-hmi`。

## 当前组件状态

- `cleannav-interfaces`：公共 ROS 2 接口与跨模块合同。
- `cleannav-mission-manager`：任务生命周期与执行编排，不发布 `/cmd_vel`。
- `cleannav-navigation`：`main` 是 stable differential-drive baseline；system 当前固定 `feature/ackermann-hybrid-mppi-v1`，SHA 为 `ef5b602166c11b71862f8a54111ef0b67d16b4a3`。

Navigation 的 Ackermann feature 已在组件仓库内部验证 Smac Hybrid-A*、MPPI Ackermann、Safety final `/cmd_vel` gate 和 Gazebo closed-loop movement，但这不表示 full CleanNav system integration 已完成，也不表示该 feature 已 merge 到 Navigation `main`。

Mission Manager 不发布 `/cmd_vel`；Safety Supervisor 保持最终速度门控职责。Task Catalog 与 interfaces 合同由 `cleannav-interfaces` 管理，不在本仓库重新定义组件内部业务。

完整组件 pin、来源和理由见 [`docs/COMPONENT_VERSIONS.md`](docs/COMPONENT_VERSIONS.md)。

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
