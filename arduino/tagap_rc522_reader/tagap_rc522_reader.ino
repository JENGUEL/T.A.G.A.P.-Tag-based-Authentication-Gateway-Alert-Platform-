#include <SPI.h>
#include <MFRC522.h>

constexpr byte RFID_SS_PIN = 10;
constexpr byte RFID_RST_PIN = 9;
constexpr byte BUZZER_PIN = 5;
constexpr unsigned long SERIAL_BAUD_RATE = 9600;

MFRC522 reader(RFID_SS_PIN, RFID_RST_PIN);
bool readerReady = false;

void reportReaderStatus() {
  const byte version = reader.PCD_ReadRegister(MFRC522::VersionReg);
  readerReady = version != 0x00 && version != 0xFF;
  Serial.println(readerReady
    ? "TAGAP_READER/1;RC522=OK"
    : "TAGAP_READER/1;RC522=ERROR");
}

void setup() {
  Serial.begin(SERIAL_BAUD_RATE);
  Serial.setTimeout(50);
  SPI.begin();
  reader.PCD_Init();
  pinMode(BUZZER_PIN, OUTPUT);
  reportReaderStatus();
}

void loop() {
  if (Serial.available()) {
    String command = Serial.readStringUntil('\n');
    command.trim();
    if (command == "TAGAP_PING") {
      reportReaderStatus();
    }
  }

  if (!readerReady) {
    delay(100);
    return;
  }

  if (!reader.PICC_IsNewCardPresent() || !reader.PICC_ReadCardSerial()) {
    return;
  }

  Serial.print("UID:");
  for (byte index = 0; index < reader.uid.size; index++) {
    if (reader.uid.uidByte[index] < 0x10) {
      Serial.print('0');
    }
    Serial.print(reader.uid.uidByte[index], HEX);
  }
  Serial.println();

  tone(BUZZER_PIN, 2200, 100);
  delay(120);
  noTone(BUZZER_PIN);

  reader.PICC_HaltA();
  reader.PCD_StopCrypto1();
  delay(300);
}
