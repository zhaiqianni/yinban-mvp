// Yinban C-001 competition firmware.
//
// Verified hardware:
//   - Five-way line sensor on GPIO 13, 18, 19, 34, 35.
//   - Left motor forward/reverse on GPIO 17/16.
//   - Right motor forward/reverse on GPIO 26/27.
//   - Local stop button on GPIO 25.
//   - HS-SR04-L ultrasonic Trig/Echo on GPIO 33/32.
//
// Safety rules:
//   - Power-up and reset always leave the motors stopped.
//   - Only START:CARDIOLOGY may begin a run.
//   - STOP, the local button, line loss, route timeout, and sensor failure stop
//     both motors locally without waiting for the computer.
//   - An obstacle stop is latched. Removing the obstacle never restarts the
//     vehicle; RESUME is required after the clearance has been confirmed.

#include <Arduino.h>
#include "BluetoothSerial.h"

#if !defined(CONFIG_BT_ENABLED) || !defined(CONFIG_BLUEDROID_ENABLED)
#error This firmware requires an original ESP32 with Bluetooth Classic support.
#endif

BluetoothSerial SerialBT;

namespace Pins {
constexpr uint8_t kLine[5] = {13, 18, 19, 34, 35};
constexpr uint8_t kLeftForward = 17;
constexpr uint8_t kLeftReverse = 16;
constexpr uint8_t kRightReverse = 27;
constexpr uint8_t kRightForward = 26;
constexpr uint8_t kStopButton = 25;
constexpr uint8_t kUltrasonicTrig = 33;
constexpr uint8_t kUltrasonicEcho = 32;
}  // namespace Pins

namespace Pwm {
constexpr uint8_t kLeftForwardChannel = 0;
constexpr uint8_t kLeftReverseChannel = 1;
constexpr uint8_t kRightReverseChannel = 2;
constexpr uint8_t kRightForwardChannel = 3;
constexpr uint32_t kFrequencyHz = 2000;
constexpr uint8_t kResolutionBits = 8;
}  // namespace Pwm

constexpr bool kBlackIsLow = true;
constexpr bool kOut1IsPhysicalLeft = true;
constexpr int kBaseDuty = 90;
constexpr int kMinimumDuty = 35;
constexpr int kMaximumDuty = 130;
constexpr float kProportionalGain = 18.0F;
constexpr float kDerivativeGain = 14.0F;

constexpr float kObstacleStopCm = 25.0F;
constexpr float kObstacleClearCm = 30.0F;
constexpr uint8_t kObstacleConfirmCount = 3;
constexpr uint8_t kClearConfirmCount = 3;
constexpr uint8_t kNoEchoStopCount = 5;
constexpr unsigned long kEchoTimeoutUs = 25000;
constexpr unsigned long kUltrasonicIntervalMs = 60;

constexpr unsigned long kLineLostStopMs = 150;
constexpr unsigned long kFinishConfirmMs = 150;
constexpr unsigned long kMaximumRouteRuntimeMs = 60000;
constexpr unsigned long kButtonDebounceMs = 40;
constexpr unsigned long kCommunicationTimeoutMs = 1500;

enum class RobotState {
  Idle,
  Moving,
  Blocked,
  LineLost,
  Arrived,
  Error,
};

RobotState robotState = RobotState::Idle;
String activeRoute;
String usbBuffer;
String bluetoothBuffer;

float previousLineError = 0.0F;
float lastDistanceCm = -1.0F;
unsigned long routeStartedMs = 0;
unsigned long lineLostStartedMs = 0;
unsigned long finishStartedMs = 0;
unsigned long lastUltrasonicMs = 0;
unsigned long buttonChangedMs = 0;
unsigned long lastControlMessageMs = 0;
bool rawButtonPressed = false;
bool stableButtonPressed = false;
uint8_t obstacleCount = 0;
uint8_t clearCount = 0;
uint8_t noEchoCount = 0;

void setupPwm(uint8_t pin, uint8_t channel) {
  ledcSetup(channel, Pwm::kFrequencyHz, Pwm::kResolutionBits);
  ledcAttachPin(pin, channel);
  ledcWrite(channel, 0);
}

void writeMotor(uint8_t forwardChannel, uint8_t reverseChannel, int command) {
  command = constrain(command, -kMaximumDuty, kMaximumDuty);
  if (command > 0) {
    ledcWrite(reverseChannel, 0);
    ledcWrite(forwardChannel, max(command, kMinimumDuty));
  } else if (command < 0) {
    ledcWrite(forwardChannel, 0);
    ledcWrite(reverseChannel, max(-command, kMinimumDuty));
  } else {
    ledcWrite(forwardChannel, 0);
    ledcWrite(reverseChannel, 0);
  }
}

void drive(int left, int right) {
  writeMotor(Pwm::kLeftForwardChannel, Pwm::kLeftReverseChannel, left);
  writeMotor(Pwm::kRightForwardChannel, Pwm::kRightReverseChannel, right);
}

void stopMotors() {
  drive(0, 0);
}

void reportEvent(const String& event) {
  Serial.println(event);
  SerialBT.println(event);
}

void resetRunTracking() {
  previousLineError = 0.0F;
  lineLostStartedMs = 0;
  finishStartedMs = 0;
  lastUltrasonicMs = 0;
  obstacleCount = 0;
  clearCount = 0;
  noEchoCount = 0;
  lastDistanceCm = -1.0F;
}

void enterIdle(bool clearRoute = false) {
  stopMotors();
  robotState = RobotState::Idle;
  routeStartedMs = 0;
  resetRunTracking();
  if (clearRoute) {
    activeRoute = "";
  }
  reportEvent("READY");
}

void enterError(const String& reason) {
  stopMotors();
  robotState = RobotState::Error;
  reportEvent("ERROR:" + reason);
}

bool sensorOnBlack(uint8_t pin) {
  const bool isHigh = digitalRead(pin) == HIGH;
  return kBlackIsLow ? !isHigh : isHigh;
}

float readDistanceCm() {
  digitalWrite(Pins::kUltrasonicTrig, LOW);
  delayMicroseconds(2);
  digitalWrite(Pins::kUltrasonicTrig, HIGH);
  delayMicroseconds(10);
  digitalWrite(Pins::kUltrasonicTrig, LOW);

  const unsigned long durationUs =
      pulseIn(Pins::kUltrasonicEcho, HIGH, kEchoTimeoutUs);
  if (durationUs == 0) {
    return -1.0F;
  }
  return static_cast<float>(durationUs) / 58.0F;
}

void readLine(bool line[5], int& activeCount, int& weightedSum) {
  static const int weights[5] = {-2, -1, 0, 1, 2};
  activeCount = 0;
  weightedSum = 0;

  for (uint8_t index = 0; index < 5; ++index) {
    const uint8_t physicalIndex =
        kOut1IsPhysicalLeft ? index : static_cast<uint8_t>(4 - index);
    line[physicalIndex] = sensorOnBlack(Pins::kLine[index]);
  }

  for (uint8_t index = 0; index < 5; ++index) {
    if (line[index]) {
      ++activeCount;
      weightedSum += weights[index];
    }
  }
}

void startRoute(const String& route) {
  if (route != "CARDIOLOGY") {
    reportEvent("ERROR:UNSUPPORTED_ROUTE");
    return;
  }

  bool line[5];
  int activeCount = 0;
  int weightedSum = 0;
  readLine(line, activeCount, weightedSum);
  if (activeCount == 0) {
    stopMotors();
    robotState = RobotState::LineLost;
    reportEvent("LINE_LOST");
    return;
  }

  const float distanceCm = readDistanceCm();
  lastDistanceCm = distanceCm;
  if (distanceCm > 0.0F && distanceCm < kObstacleStopCm) {
    stopMotors();
    activeRoute = route;
    robotState = RobotState::Blocked;
    obstacleCount = kObstacleConfirmCount;
    clearCount = 0;
    reportEvent("BLOCKED:" + String(distanceCm, 1));
    return;
  }

  activeRoute = route;
  resetRunTracking();
  robotState = RobotState::Moving;
  routeStartedMs = millis();
  lastControlMessageMs = routeStartedMs;
  reportEvent("MOVING");
}

void reportCurrentState() {
  switch (robotState) {
    case RobotState::Idle:
      reportEvent("READY");
      break;
    case RobotState::Moving:
      reportEvent("MOVING");
      break;
    case RobotState::Blocked:
      reportEvent("BLOCKED:" + String(max(lastDistanceCm, 0.0F), 1));
      break;
    case RobotState::LineLost:
      reportEvent("LINE_LOST");
      break;
    case RobotState::Arrived:
      reportEvent("ARRIVED:" + activeRoute);
      break;
    case RobotState::Error:
      reportEvent("ERROR:STOPPED");
      break;
  }
}

void handleCommand(String command) {
  command.trim();
  command.toUpperCase();
  if (command.length() == 0) {
    return;
  }

  if (command == "PING") {
    lastControlMessageMs = millis();
    reportCurrentState();
    return;
  }
  if (command == "STOP") {
    lastControlMessageMs = millis();
    enterIdle(false);
    return;
  }
  if (command == "RESET") {
    lastControlMessageMs = millis();
    enterIdle(true);
    return;
  }
  if (command == "RESUME") {
    lastControlMessageMs = millis();
    if (robotState != RobotState::Blocked) {
      reportEvent("ERROR:RESUME_NOT_ALLOWED");
      return;
    }
    if (clearCount < kClearConfirmCount) {
      reportEvent("BLOCKED:" + String(max(lastDistanceCm, 0.0F), 1));
      return;
    }

    resetRunTracking();
    robotState = RobotState::Moving;
    routeStartedMs = millis();
    lastControlMessageMs = routeStartedMs;
    reportEvent("MOVING");
    return;
  }
  if (command.startsWith("START:")) {
    lastControlMessageMs = millis();
    startRoute(command.substring(6));
    return;
  }

  stopMotors();
  robotState = RobotState::Error;
  reportEvent("ERROR:UNKNOWN_COMMAND");
}

void readCommands(Stream& stream, String& buffer) {
  while (stream.available()) {
    const char current = static_cast<char>(stream.read());
    if (current == '\n' || current == '\r') {
      if (buffer.length() > 0) {
        handleCommand(buffer);
        buffer = "";
      }
    } else if (buffer.length() < 80) {
      buffer += current;
    } else {
      buffer = "";
      stopMotors();
      robotState = RobotState::Error;
      reportEvent("ERROR:COMMAND_TOO_LONG");
    }
  }
}

void updateButton() {
  const unsigned long now = millis();
  const bool pressed = digitalRead(Pins::kStopButton) == LOW;
  if (pressed != rawButtonPressed) {
    rawButtonPressed = pressed;
    buttonChangedMs = now;
  }

  if (now - buttonChangedMs < kButtonDebounceMs ||
      stableButtonPressed == rawButtonPressed) {
    return;
  }

  stableButtonPressed = rawButtonPressed;
  if (stableButtonPressed) {
    enterIdle(false);
  }
}

void updateUltrasonic() {
  if (robotState != RobotState::Moving &&
      robotState != RobotState::Blocked) {
    return;
  }

  const unsigned long now = millis();
  if (now - lastUltrasonicMs < kUltrasonicIntervalMs) {
    return;
  }
  lastUltrasonicMs = now;

  lastDistanceCm = readDistanceCm();
  if (lastDistanceCm < 0.0F) {
    clearCount = 0;
    obstacleCount = 0;
    if (robotState == RobotState::Moving &&
        ++noEchoCount >= kNoEchoStopCount) {
      enterError("ULTRASONIC_NO_ECHO");
    }
    return;
  }
  noEchoCount = 0;

  if (robotState == RobotState::Moving) {
    if (lastDistanceCm < kObstacleStopCm) {
      if (obstacleCount < kObstacleConfirmCount) {
        ++obstacleCount;
      }
      if (obstacleCount >= kObstacleConfirmCount) {
        stopMotors();
        robotState = RobotState::Blocked;
        clearCount = 0;
        reportEvent("BLOCKED:" + String(lastDistanceCm, 1));
      }
    } else {
      obstacleCount = 0;
    }
    return;
  }

  if (lastDistanceCm >= kObstacleClearCm) {
    if (clearCount < kClearConfirmCount) {
      ++clearCount;
    }
  } else {
    clearCount = 0;
  }
}

void updateLineFollowing() {
  if (robotState != RobotState::Moving) {
    return;
  }

  const unsigned long now = millis();
  bool line[5];
  int activeCount = 0;
  int weightedSum = 0;
  readLine(line, activeCount, weightedSum);

  if (activeCount == 5) {
    stopMotors();
    lineLostStartedMs = 0;
    if (finishStartedMs == 0) {
      finishStartedMs = now;
    } else if (now - finishStartedMs >= kFinishConfirmMs) {
      robotState = RobotState::Arrived;
      reportEvent("ARRIVED:" + activeRoute);
    }
    return;
  }
  finishStartedMs = 0;

  if (activeCount == 0) {
    stopMotors();
    if (lineLostStartedMs == 0) {
      lineLostStartedMs = now;
    } else if (now - lineLostStartedMs >= kLineLostStopMs) {
      robotState = RobotState::LineLost;
      reportEvent("LINE_LOST");
    }
    return;
  }

  lineLostStartedMs = 0;
  const float error = static_cast<float>(weightedSum) / activeCount;
  const float correction =
      kProportionalGain * error +
      kDerivativeGain * (error - previousLineError);
  previousLineError = error;

  const int left = constrain(
      static_cast<int>(kBaseDuty + correction),
      kMinimumDuty,
      kMaximumDuty);
  const int right = constrain(
      static_cast<int>(kBaseDuty - correction),
      kMinimumDuty,
      kMaximumDuty);
  drive(left, right);
}

void setup() {
  Serial.begin(115200);
  SerialBT.begin("YINBAN_ROBOT");

  for (uint8_t pin : Pins::kLine) {
    pinMode(pin, INPUT);
  }
  pinMode(Pins::kStopButton, INPUT_PULLUP);
  pinMode(Pins::kUltrasonicTrig, OUTPUT);
  pinMode(Pins::kUltrasonicEcho, INPUT);
  digitalWrite(Pins::kUltrasonicTrig, LOW);

  setupPwm(Pins::kLeftForward, Pwm::kLeftForwardChannel);
  setupPwm(Pins::kLeftReverse, Pwm::kLeftReverseChannel);
  setupPwm(Pins::kRightReverse, Pwm::kRightReverseChannel);
  setupPwm(Pins::kRightForward, Pwm::kRightForwardChannel);
  stopMotors();

  rawButtonPressed = digitalRead(Pins::kStopButton) == LOW;
  stableButtonPressed = rawButtonPressed;
  buttonChangedMs = millis();
  delay(250);
  reportEvent("READY");
}

void loop() {
  readCommands(Serial, usbBuffer);
  readCommands(SerialBT, bluetoothBuffer);
  updateButton();

  if (robotState == RobotState::Moving &&
      millis() - routeStartedMs >= kMaximumRouteRuntimeMs) {
    enterError("ROUTE_TIMEOUT");
  }

  if (robotState == RobotState::Moving &&
      millis() - lastControlMessageMs >= kCommunicationTimeoutMs) {
    enterError("COMMUNICATION_TIMEOUT");
  }

  updateUltrasonic();
  updateLineFollowing();

  if (robotState != RobotState::Moving) {
    stopMotors();
  }
  delay(2);
}
