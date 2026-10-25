# 踩过的坑

按出现频率排序。前四条是这套方案能不能跑起来的分水岭。

## 1. shell 里 `su` 被拒：缺 `kernelsu.allow_shell=1`

非 `CONFIG_KSU_DEBUG` 配置下，内核里 `allow_shell` 默认 `false`。shell（UID 2000）发起的 `su`
会被直接拒绝，只有管理器授权的 App 能用 root。

重打包只复制原厂 cmdline，所以必须自己追加：

```
console=... buildvariant=user kernelsu.allow_shell=1
```

cmdline 在 header offset 64、长 512 字节，追加后必须保证 NUL 结尾且不超长。
`tools/verify_boot.py` 会检查这一项。

## 2. fork 子进程 `exec su` 报 ENOENT

**症状**：`su -c id` 单独执行正常，但 `su -c id; echo $?`、脚本、app fork 出的子进程全部失败，
VFS 报 `No such file or directory`，看起来像 `su` 不存在。

**原因**：manual hook 在正常进程上下文中执行，filename 所在页可能尚未驻留。
`strncpy_from_user_nofault()` 不触发缺页，直接返回 `-EFAULT`，上游代码只在
`preempt_count()!=0`（kprobe 上下文）时才换用会缺页的读取。manual 路径不满足这个条件，
于是 sucompat 静默放弃，exec 继续按原 filename 走，得到 ENOENT。

**修复**（已包含在 `patches/ksu-next/`）：读失败且
`!in_atomic() && !irqs_disabled() && !pagefault_disabled()` 时，用 `strncpy_from_user()` 重试。
这条不能删，删了 fork 场景立刻复现。

## 3. 管理器显示 UAPI 版本警告

**症状**：管理器首页出现红色警告卡片：“管理器版本 5 过低 … 无法正常工作”。

**原因**：`ksu_next/uapi/supercall.h` 里 `KERNEL_SU_UAPI_VERSION = 6`，而官方最高版本的管理器
v3.4.2 只上报 5。管理器源码里这只是 `WarningCard`，不拦截任何功能。

**处理**：改成 5 重新编译。管理器本来就不会调用 v6 新增的 `KSU_IOCTL_LOOKUP_SYMBOLS` /
`KSU_GET_INFO_FLAG_PREINIT`，内核侧 preinit 逻辑也不受影响。以后换成支持 UAPI 6 的管理器，
把这一行改回 6 即可。

## 4. 管理器报“不支持非 GKI 内核”

**症状**：刷入后管理器显示不支持，`su` 全挂。

**原因**：用了 syscall-table hook 模式。这台设备的实测结论是：非 GKI 4.19 上必须用
**manual hook**。`CONFIG_KSU_SYSCALL_TABLE_HOOK` 和 `CONFIG_KSU_KPROBES_HOOK` 都不要开，
`CONFIG_KPROBES` 也保持关闭。

## 5. root fd 被安装两次

**症状**：setuid 相关行为异常，或管理器连接不稳定。

**原因**：在 `kernel/sys.c` 里额外加了 setuid hook。4.19 上 setuid 已经由 LSM 的
`task_fix_setuid`（`ksu_next/kernel/hook/lsm_hooks.c` → `ksu_handle_setresuid()`）处理，
重复插桩会让 fd 装两次。

**记法**：`kernel/sys.c` 在本方案里唯一的改动是 `newuname` 的 SUSFS uname 伪装，那**不是**
setuid hook。

## 6. MODULE_SIG 与外部模块

原厂 defconfig 开着 `CONFIG_MODULE_SIG` / `MODULE_SIG_FORCE`。本方案交付的配置**保持原样**，
内核照常启动：KSU 以 `CONFIG_KSU=y` 内建，WiFi/音频/显示/触摸等关键驱动也都内建，
启动过程不加载外部 `.ko`。原厂配置里只有 4 个非关键 `=m` 模块，因 vermagic 不同本来也不会加载。

不要为了 KSU 去关 `MODULE_SIG`。只有当你需要加载自编外部模块时，才要单独处理签名
（自签并注册公钥，或改配置但自行承担后果）。

## 7. boot 镜像校验失败

| 检查项 | 要求 |
|---|---|
| 文件大小 | 恰好 **100663296** 字节（96 MiB，boot 分区大小） |
| header | `ANDROID!`，header v2，page_size 4096 |
| offset 8 `kernel_size` | 等于新的 `Image.gz` 文件大小 |
| 内核段 | 与 `Image.gz` 逐字节一致 |
| ramdisk 段 | 与原厂逐字节一致 |
| cmdline | NUL 结尾，不超过 512 字节 |

尾部比较时排除分区末尾的零填充，不要直接按旧偏移比较整段。

## 8. 社区 4.19.325 树的蓝牙问题

社区 4.19.325 树上开启蓝牙会硬崩并进入 CrashDump。`patches/kernel/0003` 回滚了社区
`cef2c316` 的 GENI UART runtime PM 改动，作为**尝试性修复**，只做过编译与镜像校验，
**没有完成上机验证**，不能当作已解决处理。

项目后续换回原厂 4.19.157 内核，蓝牙实测正常，KSU 方案也随之停更（改用 APatch）。
如果你要在社区树上继续用这套 KSU，先确认蓝牙路径能接受。

## 9. SUSFS 的内核/用户态版本必须配套

- 内核侧 v2.3.0 → 用户态模块 `SUSFS-FOR-KERNELSU v2.3.0-R28`；
- 换 KSU 或内核版本要重新移植内核侧补丁，**不能**直接套 GKI 的 SUSFS LKM；
- 开启 `CONFIG_KSU_SUSFS_HIDE_KSU_SUSFS_SYMBOLS` 后，`/proc/kallsyms` 查不到 susfs 符号是正常的。

## 10. `add_sus_path` 重启失效

SUSFS 的路径隐藏是内存态。持久化方式：写 `/data/adb/susfs4ksu/sus_path.txt`，或用模块 WebUI。

## 11. 源码版本不是原厂版本

内核来自社区 **4.19.325** 树，原厂是 **4.19.157**。不是同一份源码，驱动行为（包括上面第 8 条）
存在差异。原厂 `grass-perf_defconfig` 能复用，但不代表其余代码等价。

## 12. 构建与刷机的副作用

- `build_kernel.py` 会删除并重建 `kernel/out/`；`.config` 和日志先复制出去。
- 脚本还会写 `kernel/AnyKernel3/Image` 和 `kernel/GrassKernel_<日期>.zip`，它们不是最终交付物。
- 关闭 AVB/verity 后 **OTA 会失败**；刷机前备份原厂 `boot.img` / `vbmeta.img`，确认 9008 + QFIL 救砖路径。

## 13. 其他

- `/proc/ksu_debug` 只能 root 读，shell 直接读会被 SELinux 拒绝（`su 0 cat` 可以）。
- 管理器必须用官方 release：内核内置了管理器签名哈希，第三方重签的 APK 不会被 crown。
- KernelSU-Next 非 GKI 属社区支持，出问题需要自己救砖。
