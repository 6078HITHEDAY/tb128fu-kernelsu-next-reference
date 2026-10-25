# TB128FU × KernelSU-Next (legacy) × SUSFS v2.3.0

在 **Lenovo TB128FU**（小新 Pad 2022 / P89990JA1 / grass / SM6225 / Android 13 / ZUI 15）上，把
**KernelSU-Next `legacy` 分支（非 GKI）**以 **manual hook** 方式接进 4.19 内核，并内置
**SUSFS v2.3.0 NON-GKI** 的完整参考实现。

> **English:** Reference patch set and field notes for running KernelSU-Next (legacy, non-GKI)
> with manual hook and built-in SUSFS v2.3.0 on the Lenovo TB128FU. This is not a kernel fork or a
> KernelSU fork — it is a set of patches against pinned upstream commits, plus build, packaging and
> validation notes. Everything here was built and verified on the device listed below.

本仓库的 git 历史只放**补丁与文档**，不含内核全树、管理器 APK 或原厂固件；最终 boot 镜像与
校验值作为 [Release r10](https://github.com/6078HITHEDAY/tb128fu-kernelsu-next-reference/releases/tag/r10)
附件发布。补丁已验证能在下列基线提交上逐级干净应用，并**精确复现**当时的源码树
（见 [`patches/README.md`](patches/README.md)）。

## 项目状态

这套 KSU 方案在 2026-10-25 完成 r10 实测（管理器工作中 / manual / SUSFS 生效）。之后设备改用
原厂 4.19.157 + APatch，本仓库作为**可复现的参考存档**保留：补丁与结论都经过实际上机验证，
但不再跟随上游更新。

## 基线

| 组件 | 版本 / 提交 |
|---|---|
| 设备 | Lenovo TB128FU，grass，SM6225，A/B，当前 `_a` |
| 系统 | `TB128FU_CN_OPEN_USER_Q00126_T_ZUI_15.0.619_ST_240531`（Android 13） |
| 内核源码 | 社区 4.19.325 树：`Roynas-Android-Playground/kernel_lenovo_tb128fu` @ `e26c9a738` |
| 内核配置 | 原厂 `arch/arm64/configs/grass-perf_defconfig` |
| 工具链 | AOSP clang 12.0.5（r416183b） |
| KernelSU-Next | `legacy` @ `0b17f242`（`v3.4.0-legacy`，tag 之后第 21 个提交） |
| SUSFS | 内核侧 v2.3.0 NON-GKI；用户态模块 v2.3.0-R28 |
| 管理器 | 官方 v3.4.2（33355-5），内核上报 KSU version `33316-5`（UAPI 5） |
| Hook 模式 | **manual hook**（`CONFIG_KSU_MANUAL_HOOK=y`），kprobe / syscall-table 均关闭 |

内核实际版本串：`4.19.325-cip135-st19-Grass-perf+`

## 仓库内容

```
patches/
  ksu-next/
    0001-manual-sucompat-retry-uapi5.diff        # 70f14520：manual sucompat + su 修复 + UAPI 5
    0002-susfs-v2.3.0-legacy-integration.diff    # a4ba4598：SUSFS 接入 legacy supercall
    combined.diff                                # 以上两个的合并 diff
  kernel/
    0001-manual-hook-integration.patch           # c7b497dde：manual hook 插桩 + KSU 构建接入
    0002-susfs-v2.3.0-non-gki.patch              # 17e51f96f：SUSFS v2.3.0 4.19 非 GKI 移植
    0003-bt-revert-geni-uart-pm.patch            # b3f6249be：可选，与 KSU 无关的蓝牙修复尝试
    combined.diff
  build-compat/
    engine.h                                     # OpenSSL 3.5 主机工具兼容 stub
docs/
  hook-points.md    # 每个插桩点的位置与调用约定
  build.md          # 编译、配置校验、boot 重打包
  validation.md     # 上机测试命令与实测结果
  pitfalls.md       # 踩过的坑
tools/
  verify_boot.py    # 重打包 boot 的校验脚本（尺寸/段/cmdline）
```

## 快速上手

```bash
# 1. KSU 侧：legacy 基线 + 补丁
git clone https://github.com/KernelSU-Next/KernelSU-Next.git ksu_next
git -C ksu_next checkout 0b17f242
git -C ksu_next apply /path/to/patches/ksu-next/combined.diff

# 2. 内核侧：社区 4.19.325 基线 + 补丁
git clone https://github.com/Roynas-Android-Playground/kernel_lenovo_tb128fu.git kernel
git -C kernel checkout e26c9a738
git -C kernel apply /path/to/patches/kernel/0001-manual-hook-integration.patch
git -C kernel apply /path/to/patches/kernel/0002-susfs-v2.3.0-non-gki.patch
# 可选：蓝牙回滚尝试（0003），与 KSU 无关
# git -C kernel apply /path/to/patches/kernel/0003-bt-revert-geni-uart-pm.patch

# 3. 把 KSU 源码挂进内核树（构建脚本依赖这个相对链接）
cd kernel
ln -sfn ../../ksu_next/kernel drivers/kernelsu

# 4. 宿主机 OpenSSL 3.x 兼容 stub（只用 sign-file/extract-cert 的编译）
mkdir -p scripts/openssl-stub/openssl
cp /path/to/patches/build-compat/engine.h scripts/openssl-stub/openssl/engine.h

# 5. 用原厂 grass-perf_defconfig 编译 Image.gz（工具链、配置与打包见 docs/build.md）
```

只想接 KSU、不要 SUSFS 时：KSU 侧只应用 `0001`，内核侧只应用 `0001`。

## 关键改动

### KernelSU 侧（`ksu_next/`，相对 `0b17f242`，+497 / −32）

- `feature/sucompat.c`：新增 manual 入口
  `ksu_handle_execve_sucompat_manual(&filename, argv, execveat, fd, flags)`，让 `fs/exec.c` 的
  syscall 入口直接调用，不再依赖 `pt_regs`。
- **su 偶发失败修复**：manual hook 在正常进程上下文执行时，filename 页可能尚未驻留，
  `strncpy_from_user_nofault()` 返回 `-EFAULT`；旧代码只在 `preempt_count()!=0` 时改用会触发
  缺页的读取，于是 fork 出的子进程 `exec su` 被静默跳过，VFS 报 `ENOENT`。现在补上
  `!in_atomic() && !irqs_disabled() && !pagefault_disabled()` 时的 `strncpy_from_user()` 重试。
- `uapi/supercall.h`：`KERNEL_SU_UAPI_VERSION` 由 6 改为 **5**，与官方 v3.4.2 管理器对齐；
  v6 新增的 `KSU_IOCTL_LOOKUP_SYMBOLS` / `KSU_GET_INFO_FLAG_PREINIT` 管理器并不使用。
- `kernel/core/init.c`：`ksu_debug_log()` 与 `/proc/ksu_debug`（8 KB 环形缓冲，整行淘汰）。
- `kernel/hook/patch_memory.c`：4.19.325 厂商树已回移 `copy_to_kernel_nofault()`，避免被
  版本宏错误替换成 `probe_kernel_write()`。
- 其余为 legacy 分支的本地修复：`throne_tracker` / `pkg_observer` / `ksud_integration` /
  `boot_event` / LSM setuid fd 安装 / syscall-table hook 编译兼容。
- SUSFS 集成见 `0002`：`Kconfig` 菜单、`susfs_init()`、setuid hook 的 extra work 与 umounted
  标记、SELinux SID 缓存、`SUSFS_MAGIC` 的 15 个 `CMD_SUSFS_*`（经 manual reboot hook 进入）、
  boot-completed 时的 sdcard monitor。

### 内核侧（相对 `e26c9a738`，+3541 / −114）

- **manual hook 插桩**（`0001`）：`fs/exec.c`、`fs/open.c`、`fs/stat.c`、`fs/read_write.c`、
  `drivers/input/input.c`、`kernel/reboot.c`，外加 `fs/namespace.c` 的 `path_umount()`、
  `include/linux/seccomp.h` 的 `filter_count`、clang 12 与 OpenSSL 3.5 的构建兼容。
  逐点说明见 [`docs/hook-points.md`](docs/hook-points.md)。
- **SUSFS v2.3.0 NON-GKI**（`0002`）：新增 `fs/susfs.c`、`include/linux/susfs.h`、
  `include/linux/susfs_def.h`，改动 `namei` / `namespace` / `readdir` / `stat` / `statfs` /
  `proc` / `super` / `mm` / `selinux/avc` / `kallsyms` 等，并追加 10 个 `CONFIG_KSU_SUSFS*`。
- **蓝牙回滚**（`0003`，可选）：回滚社区 `cef2c316` 的 GENI UART runtime PM 改动。与本仓库的
  KSU 工作无关，但社区 4.19.325 树上开启蓝牙会触发 CrashDump，需要一并评估（见
  [`docs/pitfalls.md`](docs/pitfalls.md)）。

## 实测结果（2026-10-25）

- 管理器 v3.4.2 首页：Working / Manual / 内核 `33316-5` / SuFS `v2.3.0 (NON-GKI)`，无警告卡片。
- `su -c id` → `uid=0(root) … context=u:r:ksu:s0`；直接调用、fork 子进程、脚本内调用、
  连续 20 次调用全部成功。
- SUSFS 隐藏：`add_sus_path` 后普通 app uid 访问返回 `No such file or directory`，root 仍可见。
- 详细命令与输出见 [`docs/validation.md`](docs/validation.md)。

## 已知坑（摘要）

| 症状 | 原因 / 处理 |
|---|---|
| shell 里 `su` 被拒 | boot cmdline 缺 `kernelsu.allow_shell=1` |
| fork 出的子进程 `exec su` 报 ENOENT | manual sucompat 缺进程上下文重试（本仓库已修） |
| 管理器提示 UAPI 版本不匹配 | `KERNEL_SU_UAPI_VERSION` 未改为 5 |
| 管理器报“不支持非 GKI 内核” | 用了 syscall-table hook；必须用 manual hook |
| fd 被安装两次 | 在 `kernel/sys.c` 重复插桩 setuid（应只走 LSM `task_fix_setuid`） |
| 刷入后无法开机 | boot 镜像尺寸不是 100663296 字节 / cmdline 未 NUL 结尾 |

完整清单见 [`docs/pitfalls.md`](docs/pitfalls.md)。

## 许可与致谢

- 根目录 `LICENSE` 为 **GPL-3.0**（取自 KernelSU-Next），适用于本仓库的文档、工具与
  `patches/ksu-next/`。
- `patches/kernel/` 直接修改 Linux 4.19 源码，按内核许可以 **GPL-2.0 only** 提供；
  SUSFS 内核代码同样来自 GPL-2.0 的 susfs4ksu。
- 两侧许可不同是上游现状（KernelSU-Next 为 GPL-3.0，Linux 为 GPL-2.0-only），补丁按各自的
  上游条款分发；使用前请自行确认这对你的分发方式意味着什么。
- [KernelSU-Next](https://github.com/KernelSU-Next/KernelSU-Next)（GPL-3.0），legacy 分支；
  preinit 机制来自 [tiann/KernelSU#3907](https://github.com/tiann/KernelSU/pull/3907)。
- [simonpunk/susfs4ksu](https://github.com/simonpunk/susfs4ksu) 的 SUSFS v2.3.0，内核侧 4.19
  补丁参考 [JackA1ltman/NonGKI_Kernel_Build_2nd](https://github.com/JackA1ltman/NonGKI_Kernel_Build_2nd)，
  KSU 侧集成参考
  [wshamroukh/KernelSU-Next-SUSFS-kernelv4.19](https://github.com/wshamroukh/KernelSU-Next-SUSFS-kernelv4.19)。
- 用户态模块 [sidex15/susfs4ksu-module](https://github.com/sidex15/susfs4ksu-module) R28。
- 社区内核树
  [Roynas-Android-Playground/kernel_lenovo_tb128fu](https://github.com/Roynas-Android-Playground/kernel_lenovo_tb128fu)。

本仓库不包含联想原厂固件、boot 镜像或管理器 APK；请从各自官方渠道获取。修改 boot 镜像、
关闭 verity 都存在变砖风险，操作前务必备份原厂镜像并确认救砖路径。
