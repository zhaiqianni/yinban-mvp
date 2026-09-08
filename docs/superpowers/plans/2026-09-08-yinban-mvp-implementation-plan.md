# “银伴”医院智能陪诊导引机器人 MVP 实施计划

日期：2026-09-08  
依据：2026-09-08-yinban-mvp-design.md  
实施范围：P0 软件主流程、模拟机器人、自动测试、ESP32 固件骨架与交付文档

## 1. 实施原则

- 先完成无硬件也能演示的闭环，再接入真实小车。
- 每个核心模块先写可测试的纯 Python 逻辑，再接入 API 和界面。
- 在线 LLM、第二条实体路线和高级视觉功能不进入本阶段。
- 所有硬件调用都通过 RobotLink 接口，模拟与真实串口可以互换。
- STOP、断线、丢线和超时保护优先于新增功能。

## 2. 任务拆分

### Task 1：项目骨架与运行环境

创建：

- yinban-mvp/README.md
- yinban-mvp/requirements.txt
- yinban-mvp/.env.example
- yinban-mvp/.gitignore
- yinban-mvp/run.ps1
- Python 包目录和测试目录

完成条件：

- 可以建立 .venv 并安装依赖。
- python -m app.main 能启动服务。

### Task 2：医院数据与意图识别

创建：

- app/data/hospital.json
- app/data/intents.json
- app/core/intent_router.py
- app/core/dialogue_engine.py
- tests/test_intent_router.py

实现：

- navigate、process、help、stop 和 unknown 五类意图。
- 紧急/停止关键词优先。
- 目的地别名匹配。
- 预设回答和澄清回答。

完成条件：

- 15 条演示问法全部通过测试。
- 未知问题不会生成医疗建议。

### Task 3：路线与医院地图

创建：

- app/data/routes.json
- app/core/route_planner.py
- tests/test_route_planner.py

实现：

- 基于节点连接关系的最短路径。
- 区分“可展示路线”和“可发送给实体机器人路线”。
- CARDIOLOGY 为唯一 P0 实体路线。

完成条件：

- 心内科路线返回大厅、电梯口、心内科。
- 药房和厕所可展示，但不得误发实体路线指令。

### Task 4：机器人协议、模拟器与真实串口接口

创建：

- app/services/robot_protocol.py
- app/services/robot_link.py
- app/services/mock_robot.py
- tests/test_robot_protocol.py
- tests/test_mock_robot.py

实现：

- PING、START、STOP、RESUME、RESET。
- READY、MOVING、BLOCKED、LINE_LOST、ARRIVED、ERROR。
- 模拟机器人按时间推进状态。
- pyserial 真实串口适配。
- 串口不可用时明确进入模拟模式。

完成条件：

- 模拟器可以完成 MOVING→BLOCKED→MOVING→ARRIVED。
- STOP 可从任意运行状态立即进入 IDLE。

### Task 5：FastAPI 接口

创建：

- app/models/schemas.py
- app/api/dialogue.py
- app/api/navigation.py
- app/api/robot.py
- app/main.py
- tests/test_api.py

实现：

- POST /api/dialogue
- GET /api/navigation/{destination}
- POST /api/robot/start
- POST /api/robot/stop
- POST /api/robot/resume
- POST /api/robot/reset
- GET /api/robot/status
- GET /api/health

完成条件：

- API 测试通过。
- 静态 Web 页面由同一 FastAPI 服务提供。

### Task 6：老年友好 Web UI

创建：

- app/web/index.html
- app/web/css/app.css
- app/web/js/app.js
- app/web/assets/hospital-map.svg

实现：

- 四个大按钮、语音按钮和文字输入。
- 回答、路线节点、机器人状态和连接模式显示。
- 浏览器 Web Speech API 与 speechSynthesis。
- 语音不可用时不影响按钮和文字输入。
- 心内科任务的一键演示、停止和复位。
- 每 500 毫秒轮询机器人状态。

完成条件：

- 在 Edge/Chrome 中可完成软件闭环。
- 页面缩放到 125% 时无主要内容溢出。

### Task 7：ESP32 固件骨架

创建：

- firmware/yinban_car/yinban_car.ino

实现：

- 状态机和串口/经典蓝牙指令解析。
- TB6612FNG 双电机控制。
- 五路数字巡线输入。
- HC-SR04P 距离检测。
- 障碍、丢线、终点和最长运行时间保护。
- 所有引脚集中定义并附修改说明。

完成条件：

- Arduino 代码结构完整且无占位逻辑。
- 无硬件环境下完成静态人工检查；实际引脚需按采购套件调整。

### Task 8：操作与交付文档

创建：

- docs/procurement.md
- docs/wiring.md
- docs/demo-script.md
- docs/troubleshooting.md

实现：

- 淘宝搜索词、卖家确认清单和预算。
- 接线原则、3.3V 电平和共地警告。
- 2 分钟演示台词与故障降级流程。
- 蓝牙、串口、语音和巡线常见故障排查。

完成条件：

- 非硬件专业成员可以依据文档完成软件启动和基本接线核对。

### Task 9：端到端验证

执行：

- pytest
- FastAPI 启动与健康检查
- 浏览器主流程检查
- 模拟机器人完整任务
- 静态文件与 JSON 格式检查

完成条件：

- 自动测试全部通过。
- 软件无需 API Key 和真实硬件即可运行。
- 界面清楚标识 SIMULATION 或 HARDWARE。

## 3. 实施顺序

1. Task 1–3：建立可测试的业务核心。
2. Task 4–5：打通模拟机器人和 API。
3. Task 6：实现完整演示界面。
4. Task 7：提供可按套件调整的固件。
5. Task 8–9：文档、测试和交付验证。

## 4. 预期提交

- 提交 1：实施计划。
- 提交 2：后端核心、数据、API 和自动测试。
- 提交 3：Web UI、模拟机器人与端到端验证。
- 提交 4：ESP32 固件和硬件交付文档。

## 5. 暂不实施

- LLM API。
- 真实医院接口。
- 第二条实体路线。
- 人脸、NFC、UWB、摄像头或人体跟随。
- ROS、SLAM、激光雷达和电梯联动。
