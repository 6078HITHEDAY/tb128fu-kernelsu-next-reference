# Manual hook 插桩点

`CONFIG_KSU_MANUAL_HOOK=y` 时内核不会自动挂 hook，所有入口都要在源码里显式调用。
以下位置对应 `patches/kernel/0001-manual-hook-integration.patch`。

约定：每个插桩块都包在 `#if defined(CONFIG_KSU) && defined(CONFIG_KSU_MANUAL_HOOK)` 里，
所以关掉 KSU 后这些调用完全消失，不会留下悬空符号。

## 内核侧

| 文件 / 函数 | 调用 | 说明 |
|---|---|---|
| `fs/exec.c` `SYSCALL_DEFINE3(execve)` | `ksu_handle_execve_ksud(filename, argv)`<br>`ksu_handle_execve_sucompat_manual(&filename, argv, false, AT_FDCWD, 0)` | 两个入口都必须调用：ksud 负责管理器/模块路径，sucompat 负责 `su` |
| `fs/exec.c` `SYSCALL_DEFINE5(execveat)` | 同上，`execveat=true` 并传 `fd, flags` | 只在 `fd == AT_FDCWD && flags == 0` 时插桩 |
| `fs/exec.c` `COMPAT_SYSCALL_DEFINE3(execve)` | `ksu_handle_compat_execve_ksud(filename, argv)`<br>`ksu_handle_execve_sucompat_manual(&filename, NULL, …)` | 32 位进程；compat 的 argv 类型不同，sucompat 传 `NULL` |
| `fs/exec.c` `COMPAT_SYSCALL_DEFINE5(execveat)` | 同上 | 同样只在 `fd == AT_FDCWD && flags == 0` 时插桩 |
| `fs/open.c` `SYSCALL_DEFINE3(faccessat)` | `ksu_handle_faccessat(&dfd, &filename, &mode, NULL)` | 用于拦截对 manager 路径的探测 |
| `fs/stat.c` `SYSCALL_DEFINE4(newfstatat)` | `ksu_handle_stat(&dfd, &filename, &flag)` | 原生 |
| `fs/stat.c` `SYSCALL_DEFINE4(fstatat64)` | 同上 | 4.19 树里单独存在，**不要漏** |
| `fs/stat.c` `COMPAT_SYSCALL_DEFINE4(newfstatat)` | 先转成 `int ksu_dfd`，调用后写回 `dfd` | compat 入口的 dfd 是 `unsigned int` |
| `fs/read_write.c` `SYSCALL_DEFINE3(read)` | `if (unlikely(ksu_init_rc_hook)) ksu_handle_sys_read(fd)` | 只服务于 init.rc 注入，开关关闭时近零开销 |
| `drivers/input/input.c` `input_event()` | `if (unlikely(ksu_input_hook)) ksu_handle_input_handle_event(&type, &code, &value)` | 音量键触发管理器入口 |
| `kernel/reboot.c` `SYSCALL_DEFINE4(reboot)` | `ksu_handle_sys_reboot(magic1, magic2, cmd, &arg)` | 同时承载 fd 安装与 SUSFS `CMD_SUSFS_*` |

### `kernel/reboot.c` 的声明顺序

该函数是 C89 风格：`struct pid_namespace *pid_ns = task_active_pid_ns(current);` 原本在声明区。
插桩要把 `pid_ns` 的赋值移到所有声明之后，否则 clang 在 `-Wdeclaration-after-statement` 下报警：

```c
struct pid_namespace *pid_ns;
char buffer[256];
int ret = 0;

pid_ns = task_active_pid_ns(current);

#if defined(CONFIG_KSU) && defined(CONFIG_KSU_MANUAL_HOOK)
	ksu_handle_sys_reboot(magic1, magic2, cmd, &arg);
#endif
```

### 不要做的事

- **不要在 `kernel/sys.c` 里加 setuid hook。** 4.19 上 setuid 由 LSM 的 `task_fix_setuid`
  （`ksu_next/kernel/hook/lsm_hooks.c` → `ksu_handle_setresuid()`）处理，再加一处会把
  manager 的 fd 安装两次。
- **不要切回 syscall-table hook。** 在非 GKI 4.19 上实测管理器直接报“不支持非 GKI 内核”；
  kprobe hook 在本树同样不可用（`CONFIG_KPROBES` 关闭）。

## 为 manual hook 补的内核辅助改动

| 改动 | 原因 |
|---|---|
| `fs/namespace.c`：新增 `can_umount()` / `path_umount()` | KSU 需要按 path 卸载（模块/overlay），4.19 没有这个辅助函数 |
| `include/linux/seccomp.h`：`struct seccomp` 增加 `atomic_t filter_count` | KSU 的 seccomp 相关兼容代码依赖该字段 |
| `include/linux/compiler-clang.h`：`__diagnose_as` 加 `__has_attribute` 保护 | AOSP clang 12.0.5 不认识该属性 |
| `scripts/Makefile` + `scripts/openssl-stub/openssl/engine.h` | Fedora/OpenSSL 3.5 主机上 `sign-file`/`extract-cert` 的编译兼容 |

## KernelSU 侧入口

`ksu_next/kernel/feature/sucompat.c` 中：

```c
long ksu_handle_execve_sucompat_manual(const char __user **filename_user,
				       const char __user *const __user *argv_user,
				       bool execveat, int fd, int flags);
```

它和 kprobe 路径共用 `ksu_handle_execve_sucompat_common()`，区别只是 syscall 参数由调用方直接传入，
不再从 `pt_regs` 里取。核心逻辑：

1. `strncpy_from_user_nofault()` 读 filename；
2. 读失败且处于正常进程上下文（`!in_atomic() && !irqs_disabled() && !pagefault_disabled()`）时，
   改用会触发缺页的 `strncpy_from_user()` 重试 —— **这一条是 fork 子进程 `su` 能用的关键**；
3. 命中 `/system/bin/su` 且 UID 允许时，替换 filename 为 ksud，并 `escape_with_root_profile()`。

SUSFS 的 `CMD_SUSFS_*` 不额外占用 hook 点：全部塞进 `reboot(2)` 的 `SUSFS_MAGIC` 分支，
由上面 `kernel/reboot.c` 的同一个插桩进入。
