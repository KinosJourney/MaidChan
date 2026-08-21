# Maid-chan macOS 打包与更新流程

本文档用于将当前源码打包成可从 macOS Spotlight（聚焦搜索）启动的
`Maid-chan.app`。

## 一、平时修改和测试

开发过程中不需要每次都打包。在项目目录运行源码即可：

```bash
./run.command
```

也可以在已激活虚拟环境的终端运行：

```bash
python oc.py
```

确认功能修改完成、准备使用 Spotlight 启动最新版时，再执行下面的打包流程。

## 二、首次准备环境

在项目目录运行：

```bash
./install.command
```

该脚本会创建 `.venv` 并安装 PySide6、PyInstaller 等依赖。通常只需执行一次；
修改普通 Python 代码时不用重新安装依赖。

## 三、推荐：Push 后自动打包并替换

先提交全部修改，然后不要直接运行 `git push`，改为：

```bash
bash ./push-and-package.sh
```

脚本会依次执行：

1. 检查工作区是否干净，避免打包未提交的代码；
2. Push 当前分支；
3. Push 成功后打包 `Maid-chan.app`；
4. 验证新应用签名；
5. 安全替换 `~/Applications/Maid-chan.app`；
6. 更新 Spotlight 索引并启动最新版。

如果 Push 或打包失败，已安装的旧版本不会被替换。需要指定远端或分支时，
可以像 `git push` 一样传入参数：

```bash
bash ./push-and-package.sh origin main
```

> Git 本身没有客户端 `post-push` 钩子，因此以后需要用这个脚本代替直接执行
> `git push`，才能确保 Push 成功后自动打包。

## 四、手动重新打包

先从桌宠右键菜单选择“退出”，避免旧版本仍在运行，然后在项目目录执行：

```bash
PYINSTALLER_CONFIG_DIR="$PWD/.pyinstaller-cache" bash ./pack.command
```

使用项目内的独立 PyInstaller 缓存，可以避免系统缓存损坏导致打包失败。

成功后会生成：

- `dist/Maid-chan.app`：可以直接运行的 macOS 应用；
- `dist/Maid-chan-macOS.zip`：用于备份或分发的压缩包。

## 五、安装或更新应用

### 使用 Finder

1. 打开项目中的 `dist` 文件夹；
2. 将 `Maid-chan.app` 复制到当前用户主目录下的“应用程序”文件夹；
3. 如果已有旧版本，选择“替换”。

目标路径是：

```text
~/Applications/Maid-chan.app
```

### 使用终端

首次安装：

```bash
mkdir -p "$HOME/Applications"
ditto "dist/Maid-chan.app" "$HOME/Applications/Maid-chan.app"
mdimport "$HOME/Applications/Maid-chan.app"
```

更新时建议先删除旧应用，再复制新应用，避免旧文件残留：

```bash
rm -rf "$HOME/Applications/Maid-chan.app"
ditto "dist/Maid-chan.app" "$HOME/Applications/Maid-chan.app"
mdimport "$HOME/Applications/Maid-chan.app"
```

安装后按 `Command + 空格`，搜索 `Maid-chan` 即可启动。

## 六、API 配置和用户数据

本机已经配置过 API Key 时，重新打包和替换应用不需要再次配置。

安装版从以下私有文件读取 `.env`：

```text
~/Library/Application Support/MaidChan/.env
```

在新 Mac 上首次安装时，可将项目中的 `.env` 安全复制过去：

```bash
mkdir -p "$HOME/Library/Application Support/MaidChan"
install -m 600 ".env" "$HOME/Library/Application Support/MaidChan/.env"
```

不要将真实 `.env` 放入压缩包、提交到 Git 或发送给其他人。

聊天记录、设置、档案、待办和番茄钟数据也位于：

```text
~/Library/Application Support/MaidChan/
```

因此重新打包、删除旧 `.app` 或安装新版本不会清除这些数据。

## 七、哪些修改需要重新打包

需要重新打包：

- 修改 `maidchan/` 或 `oc.py` 中的 Python 代码；
- 修改 `pic/` 中的角色图片或应用图标；
- 修改打包到应用内的 `readme.md`；
- 新增、删除或升级 Python 依赖。

不需要重新打包：

- 修改用户设置、档案、待办或聊天记录；
- 仅修改用户数据目录中的 `.env`；
- 开发阶段只想运行和测试源码。

## 八、验证安装结果

检查 Spotlight 是否已经索引：

```bash
mdfind "kMDItemFSName == 'Maid-chan.app'"
```

正常情况下应看到：

```text
/Users/你的用户名/Applications/Maid-chan.app
```

也可以直接启动：

```bash
open "$HOME/Applications/Maid-chan.app"
```

## 九、常见问题

### Spotlight 搜到的还是旧版本

先彻底退出正在运行的 Maid-chan，确认已经用新生成的
`dist/Maid-chan.app` 替换旧应用，然后重新执行：

```bash
mdimport "$HOME/Applications/Maid-chan.app"
```

### macOS 提示无法验证开发者

在 Finder 中右键 `Maid-chan.app`，选择“打开”，然后再次确认“打开”。

### 打包时出现 PyInstaller 缓存错误

使用本文第四节带 `PYINSTALLER_CONFIG_DIR` 的命令重新打包，不要直接复用损坏的
系统缓存。

### 换到另一台 Mac 无法运行

当前打包产物通常只保证兼容打包它的 Mac 架构。Intel Mac 和 Apple Silicon Mac
之间分发时，建议在目标架构的 Mac 上分别打包。
