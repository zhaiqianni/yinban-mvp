// Yinban C-001 multi-route competition firmware.
//
// Verified pins:
//   line sensors 13/18/19/34/35, left motor 17/16, right motor 26/27,
//   local stop button 25, HS-SR04-L Trig/Echo 33/32.
//
// The computer sends a validated route action queue. The car never resumes
// after power loss, Bluetooth reconnect, manual stop, line loss, or a turn
// timeout. RESET is an explicit confirmation that the car was manually placed
// at the fixed lobby start with its nose pointing toward elevator 3.

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
constexpr int kTurnDuty = 78;
constexpr float kProportionalGain = 18.0F;
constexpr float kDerivativeGain = 14.0F;

constexpr float kObstacleStopCm = 25.0F;
constexpr float kObstacleClearCm = 30.0F;
constexpr uint8_t kObstacleConfirmCount = 3;
constexpr uint8_t kClearConfirmCount = 3;
constexpr uint8_t kNoEchoStopCount = 5;
constexpr unsigned long kEchoTimeoutUs = 25000;
constexpr unsigned long kUltrasonicIntervalMs = 60;

constexpr uint8_t kMaximumActions = 8;
constexpr unsigned long kNodeConfirmMs = 30;
constexpr unsigned long kLineStableMs = 35;
constexpr unsigned long kLineLostStopMs = 150;
constexpr unsigned long kStraightCrossMs = 240;
constexpr unsigned long kTurnAdvanceMs = 125;
constexpr unsigned long kTurnMinimumMs = 190;
constexpr unsigned long kTurnTimeoutMs = 1500;
constexpr unsigned long kUTurnMinimumMs = 430;
constexpr unsigned long kUTurnTimeoutMs = 2300;
constexpr unsigned long kMaximumRouteRuntimeMs = 60000;
constexpr unsigned long kButtonDebounceMs = 40;
constexpr unsigned long kCommunicationTimeoutMs = 1500;

enum class RobotState {
  NeedsReset,
  Idle,
  Moving,
  Turning,
  Blocked,
  LineLost,
  Arrived,
  Error,
};

enum class Maneuver { None, Straight, Left, Right, UTurn };

RobotState robotState = RobotState::NeedsReset;
RobotState stateBeforeBlocked = RobotState::Moving;
Maneuver maneuver = Maneuver::None;
String activeMission;
String activeBaseRoute;
String usbBuffer;
String bluetoothBuffer;
char routeActions[kMaximumActions];
uint8_t actionCount = 0;
uint8_t actionIndex = 0;
uint8_t nodeCount = 0;

float previousLineError = 0.0F;
float lastDistanceCm = -1.0F;
unsigned long routeStartedMs = 0;
unsigned long lineLostStartedMs = 0;
unsigned long nodeStartedMs = 0;
unsigned long normalLineStartedMs = 0;
unsigned long maneuverStartedMs = 0;
unsigned long turnLineStartedMs = 0;
unsigned long lastUltrasonicMs = 0;
unsigned long buttonChangedMs = 0;
unsigned long lastControlMessageMs = 0;
bool rawButtonPressed = false;
bool stableButtonPressed = false;
bool homeReady = false;
bool nodeArmed = true;
bool turnSawClear = false;
bool hadBluetoothClient = false;
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

void stopMotors() { drive(0, 0); }

void reportEvent(const String& event) {
  Serial.println(event);
  SerialBT.println(event);
}

void clearMission() {
  activeMission = "";
  activeBaseRoute = "";
  actionCount = 0;
  actionIndex = 0;
  nodeCount = 0;
  maneuver = Maneuver::None;
}

void resetRunTracking() {
  previousLineError = 0.0F;
  lineLostStartedMs = 0;
  nodeStartedMs = 0;
  normalLineStartedMs = 0;
  maneuverStartedMs = 0;
  turnLineStartedMs = 0;
  lastUltrasonicMs = 0;
  obstacleCount = 0;
  clearCount = 0;
  noEchoCount = 0;
  lastDistanceCm = -1.0F;
  nodeArmed = true;
  turnSawClear = false;
}

void enterNeedsReset() {
  stopMotors();
  robotState = RobotState::NeedsReset;
  homeReady = false;
  routeStartedMs = 0;
  clearMission();
  resetRunTracking();
  reportEvent("NEEDS_RESET");
}

void confirmHome() {
  stopMotors();
  robotState = RobotState::Idle;
  homeReady = true;
  routeStartedMs = 0;
  clearMission();
  resetRunTracking();
  reportEvent("HOME_READY");
}

void enterError(const String& reason) {
  stopMotors();
  robotState = RobotState::Error;
  homeReady = false;
  reportEvent("ERROR:" + reason);
}

bool sensorOnBlack(uint8_t pin) {
  const bool isHigh = digitalRead(pin) == HIGH;
  return kBlackIsLow ? !isHigh : isHigh;
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

float readDistanceCm() {
  digitalWrite(Pins::kUltrasonicTrig, LOW);
  delayMicroseconds(2);
  digitalWrite(Pins::kUltrasonicTrig, HIGH);
  delayMicroseconds(10);
  digitalWrite(Pins::kUltrasonicTrig, LOW);
  const unsigned long durationUs =
      pulseIn(Pins::kUltrasonicEcho, HIGH, kEchoTimeoutUs);
  return durationUs == 0 ? -1.0F : static_cast<float>(durationUs) / 58.0F;
}

bool isAllowedAction(char action) {
  return action == 'S' || action == 'L' || action == 'R' ||
         action == 'U' || action == 'X';
}

bool missionMatches(const String& mission, const String& actions) {
  return (mission == "CARDIOLOGY" && actions == "S,X") ||
         (mission == "TOILET" && actions == "R,X") ||
         (mission == "PHARMACY" && actions == "S,R,X") ||
         (mission == "RETURN_CARDIOLOGY" && actions == "U,S,X") ||
         (mission == "RETURN_TOILET" && actions == "U,L,X") ||
         (mission == "RETURN_PHARMACY" && actions == "U,L,S,X");
}

bool parseActions(const String& actionText) {
  actionCount = 0;
  if (actionText.length() == 0 || actionText.endsWith(",")) {
    return false;
  }
  int start = 0;
  while (start < actionText.length()) {
    const int comma = actionText.indexOf(',', start);
    const int end = comma < 0 ? actionText.length() : comma;
    if (end - start != 1 || actionCount >= kMaximumActions) {
      return false;
    }
    const char action = actionText.charAt(start);
    if (!isAllowedAction(action)) {
      return false;
    }
    routeActions[actionCount++] = action;
    if (comma < 0) {
      break;
    }
    start = comma + 1;
  }
  if (actionCount == 0 || routeActions[actionCount - 1] != 'X') {
    return false;
  }
  for (uint8_t index = 0; index + 1 < actionCount; ++index) {
    if (routeActions[index] == 'X') {
      return false;
    }
    if (routeActions[index] == 'U' && index != 0) {
      return false;
    }
  }
  return true;
}

String baseRouteFor(const String& mission) {
  return mission.startsWith("RETURN_") ? mission.substring(7) : mission;
}

void reportMoving() { reportEvent("MOVING:" + activeMission); }

void beginManeuver(Maneuver next) {
  maneuver = next;
  maneuverStartedMs = millis();
  turnLineStartedMs = 0;
  turnSawClear = false;
  nodeArmed = false;
  robotState = next == Maneuver::Straight ? RobotState::Moving
                                          : RobotState::Turning;
  if (next == Maneuver::Left) {
    reportEvent("TURNING:LEFT");
  } else if (next == Maneuver::Right) {
    reportEvent("TURNING:RIGHT");
  } else if (next == Maneuver::UTurn) {
    reportEvent("TURNING:UTURN");
  } else {
    reportEvent("TURNING:STRAIGHT");
  }
}

bool linePresentAtStart() {
  bool line[5];
  int activeCount = 0;
  int weightedSum = 0;
  readLine(line, activeCount, weightedSum);
  return activeCount > 0;
}

void startMission(const String& mission, const String& actionText) {
  const bool isReturn = mission.startsWith("RETURN_");
  const String baseRoute = baseRouteFor(mission);
  if (!missionMatches(mission, actionText) || !parseActions(actionText)) {
    enterError("INVALID_ROUTE");
    return;
  }
  if ((!isReturn && (robotState != RobotState::Idle || !homeReady)) ||
      (isReturn && (robotState != RobotState::Arrived ||
                    activeBaseRoute != baseRoute))) {
    enterError("POSITION_MISMATCH");
    return;
  }
  if (!linePresentAtStart()) {
    robotState = RobotState::LineLost;
    homeReady = false;
    reportEvent("LINE_LOST");
    return;
  }
  const float distanceCm = readDistanceCm();
  lastDistanceCm = distanceCm;
  if (distanceCm > 0.0F && distanceCm < kObstacleStopCm) {
    enterError("START_BLOCKED");
    return;
  }

  activeMission = mission;
  activeBaseRoute = baseRoute;
  actionIndex = 0;
  nodeCount = 0;
  homeReady = false;
  resetRunTracking();
  // Ignore the start/arrival marker under the sensors. The first route action
  // belongs to the next junction after normal line has been reacquired.
  nodeArmed = false;
  routeStartedMs = millis();
  lastControlMessageMs = routeStartedMs;
  robotState = RobotState::Moving;
  reportMoving();
  if (routeActions[0] == 'U') {
    beginManeuver(Maneuver::UTurn);
  }
}

void finishMission() {
  stopMotors();
  const String completedMission = activeMission;
  reportEvent("ARRIVED:" + completedMission);
  if (completedMission.startsWith("RETURN_")) {
    robotState = RobotState::Idle;
    homeReady = true;
    clearMission();
    reportEvent("HOME_READY");
  } else {
    robotState = RobotState::Arrived;
    homeReady = false;
  }
}

void executeNodeAction() {
  if (actionIndex >= actionCount) {
    enterError("ACTION_UNDERFLOW");
    return;
  }
  const char action = routeActions[actionIndex];
  ++nodeCount;
  reportEvent("NODE:" + activeMission + ":" + String(nodeCount));
  if (action == 'X') {
    ++actionIndex;
    finishMission();
  } else if (action == 'S') {
    beginManeuver(Maneuver::Straight);
  } else if (action == 'L') {
    beginManeuver(Maneuver::Left);
  } else if (action == 'R') {
    beginManeuver(Maneuver::Right);
  } else {
    enterError("UNEXPECTED_ACTION");
  }
}

void finishManeuver() {
  ++actionIndex;
  maneuver = Maneuver::None;
  maneuverStartedMs = 0;
  turnLineStartedMs = 0;
  normalLineStartedMs = 0;
  lineLostStartedMs = 0;
  previousLineError = 0.0F;
  nodeArmed = false;
  robotState = RobotState::Moving;
  reportMoving();
}

void reportCurrentState() {
  switch (robotState) {
    case RobotState::NeedsReset:
      reportEvent("NEEDS_RESET");
      break;
    case RobotState::Idle:
      reportEvent(homeReady ? "HOME_READY" : "NEEDS_RESET");
      break;
    case RobotState::Moving:
      reportMoving();
      break;
    case RobotState::Turning:
      reportEvent(maneuver == Maneuver::Left ? "TURNING:LEFT" :
                  maneuver == Maneuver::Right ? "TURNING:RIGHT" :
                  "TURNING:UTURN");
      break;
    case RobotState::Blocked:
      reportEvent("BLOCKED:" + String(max(lastDistanceCm, 0.0F), 1));
      break;
    case RobotState::LineLost:
      reportEvent("LINE_LOST");
      break;
    case RobotState::Arrived:
      reportEvent("ARRIVED:" + activeMission);
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
  if (command == "RESET") {
    lastControlMessageMs = millis();
    confirmHome();
    return;
  }
  if (command == "STOP") {
    lastControlMessageMs = millis();
    if (robotState == RobotState::Moving || robotState == RobotState::Turning ||
        robotState == RobotState::Blocked) {
      enterNeedsReset();
    } else {
      stopMotors();
      reportCurrentState();
    }
    return;
  }
  if (command == "RESUME") {
    lastControlMessageMs = millis();
    if (robotState != RobotState::Blocked || clearCount < kClearConfirmCount) {
      reportEvent(robotState == RobotState::Blocked
                      ? "BLOCKED:" + String(max(lastDistanceCm, 0.0F), 1)
                      : "ERROR:RESUME_NOT_ALLOWED");
      return;
    }
    robotState = stateBeforeBlocked;
    obstacleCount = 0;
    clearCount = 0;
    noEchoCount = 0;
    reportCurrentState();
    return;
  }
  if (command.startsWith("RUN:")) {
    lastControlMessageMs = millis();
    const int separator = command.indexOf(':', 4);
    if (separator < 0) {
      enterError("INVALID_ROUTE");
      return;
    }
    startMission(command.substring(4, separator),
                 command.substring(separator + 1));
    return;
  }
  enterError("UNKNOWN_COMMAND");
}

void readCommands(Stream& stream, String& buffer) {
  while (stream.available()) {
    const char current = static_cast<char>(stream.read());
    if (current == '\n' || current == '\r') {
      if (buffer.length() > 0) {
        handleCommand(buffer);
        buffer = "";
      }
    } else if (buffer.length() < 96) {
      buffer += current;
    } else {
      buffer = "";
      enterError("COMMAND_TOO_LONG");
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
  if (stableButtonPressed &&
      (robotState == RobotState::Moving || robotState == RobotState::Turning ||
       robotState == RobotState::Blocked)) {
    enterNeedsReset();
  }
}

bool isActiveMotionState() {
  return robotState == RobotState::Moving ||
         robotState == RobotState::Turning;
}

void updateBluetoothConnection() {
  const bool hasClient = SerialBT.hasClient();
  if (hadBluetoothClient && !hasClient &&
      (isActiveMotionState() || robotState == RobotState::Blocked)) {
    enterError("COMMUNICATION_LOST");
  }
  hadBluetoothClient = hasClient;
}

void updateUltrasonic() {
  if (!isActiveMotionState() && robotState != RobotState::Blocked) {
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
    if (isActiveMotionState() && ++noEchoCount >= kNoEchoStopCount) {
      enterError("ULTRASONIC_NO_ECHO");
    }
    return;
  }
  noEchoCount = 0;
  if (isActiveMotionState()) {
    if (lastDistanceCm < kObstacleStopCm) {
      if (obstacleCount < kObstacleConfirmCount) {
        ++obstacleCount;
      }
      if (obstacleCount >= kObstacleConfirmCount) {
        stateBeforeBlocked = robotState;
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

void driveLine(int activeCount, int weightedSum) {
  const float error = static_cast<float>(weightedSum) / activeCount;
  const float correction =
      kProportionalGain * error +
      kDerivativeGain * (error - previousLineError);
  previousLineError = error;
  const int left = constrain(static_cast<int>(kBaseDuty + correction),
                             kMinimumDuty, kMaximumDuty);
  const int right = constrain(static_cast<int>(kBaseDuty - correction),
                              kMinimumDuty, kMaximumDuty);
  drive(left, right);
}

void updateManeuver(const bool line[5], int activeCount) {
  const unsigned long now = millis();
  const unsigned long elapsed = now - maneuverStartedMs;
  if (maneuver == Maneuver::Straight) {
    drive(kBaseDuty, kBaseDuty);
    if (elapsed >= kStraightCrossMs && activeCount <= 3) {
      finishManeuver();
    } else if (elapsed >= kTurnTimeoutMs) {
      enterError("JUNCTION_TIMEOUT");
    }
    return;
  }

  if (maneuver == Maneuver::Left) {
    if (elapsed < kTurnAdvanceMs) {
      drive(kBaseDuty, kBaseDuty);
    } else {
      drive(-kTurnDuty, kTurnDuty);
    }
  } else {
    if (maneuver == Maneuver::Right && elapsed < kTurnAdvanceMs) {
      drive(kBaseDuty, kBaseDuty);
    } else {
      drive(kTurnDuty, -kTurnDuty);
    }
  }

  if (activeCount <= 2) {
    turnSawClear = true;
  }
  const unsigned long minimum =
      maneuver == Maneuver::UTurn ? kUTurnMinimumMs : kTurnMinimumMs;
  const unsigned long timeout =
      maneuver == Maneuver::UTurn ? kUTurnTimeoutMs : kTurnTimeoutMs;
  if (turnSawClear && elapsed >= minimum && line[2] && activeCount <= 3) {
    if (turnLineStartedMs == 0) {
      turnLineStartedMs = now;
    } else if (now - turnLineStartedMs >= kLineStableMs) {
      finishManeuver();
    }
  } else {
    turnLineStartedMs = 0;
  }
  if (elapsed >= timeout) {
    enterError(maneuver == Maneuver::UTurn ? "UTURN_TIMEOUT"
                                           : "JUNCTION_TIMEOUT");
  }
}

void updateLineControl() {
  if (!isActiveMotionState()) {
    return;
  }
  const unsigned long now = millis();
  bool line[5];
  int activeCount = 0;
  int weightedSum = 0;
  readLine(line, activeCount, weightedSum);

  if (maneuver != Maneuver::None) {
    updateManeuver(line, activeCount);
    return;
  }
  if (activeCount == 0) {
    stopMotors();
    if (lineLostStartedMs == 0) {
      lineLostStartedMs = now;
    } else if (now - lineLostStartedMs >= kLineLostStopMs) {
      robotState = RobotState::LineLost;
      homeReady = false;
      reportEvent("LINE_LOST");
    }
    return;
  }
  lineLostStartedMs = 0;

  if (!nodeArmed) {
    if (activeCount <= 3) {
      if (normalLineStartedMs == 0) {
        normalLineStartedMs = now;
      } else if (now - normalLineStartedMs >= kLineStableMs) {
        nodeArmed = true;
      }
    } else {
      normalLineStartedMs = 0;
    }
    driveLine(activeCount, weightedSum);
    return;
  }

  if (activeCount >= 4) {
    stopMotors();
    if (nodeStartedMs == 0) {
      nodeStartedMs = now;
    } else if (now - nodeStartedMs >= kNodeConfirmMs) {
      nodeStartedMs = 0;
      executeNodeAction();
    }
    return;
  }
  nodeStartedMs = 0;
  driveLine(activeCount, weightedSum);
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
  hadBluetoothClient = SerialBT.hasClient();
  reportEvent("NEEDS_RESET");
}

void loop() {
  readCommands(Serial, usbBuffer);
  readCommands(SerialBT, bluetoothBuffer);
  updateBluetoothConnection();
  updateButton();

  if (isActiveMotionState() &&
      millis() - routeStartedMs >= kMaximumRouteRuntimeMs) {
    enterError("ROUTE_TIMEOUT");
  }
  if ((isActiveMotionState() || robotState == RobotState::Blocked) &&
      millis() - lastControlMessageMs >= kCommunicationTimeoutMs) {
    enterError("COMMUNICATION_TIMEOUT");
  }

  updateUltrasonic();
  updateLineControl();
  if (!isActiveMotionState()) {
    stopMotors();
  }
  delay(2);
}
