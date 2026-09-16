# C-001 硬件诊断程序

`c001_sensor_diagnostic` 是正式固件之前使用的只读诊断程序。它会强制停止左右电机，只通过 USB 串口输出：

- GPIO 13/18/19/34/35：五路循迹模块 OUT1～OUT5 原始值；
- GPIO 32/33：超声波测距结果。

`c001_motor_diagnostic` 是一次性低速电机诊断程序。它使用 GPIO
16/17 驱动左电机、GPIO 26/27 驱动右电机，上电等待八秒后依次执行
左右轮正反转和双轮前进，完成后保持停车。

## 当前已验证环境

- 主控：ESP32-WROOM-32 系列；
- 板型：`esp32:esp32:esp32`（ESP32 Dev Module）；
- ESP32 Arduino Core：`2.0.17-cn`；
- 波特率：115200；
- USB 串口：CH340（本机当前为 `COM5`）。

## 命令

```powershell
$arduinoCli = 'C:\Program Files\Arduino CLI\arduino-cli.exe'
& $arduinoCli compile --fqbn esp32:esp32:esp32 firmware\diagnostics\c001_sensor_diagnostic
& $arduinoCli upload --port COM5 --fqbn esp32:esp32:esp32 firmware\diagnostics\c001_sensor_diagnostic
& $arduinoCli monitor --port COM5 --config baudrate=115200
```

烧录及传感器检查时不要安装 14500 电池。只有进入单独的电机诊断阶段后，才在车轮架空的情况下安装电池。
