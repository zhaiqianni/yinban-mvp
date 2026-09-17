// Yinban C-001 ultrasonic obstacle-stop diagnostic.
//
// Safety behavior:
//   - Motors stay off until the GPIO25 button is pressed and released.
//   - Both wheels run forward at low duty for at most ten seconds.
//   - Three consecutive valid readings below 25 cm latch a full stop.
//   - Removing the obstacle never restarts the motors automatically.
//   - Pressing GPIO25 at any time latches a full stop.

#include <Arduino.h>

namespace Pins {
// The installed TT motor polarity makes these the physical forward directions.
constexpr uint8_t kLeftForward = 17;
constexpr uint8_t kLeftReverse = 16;
constexpr uint8_t kRightReverse = 27;
constexpr uint8_t kRightForward = 26;
constexpr uint8_t kStopButton = 25;
// Supplied ESP32 courseware: dedicated connector A0/A1 maps to 33/32.
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
constexpr uint8_t kTestDuty = 65;
}  // namespace Pwm

constexpr float kObstacleStopCm = 25.0F;
constexpr uint8_t kObstacleConfirmCount = 3;
constexpr unsigned long kEchoTimeoutUs = 25000;
constexpr unsigned long kSampleIntervalMs = 60;
constexpr unsigned long kMaximumRunMs = 30000;
constexpr unsigned long kButtonDebounceMs = 40;

enum class TestState {
  WaitingForButton,
  Running,
  Stopped,
};

TestState state = TestState::WaitingForButton;
bool previousButtonPressed = false;
unsigned long buttonChangedMs = 0;
unsigned long runStartedMs = 0;
unsigned long lastSampleMs = 0;
uint8_t obstacleCount = 0;

void setupPwm(uint8_t pin, uint8_t channel) {
  ledcSetup(channel, Pwm::kFrequencyHz, Pwm::kResolutionBits);
  ledcAttachPin(pin, channel);
  ledcWrite(channel, 0);
}

void stopMotors() {
  ledcWrite(Pwm::kLeftForwardChannel, 0);
  ledcWrite(Pwm::kLeftReverseChannel, 0);
  ledcWrite(Pwm::kRightForwardChannel, 0);
  ledcWrite(Pwm::kRightReverseChannel, 0);
}

void driveForwardLowSpeed() {
  ledcWrite(Pwm::kLeftReverseChannel, 0);
  ledcWrite(Pwm::kRightReverseChannel, 0);
  ledcWrite(Pwm::kLeftForwardChannel, Pwm::kTestDuty);
  ledcWrite(Pwm::kRightForwardChannel, Pwm::kTestDuty);
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

void latchStop(const char* reason, float distanceCm = -1.0F) {
  stopMotors();
  state = TestState::Stopped;
  Serial.print("STOP:");
  Serial.print(reason);
  if (distanceCm >= 0.0F) {
    Serial.print(" DISTANCE_CM=");
    Serial.print(distanceCm, 1);
  }
  Serial.println();
}

void setup() {
  Serial.begin(115200);
  pinMode(Pins::kStopButton, INPUT_PULLUP);
  pinMode(Pins::kUltrasonicTrig, OUTPUT);
  pinMode(Pins::kUltrasonicEcho, INPUT);
  digitalWrite(Pins::kUltrasonicTrig, LOW);

  setupPwm(Pins::kLeftForward, Pwm::kLeftForwardChannel);
  setupPwm(Pins::kLeftReverse, Pwm::kLeftReverseChannel);
  setupPwm(Pins::kRightReverse, Pwm::kRightReverseChannel);
  setupPwm(Pins::kRightForward, Pwm::kRightForwardChannel);
  stopMotors();

  Serial.println();
  Serial.println("YINBAN_OBSTACLE_STOP_DIAGNOSTIC_READY");
  Serial.println("WIRING: TRIG=33 ECHO=32 BUTTON=25");
  Serial.println("Raise both wheels, keep the path clear, then press and release GPIO25.");
  Serial.println("The test latches STOP below 25 cm and never auto-restarts.");
}

void loop() {
  const unsigned long now = millis();
  const bool buttonPressed = digitalRead(Pins::kStopButton) == LOW;

  if (buttonPressed != previousButtonPressed &&
      now - buttonChangedMs >= kButtonDebounceMs) {
    buttonChangedMs = now;
    previousButtonPressed = buttonPressed;

    if (buttonPressed && state == TestState::Running) {
      latchStop("BUTTON");
      return;
    }

    if (!buttonPressed && state == TestState::WaitingForButton) {
      const float distanceCm = readDistanceCm();
      if (distanceCm > 0.0F && distanceCm < kObstacleStopCm) {
        Serial.print("START_BLOCKED DISTANCE_CM=");
        Serial.println(distanceCm, 1);
        return;
      }

      obstacleCount = 0;
      runStartedMs = now;
      lastSampleMs = 0;
      state = TestState::Running;
      driveForwardLowSpeed();
      Serial.println("START");
    }
  }

  if (state != TestState::Running) {
    stopMotors();
    delay(5);
    return;
  }

  if (now - runStartedMs >= kMaximumRunMs) {
    latchStop("TIME_LIMIT");
    return;
  }

  if (now - lastSampleMs < kSampleIntervalMs) {
    delay(2);
    return;
  }
  lastSampleMs = now;

  const float distanceCm = readDistanceCm();
  Serial.print("RUNNING DISTANCE_CM=");
  if (distanceCm < 0.0F) {
    Serial.println("NO_ECHO");
    obstacleCount = 0;
    return;
  }

  Serial.print(distanceCm, 1);
  Serial.print(" CONFIRM=");
  if (distanceCm < kObstacleStopCm) {
    if (obstacleCount < kObstacleConfirmCount) {
      ++obstacleCount;
    }
  } else {
    obstacleCount = 0;
  }
  Serial.println(obstacleCount);

  if (obstacleCount >= kObstacleConfirmCount) {
    latchStop("OBSTACLE", distanceCm);
  }
}
