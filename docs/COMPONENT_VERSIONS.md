# CleanNav System Component Versions

`cleannav-system` 负责记录 CleanNav 多仓库集成版本。

父仓库中的 submodule gitlink SHA 才决定实际 checkout 的组件版本。分支名称只记录版本来源，不作为自动追踪规则。

## 1. 当前团队交接版本（2026-09-26）

当前 `cleannav-system` 开发线固定以下三个 ROS 2 核心 submodule：

| Component | Repository | Source branch | Current pin |
| --- | --- | --- | --- |
| `cleannav-interfaces` | `D1zzyhub7/cleannav-interfaces` | `main` | `64c14d31f5863f208fe502466c1f25cbd01e2b29` |
| `cleannav-navigation` | `D1zzyhub7/cleannav-navigation` | `feature/pc-demo-mcity` | `501a3f0fdc5aa39731f274d7ffcbbd5dcccf01f5` |
| `cleannav-mission-manager` | `D1zzyhub7/cleannav-mission-manager` | `main` | `9a71e74216488fc043d40f37c6189e3a2df943d7` |

其中：

- Interfaces 当前 main 已包含最新接口交接 README；
- Navigation 当前比赛开发线仍为 `feature/pc-demo-mcity`；
- Navigation 功能冻结点仍为 `2e6b3225d9d6c571f04aab90c7bb8d94d7901709`；
- `501a3f0` 相比冻结点主要增加比赛交接 README；
- Mission Manager 当前 main 已包含最新比赛实现与交接 README。

## 2. HMI 与 Voice

HMI 当前独立仓库：

`D1zzyhub7/cleannav-hmi`

当前 main：

`6ddff0f88e200136f2462e42e50aaaccab2d3aa6`

Voice 已经合并到：

`cleannav-hmi/voice/`

因此当前团队协作不再创建单独的 `cleannav-voice` GitHub 仓库。

历史独立 Voice 源码冻结点：

`c4e09c8a8cfa897ab85d4bbeff9b808125b410b4`

该 SHA 用于历史追溯，不代表当前存在独立 Voice 远程仓库。

HMI 当前不作为 `cleannav-system` submodule 管理，组员需要单独 clone。

## 3. Competition HIL 历史冻结基线

统一历史标签：

`competition-hil-baseline-20260921`

冻结时组件功能基线：

| Component | Frozen SHA |
| --- | --- |
| Interfaces | `e3405138c081e500850ee991f5fa53aece71e1b4` |
| Navigation | `2e6b3225d9d6c571f04aab90c7bb8d94d7901709` |
| Mission Manager | `ed519714f2da4cb0e006cdc9fd27d0a80a769927` |
| Legacy Voice | `c4e09c8a8cfa897ab85d4bbeff9b808125b410b4` |
| HMI | `0da76cf6b9c432c815d5572074188f1dfab71de5` |

这些 SHA 和 tag 用于比赛 HIL 基线回滚。

禁止重写已有 baseline tag。

## 4. 当前验证状态

历史 Competition HIL 基线已完成的组件级验证包括：

- Interfaces build / interface verification：PASS；
- Navigation config + scene：49 passed；
- NavigationFacade：26 passed；
- Scene：43 passed；
- Navigation independent build：6 packages PASS；
- Mission Manager：584 passed，1 skipped；
- Voice：51 passed；
- HMI Python：19 passed。

在后续 M1 APP 收口中还完成了：

- Flutter `pub get`：PASS；
- Flutter analyze：PASS；
- Flutter test：12/12 PASS；
- Android debug APK build：PASS；
- 真机 side-by-side 安装：PASS；
- 真机离线 UI 验收：PASS；
- Phone → PC HMI Gateway：PASS。

这些 APP 验证发生在 M0 baseline 冻结之后，因此不应反写成 9 月 21 日冻结点本身已经具备的验证证据。

当前仍未宣称完成：

- 最终实车全系统闭环；
- J6M 最终 Vehicle Adapter / Arbiter；
- 真实车辆 Ackermann 标定；
- dedicated dynamic obstacle 完整 Runtime；
- SenseVoice J6M BPU/HBM；
- VLM 实车 Shadow Decision；
- 最终 Coverage Cleaning。

## 5. 更新 submodule pin

更新组件时必须显式 checkout 已审查的 SHA：

    cd src/<component>
    git fetch origin
    git checkout --detach <reviewed-sha>
    cd ../..

然后：

    git add src/<component>
    git diff --cached --submodule=short

确认 gitlink 和验证依据以后才能提交。

不要把：

    git submodule update --remote

作为日常升级方式。

System 仓库必须精确固定经过审查的版本，不能自动追踪远程最新分支。

## 6. 当前 GitHub 仓库

当前团队正式维护五个 GitHub 仓库：

- `cleannav-interfaces`
- `cleannav-navigation`
- `cleannav-mission-manager`
- `cleannav-hmi`
- `cleannav-system`

Voice 作为 `cleannav-hmi/voice/` 子目录继续维护。
