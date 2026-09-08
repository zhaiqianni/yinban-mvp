#include <Arduino.h>
#include "BluetoothSerial.h"

#if !defined(CONFIG_BT_ENABLED) || !defined(CONFIG_BLUEDROID_ENABLED)
#error This firmware requires an original ESP32 with Bluetooth Classic support.
#endif

BluetoothSerial SerialBT;

// Adjust these pins to the actual kit schematic before powering the motors.
constexpr uint8_t PIN_STBY = 23;
constexpr uint8_t PIN_PWMA = 25;
constexpr uint8_t PIN_AIN1 = 26;
constexpr uint8_t PIN_AIN2 = 27;
constexpr uint8_t PIN_PWMB = 14;
constexpr uint8_t PIN_BIN1 = 16;
constexpr uint8_t PIN_BIN2 = 17;

constexpr uint8_t LINE_PINS[5] = {32, 33, 34, 35, 39};
constexpr uint8_t PIN_ULTRASONIC_TRIG = 18;
constexpr uint8_t PIN_ULTRASONIC_ECHO = 19;
constexpr uint8_t PIN_LOCAL_BUTTON = 13;

constexpr bool LINE_ACTIVE_LOW = true;
constexpr bool LEFT_MOTOR_REVERSED = false;
constexpr bool RIGHT_MOTOR_REVERSED = true;

constexpr int BASE_SPEED = 105;
constexpr int MAX_SPEED = 175;
constexpr float KP = 24.0f;
constexpr float KD = 16.0f;

constexpr float OBSTACLE_STOP_CM = 20.0f;
constexpr float OBSTACLE_CLEAR_CM = 26.0f;
constexpr uint8_t OBSTACLE_CONFIRM_COUNT = 3;
constexpr uint8_t CLEAR_CONFIRM_COUNT = 5;
constexpr unsigned long ULTRASONIC_INTERVAL_MS = 70;
constexpr unsigned long LINE_LOST_STOP_MS = 500;
constexpr unsigned long FINISH_CONFIRM_MS = 650;
constexpr unsigned long MAX_ROUTE_RUNTIME_MS = 30000;
constexpr unsigned long BUTTON_DEBOUNCE_MS = 250;

enum class RobotState {
  IDLE,
  FOLLOWING,
  BLOCKED,
  LINE_LOST,
  ARRIVED,
  ERROR_STATE
};

RobotState robotState = RobotState::IDLE;
String activeRoute = "";
String usbBuffer = "";
String bluetoothBuffer = "";

float lastLineError = 0.0f;
float lastDistanceCm = -1.0f;
unsigned long routeStartedAt = 0;
unsigned long lineLostSince = 0;
unsigned long finishDetectedSince = 0;
unsigned long lastUltrasonicAt = 0;
unsigned long lastButtonAt = 0;
uint8_t obstacleSamples = 0;
uint8_t clearSamples = 0;

void reportEvent(const String &event) {
  Serial.println(event);
  SerialBT.println(event);
}

void setOneMotor(
  uint8_t pin1,
  uint8_t pin2,
  uint8_t pwmPin,
  int speed,
  bool reversed
) {
  int requested = constrain(speed, -MAX_SPEED, MAX_SPEED);
  if (reversed) {
    requested = -requested;
  }
  if (requested > 0) {
    digitalWrite(pin1, HIGH);
    digitalWrite(pin2, LOW);
  } else if (requested < 0) {
    digitalWrite(pin1, LOW);
    digitalWrite(pin2, HIGH);
  } else {
    digitalWrite(pin1, LOW);
    digitalWrite(pin2, LOW);
  }
  analogWrite(pwmPin, abs(requested));
}

void drive(int leftSpeed, int rightSpeed) {
  digitalWrite(PIN_STBY, HIGH);
  setOneMotor(
    PIN_AIN1,
    PIN_AIN2,
    PIN_PWMA,
    leftSpeed,
    LEFT_MOTOR_REVERSED
  );
  setOneMotor(
    PIN_BIN1,
    PIN_BIN2,
    PIN_PWMB,
    rightSpeed,
    RIGHT_MOTOR_REVERSED
  );
}

void stopMotors() {
  analogWrite(PIN_PWMA, 0);
  analogWrite(PIN_PWMB, 0);
  digitalWrite(PIN_AIN1, LOW);
  digitalWrite(PIN_AIN2, LOW);
  digitalWrite(PIN_BIN1, LOW);
  digitalWrite(PIN_BIN2, LOW);
  digitalWrite(PIN_STBY, LOW);
}

bool sensorOnLine(uint8_t pin) {
  bool high = digitalRead(pin) == HIGH;
  return LINE_ACTIVE_LOW ? !high : high;
}

float measureDistanceCm() {
  digitalWrite(PIN_ULTRASONIC_TRIG, LOW);
  delayMicroseconds(2);
  digitalWrite(PIN_ULTRASONIC_TRIG, HIGH);
  delayMicroseconds(10);
  digitalWrite(PIN_ULTRASONIC_TRIG, LOW);

  unsigned long duration = pulseIn(PIN_ULTRASONIC_ECHO, HIGH, 25000);
  if (duration == 0) {
    return -1.0f;
  }
  return duration * 0.0343f / 2.0f;
}

void enterIdle(const String &message) {
  stopMotors();
  robotState = RobotState::IDLE;
  routeStartedAt = 0;
  lineLostSince = 0;
  finishDetectedSince = 0;
  obstacleSamples = 0;
  clearSamples = 0;
  reportEvent(message);
}

void startCardiologyRoute() {
  activeRoute = "CARDIOLOGY";
  robotState = RobotState::FOLLOWING;
  routeStartedAt = millis();
  lineLostSince = 0;
  finishDetectedSince = 0;
  obstacleSamples = 0;
  clearSamples = 0;
  lastLineError = 0.0f;
  reportEvent("MOVING");
}

void handleCommand(String command) {
  command.trim();
  command.toUpperCase();
  if (command.length() == 0) {
    return;
  }
  if (command == "PING") {
    reportEvent("READY");
    return;
  }
  if (command == "STOP") {
    enterIdle("READY");
    return;
  }
  if (command == "RESET") {
    activeRoute = "";
    enterIdle("READY");
    return;
  }
  if (command == "RESUME") {
    if (
      robotState == RobotState::BLOCKED &&
      lastDistanceCm >= OBSTACLE_CLEAR_CM
    ) {
      robotState = RobotState::FOLLOWING;
      obstacleSamples = 0;
      clearSamples = 0;
      reportEvent("MOVING");
    } else {
      reportEvent("ERROR:RESUME_NOT_ALLOWED");
    }
    return;
  }
  if (command.startsWith("START:")) {
    String route = command.substring(6);
    if (route == "CARDIOLOGY") {
      startCardiologyRoute();
    } else {
      reportEvent("ERROR:UNSUPPORTED_ROUTE");
    }
    return;
  }
  reportEvent("ERROR:UNKNOWN_COMMAND");
}

void readCommands(Stream &stream, String &buffer) {
  while (stream.available()) {
    char current = static_cast<char>(stream.read());
    if (current == '\n' || current == '\r') {
      if (buffer.length() > 0) {
        handleCommand(buffer);
        buffer = "";
      }
    } else if (buffer.length() < 80) {
      buffer += current;
    } else {
      buffer = "";
      reportEvent("ERROR:COMMAND_TOO_LONG");
    }
  }
}

void updateObstacleState() {
  if (millis() - lastUltrasonicAt < ULTRASONIC_INTERVAL_MS) {
    return;
  }
  lastUltrasonicAt = millis();
  lastDistanceCm = measureDistanceCm();
  if (lastDistanceCm < 0) {
    return;
  }

  if (robotState == RobotState::FOLLOWING) {
    if (lastDistanceCm <= OBSTACLE_STOP_CM) {
      obstacleSamples++;
      if (obstacleSamples >= OBSTACLE_CONFIRM_COUNT) {
        stopMotors();
        robotState = RobotState::BLOCKED;
        clearSamples = 0;
        reportEvent("BLOCKED:" + String(lastDistanceCm, 1));
      }
    } else {
      obstacleSamples = 0;
    }
  } else if (robotState == RobotState::BLOCKED) {
    if (lastDistanceCm >= OBSTACLE_CLEAR_CM) {
      clearSamples++;
      if (clearSamples >= CLEAR_CONFIRM_COUNT) {
        robotState = RobotState::FOLLOWING;
        obstacleSamples = 0;
        reportEvent("MOVING");
      }
    } else {
      clearSamples = 0;
    }
  }
}

void updateLineFollowing() {
  if (robotState != RobotState::FOLLOWING) {
    return;
  }

  bool line[5];
  int activeCount = 0;
  int weightedSum = 0;
  const int weights[5] = {-2, -1, 0, 1, 2};

  for (uint8_t index = 0; index < 5; index++) {
    line[index] = sensorOnLine(LINE_PINS[index]);
    if (line[index]) {
      activeCount++;
      weightedSum += weights[index];
    }
  }

  if (activeCount == 5) {
    if (finishDetectedSince == 0) {
      finishDetectedSince = millis();
    }
    if (millis() - finishDetectedSince >= FINISH_CONFIRM_MS) {
      stopMotors();
      robotState = RobotState::ARRIVED;
      reportEvent("ARRIVED:" + activeRoute);
    }
    return;
  }
  finishDetectedSince = 0;

  if (activeCount == 0) {
    if (lineLostSince == 0) {
      lineLostSince = millis();
    }
    if (millis() - lineLostSince >= LINE_LOST_STOP_MS) {
      stopMotors();
      robotState = RobotState::LINE_LOST;
      reportEvent("LINE_LOST");
      return;
    }
    int searchTurn = lastLineError < 0 ? -45 : 45;
    drive(BASE_SPEED - searchTurn, BASE_SPEED + searchTurn);
    return;
  }

  lineLostSince = 0;
  float error = static_cast<float>(weightedSum) / activeCount;
  float derivative = error - lastLineError;
  float correction = KP * error + KD * derivative;
  lastLineError = error;

  int leftSpeed = static_cast<int>(BASE_SPEED + correction);
  int rightSpeed = static_cast<int>(BASE_SPEED - correction);
  drive(leftSpeed, rightSpeed);
}

void updateLocalButton() {
  if (digitalRead(PIN_LOCAL_BUTTON) != LOW) {
    return;
  }
  if (millis() - lastButtonAt < BUTTON_DEBOUNCE_MS) {
    return;
  }
  lastButtonAt = millis();
  if (robotState == RobotState::IDLE || robotState == RobotState::ARRIVED) {
    startCardiologyRoute();
  } else {
    enterIdle("READY");
  }
}

void setup() {
  Serial.begin(115200);
  SerialBT.begin("YINBAN_ROBOT");

  pinMode(PIN_STBY, OUTPUT);
  pinMode(PIN_PWMA, OUTPUT);
  pinMode(PIN_AIN1, OUTPUT);
  pinMode(PIN_AIN2, OUTPUT);
  pinMode(PIN_PWMB, OUTPUT);
  pinMode(PIN_BIN1, OUTPUT);
  pinMode(PIN_BIN2, OUTPUT);

  for (uint8_t index = 0; index < 5; index++) {
    pinMode(LINE_PINS[index], INPUT);
  }
  pinMode(PIN_ULTRASONIC_TRIG, OUTPUT);
  pinMode(PIN_ULTRASONIC_ECHO, INPUT);
  pinMode(PIN_LOCAL_BUTTON, INPUT_PULLUP);

  stopMotors();
  delay(250);
  reportEvent("READY");
}

void loop() {
  readCommands(Serial, usbBuffer);
  readCommands(SerialBT, bluetoothBuffer);
  updateLocalButton();

  if (
    robotState == RobotState::FOLLOWING ||
    robotState == RobotState::BLOCKED
  ) {
    updateObstacleState();
  }

  if (robotState == RobotState::FOLLOWING) {
    if (millis() - routeStartedAt > MAX_ROUTE_RUNTIME_MS) {
      stopMotors();
      robotState = RobotState::ERROR_STATE;
      reportEvent("ERROR:ROUTE_TIMEOUT");
      return;
    }
    updateLineFollowing();
  } else {
    stopMotors();
  }
}
