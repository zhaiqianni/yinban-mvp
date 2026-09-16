// Yinban C-001 first low-speed five-sensor line-following diagnostic.
//
// Safety behavior:
//   - Motors remain off for eight seconds after power-up.
//   - The run is limited to ten seconds and never repeats automatically.
//   - Losing the line for 150 ms, seeing all five sensors on black, or pressing
//     the GPIO 25 button stops both motors and ends the run.

#include <Arduino.h>

namespace Pins {
constexpr uint8_t kLine[5] = {13, 18, 19, 34, 35};
// The installed TT motor polarity makes these the physical forward directions.
constexpr uint8_t kLeftForward = 17;
constexpr uint8_t kLeftReverse = 16;
constexpr uint8_t kRightReverse = 27;
constexpr uint8_t kRightForward = 26;
constexpr uint8_t kStopButton = 25;
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
constexpr unsigned long kArmingDelayMs = 8000;
constexpr unsigned long kMaximumRunMs = 10000;
constexpr unsigned long kLineLostStopMs = 150;
constexpr unsigned long kReportIntervalMs = 100;

bool testFinished = false;
unsigned long runStartedMs = 0;
unsigned long lineLostStartedMs = 0;
unsigned long lastReportMs = 0;
float previousError = 0.0F;

void setupPwm(uint8_t pin, uint8_t channel) {
  ledcSetup(channel, Pwm::kFrequencyHz, Pwm::kResolutionBits);
  ledcAttachPin(pin, channel);
  ledcWrite(channel, 0);
}

void writeMotor(uint8_t forwardChannel, uint8_t reverseChannel, int command) {
  command = constrain(command, -kMaximumDuty, kMaximumDuty);
  if (command > 0) {
    const int duty = max(command, kMinimumDuty);
    ledcWrite(reverseChannel, 0);
    ledcWrite(forwardChannel, duty);
  } else if (command < 0) {
    const int duty = max(-command, kMinimumDuty);
    ledcWrite(forwardChannel, 0);
    ledcWrite(reverseChannel, duty);
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

bool sensorOnBlack(uint8_t pin) {
  const bool isHigh = digitalRead(pin) == HIGH;
  return kBlackIsLow ? !isHigh : isHigh;
}

void finishTest(const char* reason) {
  stopMotors();
  testFinished = true;
  Serial.print("STOP:");
  Serial.println(reason);
}

void reportSensors(const bool line[5], int left, int right) {
  const unsigned long now = millis();
  if (now - lastReportMs < kReportIntervalMs) {
    return;
  }
  lastReportMs = now;

  Serial.print("LINE=[");
  for (uint8_t index = 0; index < 5; ++index) {
    Serial.print(line[index] ? '1' : '0');
    if (index < 4) {
      Serial.print(',');
    }
  }
  Serial.print("] MOTOR=[");
  Serial.print(left);
  Serial.print(',');
  Serial.print(right);
  Serial.println(']');
}

void setup() {
  Serial.begin(115200);

  for (uint8_t pin : Pins::kLine) {
    pinMode(pin, INPUT);
  }
  pinMode(Pins::kStopButton, INPUT_PULLUP);

  setupPwm(Pins::kLeftForward, Pwm::kLeftForwardChannel);
  setupPwm(Pins::kLeftReverse, Pwm::kLeftReverseChannel);
  setupPwm(Pins::kRightReverse, Pwm::kRightReverseChannel);
  setupPwm(Pins::kRightForward, Pwm::kRightForwardChannel);
  stopMotors();

  Serial.println();
  Serial.println("YINBAN_LINE_FOLLOW_DIAGNOSTIC_READY");
  Serial.println("Place the center sensor over the black line.");
  Serial.println("Low-speed run begins in 8 seconds and ends after 10 seconds.");
  delay(kArmingDelayMs);

  bool anySensorOnBlack = false;
  for (uint8_t pin : Pins::kLine) {
    anySensorOnBlack = anySensorOnBlack || sensorOnBlack(pin);
  }
  if (!anySensorOnBlack) {
    finishTest("NO_LINE_AT_START");
    return;
  }

  runStartedMs = millis();
  Serial.println("START");
}

void loop() {
  if (testFinished) {
    stopMotors();
    delay(20);
    return;
  }

  if (digitalRead(Pins::kStopButton) == LOW) {
    finishTest("BUTTON");
    return;
  }

  const unsigned long now = millis();
  if (now - runStartedMs >= kMaximumRunMs) {
    finishTest("TIME_LIMIT");
    return;
  }

  bool line[5];
  int activeCount = 0;
  int weightedSum = 0;
  const int weights[5] = {-2, -1, 0, 1, 2};

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

  if (activeCount == 5) {
    finishTest("WIDE_BLACK_MARK");
    return;
  }

  if (activeCount == 0) {
    stopMotors();
    reportSensors(line, 0, 0);
    if (lineLostStartedMs == 0) {
      lineLostStartedMs = now;
    } else if (now - lineLostStartedMs >= kLineLostStopMs) {
      finishTest("LINE_LOST");
    }
    delay(5);
    return;
  }

  lineLostStartedMs = 0;
  const float error = static_cast<float>(weightedSum) / activeCount;
  const float correction =
      kProportionalGain * error +
      kDerivativeGain * (error - previousError);
  previousError = error;

  const int left = constrain(
      static_cast<int>(kBaseDuty + correction),
      kMinimumDuty,
      kMaximumDuty);
  const int right = constrain(
      static_cast<int>(kBaseDuty - correction),
      kMinimumDuty,
      kMaximumDuty);

  drive(left, right);
  reportSensors(line, left, right);
  delay(5);
}
