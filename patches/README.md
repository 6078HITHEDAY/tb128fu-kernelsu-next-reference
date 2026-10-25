# 补丁清单

所有补丁都用 `git diff` 从实际提交导出，**不含作者信息与时间戳**，可直接 `git apply`。

许可：`ksu-next/` 的补丁衍生自 KernelSU-Next（GPL-3.0）；`kernel/` 的补丁修改 Linux 4.19
源码，按 GPL-2.0 only 提供，其中的 SUSFS 代码来自 GPL-2.0 的 susfs4ksu。

## KernelSU 侧

基线：`KernelSU-Next/KernelSU-Next` `legacy` @ `0b17f242`
（`v3.4.0-legacy` tag 之后第 21 个提交）。

| 补丁 | 内容 | 目标树 |
|---|---|---|
| `ksu-next/0001-manual-sucompat-retry-uapi5.diff` | manual sucompat 入口、进程上下文重试、UAPI 6→5、`/proc/ksu_debug`、legacy 本地修复 | `70f14520` |
| `ksu-next/0002-susfs-v2.3.0-legacy-integration.diff` | SUSFS v2.3.0 接入 legacy supercall | `a4ba4598` |
| `ksu-next/combined.diff` | 以上两个合并 | `a4ba4598` |

```bash
git clone https://github.com/KernelSU-Next/KernelSU-Next.git ksu_next
git -C ksu_next checkout 0b17f242
git -C ksu_next apply /path/to/patches/ksu-next/combined.diff
```

## 内核侧

基线：`Roynas-Android-Playground/kernel_lenovo_tb128fu` `master` @ `e26c9a738`。

| 补丁 | 内容 | 目标树 |
|---|---|---|
| `kernel/0001-manual-hook-integration.patch` | manual hook 插桩、`path_umount()`、seccomp/compiler/openssl 构建兼容、defconfig | `c7b497dde` |
| `kernel/0002-susfs-v2.3.0-non-gki.patch` | SUSFS v2.3.0 4.19 非 GKI 移植 + defconfig | `17e51f96f` |
| `kernel/0003-bt-revert-geni-uart-pm.patch` | **可选**，回滚社区 `cef2c316`，蓝牙问题尝试性修复 | `b3f6249be` |
| `kernel/combined.diff` | 三个合并（含可选补丁） | `b3f6249be` |

```bash
git clone https://github.com/Roynas-Android-Playground/kernel_lenovo_tb128fu.git kernel
git -C kernel checkout e26c9a738
git -C kernel apply /path/to/patches/kernel/0001-manual-hook-integration.patch
git -C kernel apply /path/to/patches/kernel/0002-susfs-v2.3.0-non-gki.patch
# 可选
git -C kernel apply /path/to/patches/kernel/0003-bt-revert-geni-uart-pm.patch
```

`0001` 里的 `scripts/Makefile` 改动会引用 `scripts/openssl-stub/`，这个目录不在 git 里，
需要手动放好：

```bash
mkdir -p kernel/scripts/openssl-stub/openssl
cp /path/to/patches/build-compat/engine.h kernel/scripts/openssl-stub/openssl/engine.h
```

它只影响宿主机上的 `sign-file` / `extract-cert`（OpenSSL 3.x 的 `engine.h` 兼容），
不影响目标内核。模块签名已关闭，用不到时可以连同 `scripts/Makefile` 的两行一起跳过。

## 校验

补丁已用「临时 index」验证过：逐级应用后 `write-tree` 的结果与目标提交的 tree 完全一致，
说明补丁没有丢 hunk、没有漂移。可自行复现：

```bash
export GIT_INDEX_FILE=$(mktemp)
git -C ksu_next read-tree 0b17f242
git -C ksu_next apply --cached --check patches/ksu-next/0001-manual-sucompat-retry-uapi5.diff
git -C ksu_next apply --cached        patches/ksu-next/0001-manual-sucompat-retry-uapi5.diff
git -C ksu_next apply --cached        patches/ksu-next/0002-susfs-v2.3.0-legacy-integration.diff
git -C ksu_next write-tree            # 应为 697129947f8dc22482264950b637e0494c9477ea
```

内核侧同样操作，最终 tree 应为 `2aefc8684e522d30ca182b362e98b5c304191ec0`。

## 文件校验值

```
186f74f6e647f84b130e03e8bc36c9c952207038f764b86a5e2299d7de51cd43  ksu-next/0001-manual-sucompat-retry-uapi5.diff
e7f19bfbf414b4cd94e795ecfbaa5f52a464468ecda0e2f3f112bc3dd38b0a80  ksu-next/0002-susfs-v2.3.0-legacy-integration.diff
037b3c6700a2fcef7c507e860d665bff8fcb4469737adeaf7afc04adabcdbc8d  ksu-next/combined.diff
987b02137a5ea4737b34202cf9c801da32873ba8a8962ead8df72b3c8365450e  kernel/0001-manual-hook-integration.patch
4c146871a895af2f8b375ab88553bd81c4bb623461dcd44138c5402f152559bc  kernel/0002-susfs-v2.3.0-non-gki.patch
51c36efe759fce715757e75d183528c27f40eadeb5b2b3356213ecdbdc68d86e  kernel/0003-bt-revert-geni-uart-pm.patch
63f0419dc8e47aa4eb7f6faf6deca76b7172fd755daa6f81292d17debdc1d5b4  kernel/combined.diff
de3d8eac3e193da0015b013e45eecc605faa9ec30c07c12c8bccc7dec7272fcc  build-compat/engine.h
```

## 生成方式

```bash
git -C ksu_next diff 0b17f242..70f14520 > ksu-next/0001-manual-sucompat-retry-uapi5.diff
git -C ksu_next diff 70f14520..a4ba4598 > ksu-next/0002-susfs-v2.3.0-legacy-integration.diff
git -C kernel   diff e26c9a738..c7b497dde  > kernel/0001-manual-hook-integration.patch
git -C kernel   diff c7b497dde..17e51f96f  > kernel/0002-susfs-v2.3.0-non-gki.patch
git -C kernel   diff 17e51f96f..b3f6249be  > kernel/0003-bt-revert-geni-uart-pm.patch
```

使用中文注释与文档，补丁内容保持原样。
