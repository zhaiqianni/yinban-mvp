// Yinban C-001 read-only sensor diagnostic.
//
// This sketch deliberately keeps every motor input LOW. It is safe to run from
// USB without the 14500 batteries installed.

#include <Arduino.h>

namespace Pins {
constexpr uint8_t kLeftMotorForward = 16;
constexpr uint8_t kLeftMotorReverse = 17;
constexpr uint8_t kRightMotorReverse = 26;
constexpr uint8_t kRightMotorForward = 27;
// Five-way line tracker wiring, from module OUT1 through OUT5.
constexpr uint8_t kLine1 = 13;
constexpr uint8_t kLine2 = 18;
constexpr uint8_t kLine3 = 19;
constexpr uint8_t kLine4 = 34;
constexpr uint8_t kLine5 = 35;
// The ESP32 example in the supplied C-001 courseware maps the dedicated
// ultrasonic connector's A0/A1 labels to GPIO33/GPIO32 respectively.
constexpr uint8_t kUltrasonicTrig = 33;
constexpr uint8_t kUltrasonicEcho = 32;
}  // namespace Pins

constexpr unsigned long kReportIntervalMs = 250;
constexpr unsigned long kEchoTimeoutUs = 25000;

unsigned long lastReportMs = 0;

void stopMotors() {
  digitalWrite(Pins::kLeftMotorForward, LOW);
  digitalWrite(Pins::kLeftMotorReverse, LOW);
  digitalWrite(Pins::kRightMotorForward, LOW);
  digitalWrite(Pins::kRightMotorReverse, LOW);
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
  return durationUs * 0.0343F / 2.0F;
}

void setup() {
  pinMode(Pins::kLeftMotorForward, OUTPUT);
  pinMode(Pins::kLeftMotorReverse, OUTPUT);
  pinMode(Pins::kRightMotorForward, OUTPUT);
  pinMode(Pins::kRightMotorReverse, OUTPUT);
  stopMotors();

  // GPIO 34 and 35 are input-only and have no internal pull-ups.
  // The tracking module supplies a digital level, so plain INPUT is required.
  pinMode(Pins::kLine1, INPUT);
  pinMode(Pins::kLine2, INPUT);
  pinMode(Pins::kLine3, INPUT);
  pinMode(Pins::kLine4, INPUT);
  pinMode(Pins::kLine5, INPUT);
  pinMode(Pins::kUltrasonicTrig, OUTPUT);
  pinMode(Pins::kUltrasonicEcho, INPUT);
  digitalWrite(Pins::kUltrasonicTrig, LOW);

  Serial.begin(115200);
  delay(800);
  Serial.println();
  Serial.println("YINBAN_DIAGNOSTIC_READY");
  Serial.println("WIRING: OUT1=13 OUT2=18 OUT3=19 OUT4=34 OUT5=35");
  Serial.println("FORMAT: LINE=[OUT1,OUT2,OUT3,OUT4,OUT5] DISTANCE_CM=<number|NO_ECHO>");
}

void loop() {
  stopMotors();

  const unsigned long nowMs = millis();
  if (nowMs - lastReportMs < kReportIntervalMs) {
    delay(1);
    return;
  }
  lastReportMs = nowMs;

  const int line1 = digitalRead(Pins::kLine1);
  const int line2 = digitalRead(Pins::kLine2);
  const int line3 = digitalRead(Pins::kLine3);
  const int line4 = digitalRead(Pins::kLine4);
  const int line5 = digitalRead(Pins::kLine5);
  const float distanceCm = readDistanceCm();

  Serial.print("LINE=[");
  Serial.print(line1);
  Serial.print(',');
  Serial.print(line2);
  Serial.print(',');
  Serial.print(line3);
  Serial.print(',');
  Serial.print(line4);
  Serial.print(',');
  Serial.print(line5);
  Serial.print("] DISTANCE_CM=");
  if (distanceCm < 0.0F) {
    Serial.println("NO_ECHO");
  } else {
    Serial.println(distanceCm, 1);
  }
}
