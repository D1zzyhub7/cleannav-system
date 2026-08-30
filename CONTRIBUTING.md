# 贡献 CleanNav System

- `main` 只记录通过系统 Gate 的 integration state。
- system repo 不直接复制组件源码；组件功能修改应进入对应 component repo。
- system repo 只通过 gitlink 更新组件版本；每次 component pin 更新必须记录验证依据。
- 不随意运行 `git submodule update --remote`，也不要把 detached HEAD 当作异常。
- 禁止对 `main` force push；禁止对 shared history 执行 reset、rebase 或 rewrite。
- 合并前检查所有 submodule pins，并完成 review。
- full-system integration 变更必须协调组件接口兼容性。
