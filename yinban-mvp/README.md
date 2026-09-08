# 银伴医院智能陪诊导引机器人 MVP

面向创新创业比赛的一周原型：浏览器负责老年友好交互、医院问答和路线展示，ESP32 巡线小车负责实体导引。默认使用模拟机器人，因此没有硬件和 API Key 也能运行完整软件演示。

## 当前能力

- 心内科、药房、卫生间、检验科和挂号处问询。
- 按说话顺序识别多个目的地，并组合显示分站信息和软件路线。
- 常见就医流程回答。
- 大按钮、文字输入、浏览器中文语音输入和语音播报。
- 心内科路线动画。
- 模拟机器人完整状态流程。
- USB 或经典蓝牙虚拟串口控制 ESP32。
- STOP、障碍、丢线和运行超时保护协议。

## 快速启动

在 PowerShell 中进入本目录，然后运行：

    .\run.ps1

首次运行会创建 .venv 并安装依赖。看到服务启动后，在 Edge 或 Chrome 中打开：

    http://127.0.0.1:8000

也可以手动运行：

    python -m venv .venv
    .\.venv\Scripts\python.exe -m pip install -r requirements.txt
    .\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000

## 运行测试

    .\.venv\Scripts\python.exe -m pytest -q

## 连接真实小车

先在 Windows 中将 ESP32 经典蓝牙配对为虚拟 COM 口，或通过 USB 连接。然后在启动前设置：

    $env:YINBAN_MODE = "hardware"
    $env:YINBAN_ROBOT_PORT = "COM6"
    .\run.ps1

请把 COM6 替换为设备管理器中实际显示的端口。连接失败时，系统会明确降级为模拟模式。

## 项目边界

本项目是固定环境概念验证，不是可在真实医院通用部署的自主机器人。它不包含 SLAM、医疗诊断、真实挂号系统、患者身份识别或真实医护求助通知。

硬件接线、采购、演示和故障处理分别见 docs 目录。
