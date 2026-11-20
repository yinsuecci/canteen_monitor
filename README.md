# Canteen Monitor

**简体中文** · [English](README.en.md)

[![Python 3.12+](https://img.shields.io/badge/Python-3.12%2B-3776AB?logo=python&logoColor=white)](#环境准备)
[![Windows](https://img.shields.io/badge/Collector-Windows-0078D4?logo=windows&logoColor=white)](#数据采集)
[![Dashboard](https://img.shields.io/badge/Dashboard-React%20%2B%20TypeScript-3178C6?logo=typescript&logoColor=white)](#可视化面板)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![GitHub stars](https://img.shields.io/github/stars/yinsuecci/canteen_monitor?style=flat&logo=github)](https://github.com/yinsuecci/canteen_monitor/stargazers)
[![Download source ZIP](https://img.shields.io/badge/Download-Source%20ZIP-2563EB)](https://github.com/yinsuecci/canteen_monitor/archive/refs/heads/main.zip)

📣 **分享项目**
[![Share on X](https://img.shields.io/badge/X-Share-black?logo=x&logoColor=white)](https://x.com/intent/post?url=https%3A%2F%2Fgithub.com%2Fyinsuecci%2Fcanteen_monitor)
[![Share on Telegram](https://img.shields.io/badge/Telegram-Share-26A5E4?logo=telegram&logoColor=white)](https://t.me/share/url?url=https%3A%2F%2Fgithub.com%2Fyinsuecci%2Fcanteen_monitor)

## 🧭 项目目的

Canteen Monitor 是一个基于公共 Wi-Fi **BSS Load 广播统计信息**的校园网络观测与可视化项目。采集端读取附近 AP 广播的聚合指标，服务端接收来自独立设备的扫描结果，保存历史数据，并通过 Web 面板查看 AP、采集设备和指标变化。

项目希望探索：能否利用校园内可观测的无线网络指标，辅助分析食堂等区域的网络繁忙程度及其变化趋势。


## 📚 目录

- [下载](#下载)
- [快速开始](#快速开始)
- [系统架构](#系统架构)
- [数据采集](#数据采集)
- [远程采集设备](#远程采集设备)
- [可视化面板](#可视化面板)
- [命令行使用](#命令行使用)
- [数据语义与限制](#数据语义与限制)
- [项目结构](#项目结构)
- [测试与验证](#测试与验证)
- [安全与隐私](#安全与隐私)
- [当前进度与后续计划](#当前进度与后续计划)

## 📦 下载

[下载源码 ZIP](https://github.com/yinsuecci/canteen_monitor/archive/refs/heads/main.zip) · [查看 GitHub Releases](https://github.com/yinsuecci/canteen_monitor/releases)

源码 ZIP 不是安装包。也可以使用 Git 获取源码：

```bash
git clone https://github.com/yinsuecci/canteen_monitor.git
cd canteen_monitor
```

## 🚀 快速开始

### 环境准备

- Python 3.12+
- Windows Wi-Fi 适配器：用于执行实时扫描
- Node.js：仅在需要构建前端时使用，生产服务运行不依赖 Node.js

创建虚拟环境并安装依赖：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pytest -q
```

配置文件为项目根目录下的 `config.toml`。配置中的相对路径以配置文件所在目录为基准，而不是当前终端目录。无需固定校园网 IP、校园网账号密码或管理员权限。

### 启动服务

```powershell
.\.venv\Scripts\python.exe -m canteen_monitor serve
```

浏览器打开 [http://127.0.0.1:8000](http://127.0.0.1:8000)。

默认情况下，服务只监听本机回环地址。若需要让其他采集设备向服务端上传数据，可在可信局域网中显式监听：

```powershell
.\.venv\Scripts\python.exe -m canteen_monitor serve --host 0.0.0.0
```

随后在运行服务的电脑上访问 [设备管理页面](http://127.0.0.1:8000/#devices)，创建采集设备并配置上传端。局域网监听不代表允许远程读取仪表盘数据；远程采集使用经过认证的上传接口。程序不会自动配置防火墙、公共 DNS 或 HTTPS 证书。

### 构建前端

如果需要从源码构建前端，在项目根目录执行：

```powershell
cd frontend
npm.cmd ci
npm.cmd run build
cd ..
.\.venv\Scripts\python.exe -m canteen_monitor serve
```

生产服务直接提供构建后的前端资源。开发前端时，先在项目根目录启动后端，再在 `frontend` 目录运行 `npm.cmd run dev`；Vite 会将 `/api` 请求代理到本机 8000 端口。

## 🏗️ 系统架构

```text
┌──────────────────────┐       ┌─────────────────────────┐
│ Windows 采集设备      │       │ 其他采集设备 / 传感器    │
│ netsh WLAN 扫描       │       │ JSON 上传客户端          │
└──────────┬───────────┘       └────────────┬────────────┘
           │                                │
           └──────────────┬─────────────────┘
                          │ authenticated upload
                          ▼
              ┌────────────────────────┐
              │ Python 服务端          │
              │ API / 数据校验 / 存储   │
              └────────────┬───────────┘
                           │
                           ▼
              ┌────────────────────────┐
              │ SQLite                 │
              │ 扫描会话 / 观测历史 / AP │
              └────────────┬───────────┘
                           │
                           ▼
              ┌────────────────────────┐
              │ React + TypeScript     │
              │ ECharts Dashboard      │
              └────────────────────────┘
```

当前默认采用 **Remote Device Mode（远程设备模式）**：服务端接收独立采集设备上传的数据，本机不会自动启动 Wi-Fi 扫描。只有显式使用 `serve --collect` 时，服务端才会为调试启动本机采集器。

数据处理流程：

1. 采集设备扫描附近 Wi-Fi 网络，读取操作系统提供的 BSS Load 等广播字段。
2. 解析 SSID、BSSID、Station Count、Channel Utilization 等字段。
3. 将原始扫描会话与解析后的观测结果上传或写入本地数据库。
4. 服务端保存带 UTC 时间戳的历史记录，并维护 AP 注册信息。
5. Dashboard 按采集设备、BSSID 和时间窗口展示最新状态及历史趋势。

## 📡 数据采集

### Windows 扫描

项目通过 Windows `netsh wlan show networks mode=bssid` 等系统命令获取扫描结果，并解析中英文系统输出。

当前采集与解析能力包括：

- 多 SSID、多 BSSID 结果解析。
- BSS Load 中的 Station Count、Channel Utilization、Available Admission Capacity 等字段。
- 区分字段缺失（`null`）与明确广播的数值（例如 `0`）。
- 保留原始 stdout/stderr 字节，处理 UTF-8、OEM 和中文编码。
- 记录扫描开始/完成状态、时间、采集设备标识及失败信息。

周期采集默认在每次扫描完成后等待 60 秒再开始下一次扫描。扫描超时、失败和退出码会被记录；按 Ctrl+C 可在扫描间隔中安全停止。

### 数据字段说明

| 字段 | 含义 |
|---|---|
| SSID | 无线网络名称 |
| BSSID | AP 无线接口的 MAC 标识 |
| Station Count | AP 广播的关联无线终端数量，不是人数 |
| Channel Utilization | 信道利用率相关广播指标 |
| Available Admission Capacity | BSS Load 广播的可用接入容量字段 |
| Collector | 采集设备标识 |
| Vantage | 采集设备所在位置的人工标签 |
| Timestamp | 观测记录时间，数据库统一使用 UTC |

### 采集设备与位置

采集设备的 vantage label（观测位置标签）与 AP 的物理安装位置是两个不同概念：

- **采集位置**描述扫描设备在哪里观察到某个 BSSID。
- **AP 位置映射**描述某个 BSSID 被人工判断安装或归属于哪里。
- 在某个位置扫描到一个 BSSID，并不能单独证明该 AP 就安装在该位置。
- 同一 SSID 可能对应多个 BSSID；同一物理设备也可能广播多个 BSSID。系统不会仅凭 SSID、厂商前缀或相似 MAC 自动合并 AP。

目前可以通过 CLI 对已经观测到的 BSSID 添加人工映射。映射默认是未确认状态，只有显式指定 `--confirmed` 才会标记为确认。置信度范围为 0 到 1。历史宿舍、教学楼等扫描指纹没有被预置为已确认的物理 AP 位置。

## 🌐 远程采集设备

服务端提供独立的设备注册与认证上传能力。设备管理入口为：

[http://127.0.0.1:8000/#devices](http://127.0.0.1:8000/#devices)

支持的设备管理功能：

- 创建设备并生成上传凭据。
- 查看设备在线/离线状态与数据新鲜度。
- 设置采集设备名称及样本位置标签。
- 轮换上传密钥或禁用设备。
- 保留历史扫描记录；设置页面可以选择包含本地历史数据，但不会因此启动本地扫描。

**新设备 Token 只展示一次，请在创建时妥善保存。** 不要将 Token 提交到 Git、截图公开或写入客户端日志。

完整协议、部署边界与持久化上传客户端说明见：[Remote Collectors](docs/remote-collectors.md)。

当前 Python 上传客户端可运行于独立 Windows 采集设备，也可由其他传感器将 JSON 数据上传到服务端。ESP32-C5 固件及实体硬件验证仍是独立的后续工作，不能将其视为已经完成的功能。

## 📊 可视化面板

Dashboard 使用 React、TypeScript 与 ECharts，采用暖象牙白、炭黑和锈橙色的侧边栏布局。默认展示真实 SQLite 数据；演示模式会在内存中生成示例数据，**不会向生产数据库写入模拟记录**。

已实现功能：

- 总览与关键指标。
- 可搜索、筛选的 AP 列表。
- 按 BSSID 展示 Station Count、Channel Utilization 历史趋势。
- CSV 导出当前展示的历史数据。
- 只读区域映射与采集设备配置。
- 数据过期、采集失败、空数据等状态提示。
- 移动端布局。

页面在可见时每 15 秒刷新一次，与 Wi-Fi 扫描默认 60 秒的采集周期相互独立。自动刷新可在 Settings 页面关闭。

### 图表与统计口径

- AP 数量按 **BSSID** 计数，不将 SSID 数或物理设备数混为一谈。
- 缺失扫描点在图表中保留为 null，不会补成 0。
- 历史记录按所选 AP 的采集设备筛选，支持 2 小时、24 小时和 7 天窗口。
- 每条序列最多展示最近 10,000 个扫描点；达到上限时页面会显示截断提示。
- 如果存在第二条序列，它表示同一采集设备观测到的另一个 AP。
- 多个采集设备看到同一 BSSID 时，最新读数按采集设备分别选取；总览对相同 BSSID 的展示按最新时间去重。

### API

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/api/health` | 服务健康状态 |
| GET | `/api/dashboard/summary` | Dashboard 汇总 |
| GET | `/api/aps/{bssid}/history?collector_id=windows_01&hours=24` | BSSID 历史数据 |
| GET | `/api/devices` | 设备列表 |
| POST | `/api/devices` | 创建设备（服务端本地管理） |
| PUT | `/api/devices/{collector_id}` | 更新设备（服务端本地管理） |
| POST | `/api/devices/{collector_id}/rotate-key` | 轮换设备密钥（服务端本地管理） |
| POST | `/api/collector/observations` | 认证后的设备数据上传 |

## ⌨️ 命令行使用

以下命令均在项目根目录执行。

### 单次扫描与周期采集

```powershell
.\.venv\Scripts\python.exe -m canteen_monitor scan
.\.venv\Scripts\python.exe -m canteen_monitor collect
```

- `scan` 执行一次扫描，失败时返回退出码 1。
- `collect` 按配置持续采集，失败会记录日志并在下一周期重试。
- 程序不会自动安装 Windows 服务，也不会静默注册后台任务。
- 不要让命令行和 Web 服务同时使用相同 collector ID 运行采集，除非确实需要重复数据。

### 查询历史

查看某个 BSSID 最近 100 条观测：

```powershell
.\.venv\Scripts\python.exe -m canteen_monitor history --bssid 02:00:00:00:00:02 --limit 100
```

按 SSID 和时间范围查询：

```powershell
.\.venv\Scripts\python.exe -m canteen_monitor history --ssid Campus-Demo --since "2026-11-19T00:00:00+08:00" --until "2026-11-20T00:00:00+08:00"
```

时间过滤必须提供明确时区。历史记录按时间倒序返回，默认 1,000 条，单次查询最多 10,000 条。数据库时间戳为 UTC；面向校园场景的界面应按 Asia/Shanghai 展示，不能将 UTC 直接当作本地时间。

### 人工标记 BSSID 位置

下面仅为命令格式示例，地址不是实际校园 AP：

```powershell
.\.venv\Scripts\python.exe -m canteen_monitor map aa:bb:cc:dd:ee:ff "candidate-area" --confidence 0.4 --notes "Observed nearby; installation not confirmed"
.\.venv\Scripts\python.exe -m canteen_monitor history --location "candidate-area"
```

如需将映射标记为已确认，必须显式传入 `--confirmed`。映射使用精确 BSSID，不使用厂商前缀；后续扫描不会覆盖人工标签。历史查询中的 `--location` 使用当前注册表映射，不代表历史时刻的安装位置。采集设备的 vantage label 则单独记录在每次扫描会话中。

### 数据库备份

使用 SQLite backup API 创建一致性备份（包括已提交的 WAL 数据）：

```powershell
.\.venv\Scripts\python.exe -m canteen_monitor backup data/backups/manual.sqlite3
```

目标文件必须不存在。备份会在测试中通过重新打开数据库、检查 SQLite 完整性和核对记录数进行验证。

## 🧪 测试与验证

运行 Python 测试：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

前端端到端测试（需要本地服务运行在 8000 端口，并安装 Microsoft Edge）：

```powershell
cd frontend
npm.cmd run test:e2e
```

浏览器测试覆盖模式切换、搜索筛选、历史导出、页面导航、空/错误状态，以及 1024、768、390 像素布局。截图保存在 `docs/screenshots`；文件名含 `demo` 的截图展示的是明确标注的模拟 UI 数据。

测试还覆盖远程数据接收、独立临时服务进程的真实 HTTP 上传、数据库事务、解析器和历史记录。中英文测试样本使用虚构 AP 标识和合成指标，只用于测试解析逻辑，不是实际校园采集结果或人流证据。

## 📐 数据语义与限制

- `station_count = null` 表示广播字段缺失；`0` 表示明确广播了零。
- 扫描中没有出现的 AP 不会被插入一条 Station Count 为 0 的记录。
- `channel_utilization_raw` 只保存明确获取到的 0..255 原始值；计算百分比为 `raw / 255 * 100`。
- Windows 输出中已经取整的百分比单独保存在 `channel_utilization_display_percent`。如果只拿到百分比，原始值保持 null，不会反向推算。
- Windows 未提供频段时不猜测频段。
- 原始扫描输出以字节形式保存在 `scan_sessions`；成功解码时也保存解码后的 stdout。
- 明确的“没有可用网络”结果可作为成功扫描且不产生观测；无法识别的输出会判定失败。
- 解析或校验失败时，整次扫描的观测结果都会被拒绝，避免写入误导性的部分数据；原始会话仍保留。
- 观测、AP 注册表刷新和扫描会话完成状态以事务方式提交。新扫描只追加历史记录，已完成的会话不能再次完成。
- 进程被强制终止或存储失败可能留下 `running` 状态会话；这代表未完成，不代表成功。重启时不会为其伪造观测记录。
- Windows 可能返回缓存扫描结果。记录时间代表命令执行时间，不保证是 Beacon 的实际测量时间；当前命令不会强制触发一次全新的主动扫描。
- 周边覆盖范围、信号传播和设备漫游都会改变一次扫描所能观察到的 AP 集合。

### 从终端数到实际人数：不能直接换算

Station Count 统计的是与 AP 关联的无线终端，不是自然人数量。以下因素都会影响两者之间的关系：

1. 一个人可能同时携带手机、电脑、平板等多个终端。
2. 有人可能不连接校园 Wi-Fi，或关闭无线网卡。
3. 终端可能在相邻 AP 之间漫游，导致同一设备在不同观测点出现。
4. AP 覆盖范围可能跨越食堂边界，远处终端也可能被扫描或计入。
5. 不同 AP 的广播能力、驱动实现和数据更新时间可能不同。

因此，不能简单地把多个 AP 的 Station Count 相加作为人数。若未来要研究人流估计，需要先建立可靠的 BSSID—区域映射，设计去重与时空关联方法，并使用人工计数等独立数据进行校准和验证。

## 🔐 安全与隐私

- 项目只采集 AP 的 BSSID 和广播的聚合统计字段，不采集客户端 MAC 地址、用户流量或个人身份信息。
- 不访问未经授权的网络管理接口，不尝试提升系统权限或修改操作系统安全设置。
- Dashboard 数据与设备管理接口仅供本机管理；远程采集使用认证上传。
- 不建议将服务直接暴露到公共互联网。公网部署必须自行配置 HTTPS、身份访问控制、网络隔离与密钥管理。
- Token 仅在创建时展示一次；请勿提交凭据、真实采集数据或包含敏感信息的配置文件。
- Windows 扫描若因无线网卡、驱动、WLAN 服务或系统位置权限不可用而失败，程序会记录失败，不会伪造数据或擅自修改权限。

项目采用 [MIT License](LICENSE)。部署前请阅读 [SECURITY.md](SECURITY.md)。前端构建产物包含 `THIRD_PARTY_LICENSES.txt`，分发时请保留；第三方依赖仍遵循各自许可证。

## 🗂️ 项目结构

```text
config.toml
pyproject.toml
requirements.txt
src/canteen_monitor/
  config.py       配置校验
  models.py       与采集器无关的观测数据模型
  scanner.py      netsh 进程调用与字节解码
  parser.py       中英文扫描字段解析
  storage.py      数据库结构、事务、历史记录与备份
  collector.py    单次与周期采集编排
  cli.py          命令行入口
frontend/         React + TypeScript + ECharts 前端
tests/
  fixtures/       中英文合成扫描样本
  test_*.py       自动化测试
docs/
  remote-collectors.md  远程采集协议与部署说明
  screenshots/          浏览器测试截图
data/                   本地数据库与备份（Git 忽略）
```

## 🚧 当前进度与后续计划

### 已实现

- [x] Python 项目结构、配置校验与自动化测试。
- [x] Windows netsh 扫描、超时与退出码处理、原始字节保存及中英文解码。
- [x] 中英文 BSS Load 解析、多 SSID/BSSID、缺失值与零值区分。
- [x] SQLite 观测历史、扫描会话、AP 注册表、UTC 时间戳、索引与在线备份。
- [x] 周期采集、失败记录与优雅停止。
- [x] BSSID 人工位置标签与置信度记录。
- [x] 认证远程上传、设备注册、密钥轮换和禁用。
- [x] React + TypeScript + ECharts Dashboard、历史趋势与 CSV 导出。
- [x] Python 与浏览器端自动化测试。

### 尚未实现

- [ ] AP 位置映射的 Web 写入 API。
- [ ] BSSID 映射 CSV 导入/导出。
- [ ] 基于多采集点的指纹排名与区域归属推断。
- [ ] 食堂人工人数记录表及其数据管理。
- [ ] 经过独立标注数据训练、校准和评估的人流估计/预测模型。
- [ ] ESP32-C5 固件与实体硬件的完整验证。
- [ ] 数据库不兼容升级所需的 schema migration 工具。

当前数据库结构仅创建采集阶段所需的三张核心表。解析器、数据库结构和存储模块与 HTTP、前端代码保持独立，便于后续扩展。

---

**项目原则：先保证采集数据真实、来源可追溯、统计口径清晰，再讨论区域归属与人数估计。**
