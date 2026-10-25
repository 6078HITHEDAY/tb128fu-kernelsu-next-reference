# 构建与打包

## 源码布局

```
project/
  kernel/            # 社区 4.19.325 树（Roynas-Android-Playground/kernel_lenovo_tb128fu）
  ksu_next/          # KernelSU-Next legacy
  toolchain/         # AOSP clang 12.0.5 (r416183b)
```

内核树里需要两个相对符号链接：

```bash
cd kernel
ln -sfn ../toolchain toolchain              # 工具链
ln -sfn ../../ksu_next/kernel drivers/kernelsu   # KSU 源码（含 Kconfig/Makefile）
```

`drivers/kernelsu` 必须放在 `drivers/` 下：`drivers/Kconfig` 和 `drivers/Makefile` 的接入行是补丁加的，
但源码本身通过链接提供，不复制进内核树。

## defconfig

补丁在 `arch/arm64/configs/grass-perf_defconfig` 末尾追加：

```
CONFIG_KSU=y
CONFIG_KSU_MANUAL_HOOK=y
# CONFIG_KSU_SYSCALL_TABLE_HOOK is not set
# CONFIG_KSU_KPROBES_HOOK is not set
# CONFIG_KPROBES is not set

CONFIG_KSU_SUSFS=y
CONFIG_KSU_SUSFS_SUS_PATH=y
CONFIG_KSU_SUSFS_SUS_MOUNT=y
CONFIG_KSU_SUSFS_SUS_KSTAT=y
CONFIG_KSU_SUSFS_SPOOF_UNAME=y
CONFIG_KSU_SUSFS_ENABLE_LOG=y
CONFIG_KSU_SUSFS_HIDE_KSU_SUSFS_SYMBOLS=y
CONFIG_KSU_SUSFS_SPOOF_CMDLINE_OR_BOOTCONFIG=y
CONFIG_KSU_SUSFS_OPEN_REDIRECT=y
CONFIG_KSU_SUSFS_SUS_MAP=y
```

`KPROBES` 必须关闭：本树没有可用的 kprobe hook，开着只会增加攻击面。syscall-table hook
在非 GKI 设备上会被管理器判定为不支持。

## 编译

本项目使用本地封装脚本 `kernel/build_kernel.py`（**未收录**，属作者本机工作流）。它做的事是：

1. 以 `grass-perf_defconfig` 生成 `.config`；
2. 调用 `make` 编译 `Image.gz`；
3. 生成 KSU 需要的 UAPI 头（依赖 `ksu_next/uapi/`）；
4. 顺带写 `AnyKernel3/Image` 和 `GrassKernel_<日期>.zip` —— 这些不是最终交付物，构建前注意保护。

`LTO` / `DEBUG_INFO` / `MODULE_SIG` 的最终取值**以生成的 `out/.config` 和构建日志为准**，
不要假定脚本一定会改。本方案交付的配置里 `CONFIG_LTO=y`、`CONFIG_DEBUG_INFO=y`、
`CONFIG_MODULE_SIG_FORCE=y` 都保持原厂值，并未关闭；KSU 是内建驱动，不依赖外部模块签名。

调用方式：

```bash
cd kernel
PYTHONPATH=../kbuild_common python3 build_kernel.py
```

脚本会**删除并重建 `kernel/out/`**，需要留存的 `.config` 和日志先复制出去。

不用封装脚本时，可以用等价的 `make` 流程（本项目未以此路径验证，配置结论相同）：

```bash
cd kernel
make ARCH=arm64 O=out CC="$TC/bin/clang" \
     CLANG_TRIPLE=aarch64-linux-gnu- CROSS_COMPILE=aarch64-linux-gnu- \
     grass-perf_defconfig
make ARCH=arm64 O=out CC="$TC/bin/clang" \
     CLANG_TRIPLE=aarch64-linux-gnu- CROSS_COMPILE=aarch64-linux-gnu- \
     -j"$(nproc)" Image.gz
```

## 配置与日志校验

```bash
grep -E '^CONFIG_KSU|^# CONFIG_KSU|^# CONFIG_KPROBES' out/.config
grep -E 'CONFIG_MODULE_SIG|CONFIG_LTO|CONFIG_DEBUG_INFO=' out/.config
```

期望至少包含：

```
CONFIG_KSU=y
CONFIG_KSU_MANUAL_HOOK=y
# CONFIG_KPROBES is not set
CONFIG_KSU_SUSFS=y
CONFIG_KSU_SUSFS_SUS_PATH=y
CONFIG_KSU_SUSFS_SUS_MOUNT=y
CONFIG_KSU_SUSFS_SUS_KSTAT=y
CONFIG_KSU_SUSFS_SPOOF_UNAME=y
CONFIG_KSU_SUSFS_ENABLE_LOG=y
CONFIG_KSU_SUSFS_HIDE_KSU_SUSFS_SYMBOLS=y
CONFIG_KSU_SUSFS_SPOOF_CMDLINE_OR_BOOTCONFIG=y
CONFIG_KSU_SUSFS_OPEN_REDIRECT=y
CONFIG_KSU_SUSFS_SUS_MAP=y
```

注意：defconfig 里那两行 `# CONFIG_KSU_SYSCALL_TABLE_HOOK is not set` /
`# CONFIG_KSU_KPROBES_HOOK is not set` 在 `KSU_MANUAL_HOOK=y` 时属于被 Kconfig 隐藏的
`choice` 分支（`depends on !KSU_MANUAL_HOOK`），**不会出现在最终 `.config`**，这是正常的。
判断 hook 模式只看 `CONFIG_KSU_MANUAL_HOOK=y` 和 `# CONFIG_KPROBES is not set`。

再确认构建日志里有 `preinit enabled`。preinit 依赖 `ksu_next/uapi/`；如果给编译加了
`-DKSU_NO_PREINIT`，preinit 会被静默关掉，管理器功能不受影响，但模块的 preinit 动作不会执行。

交付配置里 LTO、`DEBUG_INFO`、`MODULE_SIG`（含 `MODULE_SIG_FORCE`）都保持原厂开启状态，
这不是问题：KSU 以 `CONFIG_KSU=y` 内建，WiFi/音频/显示/触摸等关键驱动同样内建，启动过程
不加载外部 `.ko`。只有需要加载自编外部模块时，才要单独处理签名与 vermagic。

## 重新打包 boot

原厂 boot 头是 **header v2 / page_size 4096**，boot 分区 **100663296 字节（96 MiB）**。
重打包只替换内核段，ramdisk 保持原样：

1. 复制原厂 `boot.img` 的 header 与 ramdisk；
2. 写入新的 `Image.gz`，按 page_size 重新对齐各段偏移；
3. 更新 header offset 8 的 `kernel_size`；
4. **在 cmdline 末尾追加 ` kernelsu.allow_shell=1`**；
5. 补零到分区大小。

cmdline 在 header 的 offset 64、长 512 字节，必须 NUL 结尾：

```python
from pathlib import Path

p = Path("work/new-boot.img")
d = bytearray(p.read_bytes())
cmd = d[64:576].split(b"\0", 1)[0]
if b"kernelsu.allow_shell=1" not in cmd.split():
    cmd += b" kernelsu.allow_shell=1"
assert len(cmd) < 512
d[64:576] = cmd + b"\0" * (512 - len(cmd))
p.write_bytes(d)
```

`kernelsu.allow_shell=1` 不能省：非 `CONFIG_KSU_DEBUG` 配置下 `allow_shell` 默认 `false`，
shell（UID 2000）发起的 `su` 会被直接拒绝，只有管理器授权的 App 能拿到 root。

## 校验

仓库自带 [`tools/verify_boot.py`](../tools/verify_boot.py)：

```bash
python3 tools/verify_boot.py new-boot.img \
  --stock boot.img \
  --kernel Image.gz \
  --partition-size 100663296
```

它会检查文件尺寸、页大小、内核段与 `Image.gz` 是否逐字节一致、ramdisk 是否与原厂完全一致、
cmdline 是否以原厂 cmdline 为前缀且带 `allow_shell=1`、以及是否 NUL 结尾。
全部通过时会打印镜像 sha256，可直接和交付记录比对。

## 刷入与回滚

```bash
adb reboot bootloader
fastboot getvar unlocked          # 必须 yes
fastboot --disable-verity --disable-verification flash vbmeta_a vbmeta.img
fastboot --disable-verity --disable-verification flash vbmeta_b vbmeta.img
fastboot flash boot_a new-boot.img
fastboot flash boot_b new-boot.img
fastboot reboot
```

两个槽都刷，避免切槽后失效。回滚就是把原厂 `boot.img` / `vbmeta.img` 刷回两个槽；
进不了 fastboot 时走 9008 + QFIL 包。**不要单独刷 `abl.elf`**。

首次开机可能较慢（新内核 + dex2oat），留 5–10 分钟。
