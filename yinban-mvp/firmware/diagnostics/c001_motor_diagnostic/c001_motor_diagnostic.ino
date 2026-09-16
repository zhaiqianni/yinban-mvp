// Yinban C-001 low-speed motor diagnostic.
//
// Safety sequence:
//   1. Flash from USB with the 14500 batteries removed.
//   2. Disconnect USB, raise both wheels, then connect the battery pack.
//   3. The test waits eight seconds and runs once only.

#include <Arduino.h>

namespace Pins {
constexpr uint8_t kLeftForward = 16;
constexpr uint8_t kLeftReverse = 17;
constexpr uint8_t kRightReverse = 26;
constexpr uint8_t kRightForward = 27;
}  // namespace Pins

namespace Pwm {
constexpr uint8_t kLeftForwardChannel = 0;
constexpr uint8_t kLeftReverseChannel = 1;
constexpr uint8_t kRightReverseChannel = 2;
constexpr uint8_t kRightForwardChannel = 3;
constexpr uint32_t kFrequencyHz = 2000;
constexpr uint8_t kResolutionBits = 8;
constexpr uint8_t kLowDuty = 90;  // 35% of the 8-bit PWM range.
}  // namespace Pwm

constexpr unsigned long kArmingDelayMs = 8000;
constexpr unsigned long kPulseMs = 700;
constexpr unsigned long kPauseMs = 1800;

void writeMotor(uint8_t forwardChannel, uint8_t reverseChannel,
                int16_t command) {
  const uint8_t duty = static_cast<uint8_t>(abs(command));
  if (command > 0) {
    ledcWrite(reverseChannel, 0);
    ledcWrite(forwardChannel, duty);
  } else if (command < 0) {
    ledcWrite(forwardChannel, 0);
    ledcWrite(reverseChannel, duty);
  } else {
    ledcWrite(forwardChannel, 0);
    ledcWrite(reverseChannel, 0);
  }
}

void setLeft(int16_t command) {
  writeMotor(Pwm::kLeftForwardChannel, Pwm::kLeftReverseChannel, command);
}

void setRight(int16_t command) {
  writeMotor(Pwm::kRightForwardChannel, Pwm::kRightReverseChannel, command);
}

void stopAll() {
  setLeft(0);
  setRight(0);
}

void pulse(const char* label, int16_t left, int16_t right) {
  Serial.println(label);
  setLeft(left);
  setRight(right);
  delay(kPulseMs);
  stopAll();
  Serial.println("STOP");
  delay(kPauseMs);
}

void setupPwm(uint8_t pin, uint8_t channel) {
  ledcSetup(channel, Pwm::kFrequencyHz, Pwm::kResolutionBits);
  ledcAttachPin(pin, channel);
  ledcWrite(channel, 0);
}

void setup() {
  Serial.begin(115200);

  setupPwm(Pins::kLeftForward, Pwm::kLeftForwardChannel);
  setupPwm(Pins::kLeftReverse, Pwm::kLeftReverseChannel);
  setupPwm(Pins::kRightReverse, Pwm::kRightReverseChannel);
  setupPwm(Pins::kRightForward, Pwm::kRightForwardChannel);
  stopAll();

  Serial.println();
  Serial.println("YINBAN_MOTOR_DIAGNOSTIC_READY");
  Serial.println("Raise both wheels. Test begins in 8 seconds and runs once.");
  delay(kArmingDelayMs);

  pulse("TEST 1/5: LEFT FORWARD", Pwm::kLowDuty, 0);
  pulse("TEST 2/5: LEFT REVERSE", -Pwm::kLowDuty, 0);
  pulse("TEST 3/5: RIGHT FORWARD", 0, Pwm::kLowDuty);
  pulse("TEST 4/5: RIGHT REVERSE", 0, -Pwm::kLowDuty);
  pulse("TEST 5/5: BOTH FORWARD", Pwm::kLowDuty, Pwm::kLowDuty);

  stopAll();
  Serial.println("MOTOR_DIAGNOSTIC_COMPLETE");
  Serial.println("Motors are locked off until the next reset or power cycle.");
}

void loop() {
  stopAll();
  delay(20);
}
