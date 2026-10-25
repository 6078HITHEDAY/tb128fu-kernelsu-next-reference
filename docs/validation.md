# 上机验证记录

环境：Lenovo TB128FU（grass，SM6225），ZUI 15.0.619（Android 13），A/B 当前 `_a`，
内核 `4.19.325-cip135-st19-Grass-perf+`，KernelSU-Next `v3.4.0-legacy`，SUSFS v2.3.0 NON-GKI。
验证日期：2026-10-25（r10，manual hook + SUSFS）。

## 管理器

安装官方 v3.4.2 release（内核内置了管理器签名哈希，第三方重签的 APK 不会被 crown）：

<https://github.com/KernelSU-Next/KernelSU-Next/releases/download/v3.4.2/KernelSU_Next_v3.4.2_33355-release.apk>

打开后应显示：

| 项 | 期望值 |
|---|---|
| 状态 | Working |
| Hook | Manual |
| 内核版本 | `33316-5` |
| SuFS | `v2.3.0 (NON-GKI)` |
| 警告卡片 | 无 |

`33316-5` 的后缀是 git 提交偏移（UAPI 5）；本方案在 `0b17f242` 之上加了两个提交，所以从
`33315` 变成 `33316`，功能无关。

## su

```bash
adb shell 'su -c id'                        # uid=0(root) … context=u:r:ksu:s0
adb shell 'su -c id; echo rc=$?; true'      # fork 场景，rc=0
adb shell 'echo x; su -c id'                # 连续调用
adb shell 'su 0 id'                         # uid 形式
```

脚本场景需要一个包含 `su -c id` 的脚本：

```bash
adb shell 'mkdir -p /data/local/tmp'
adb shell 'printf "#!/system/bin/sh\nsu -c id\n" > /data/local/tmp/t.sh'
adb shell 'chmod 755 /data/local/tmp/t.sh'
adb shell 'sh /data/local/tmp/t.sh'
```

实测：直接调用、fork 子进程、脚本内调用、连续 20 次调用全部返回
`uid=0(root) … context=u:r:ksu:s0`。root 的 SELinux 上下文是 `u:r:ksu:s0`，不是 `u:r:su:s0`。

## 内核调试日志

```bash
adb shell 'su 0 cat /proc/ksu_debug'
```

`/proc/ksu_debug` 是 8 KB 环形缓冲，按完整旧行淘汰，保留最新日志。注意：shell（`u:r:shell:s0`）
直接读取会被 SELinux 拒绝，必须经由 `su`。

## SUSFS

模块 `SUSFS-FOR-KERNELSU v2.3.0-R28` 安装后：

```bash
adb shell 'su -c "/data/adb/ksu/bin/ksu_susfs show version"'           # v2.3.0
adb shell 'su -c "/data/adb/ksu/bin/ksu_susfs show variant"'           # NON-GKI
adb shell 'su -c "/data/adb/ksu/bin/ksu_susfs show enabled_features"'  # 9 项
```

隐藏功能：

```bash
# root 下添加
adb shell 'su -c "/data/adb/ksu/bin/ksu_susfs add_sus_path /data/local/tmp/susfs_test"'

# 普通 app uid 访问 → No such file or directory
adb shell 'su 10100 -c "ls /data/local/tmp/susfs_test"'

# root 访问 → 正常列出
adb shell 'su -c "ls /data/local/tmp/susfs_test"'
```

`add_sus_path` 是内存态，重启失效。要持久化就写进
`/data/adb/susfs4ksu/sus_path.txt`，或使用模块 WebUI（管理器 → 模块 → SUSFS）。

## 结果汇总

| 项目 | 结果 |
|---|---|
| 管理器状态 / Hook | Working / Manual，无警告 |
| `su -c id` | 通过，`u:r:ksu:s0` |
| fork 子进程 exec su | 通过（依赖进程上下文重试修复） |
| 脚本内调用 | 通过 |
| 连续 20 次调用 | 通过 |
| SUSFS version / variant | v2.3.0 / NON-GKI |
| `add_sus_path` 隐藏 | 普通 uid `ENOENT`，root 可见 |
| 开机 / 日常使用 | 正常；社区 4.19.325 树的蓝牙问题见 pitfalls |

> 本记录来自当时的单机实测，不构成对其他批次/其他系统版本的保证。原厂系统版本为
> `TB128FU_CN_OPEN_USER_Q00126_T_ZUI_15.0.619_ST_240531`。
