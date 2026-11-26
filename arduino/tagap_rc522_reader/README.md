# TAGAP RC522 Reader

## Wiring

| RC522 | Arduino Uno |
|---|---|
| 3.3V | 3.3V |
| RST | D9 |
| GND | GND |
| MISO | D12 |
| MOSI | D11 |
| SCK | D13 |
| SDA / SS | D10 |

Connect the buzzer signal to **D5** and its ground to **GND**.

The RC522 is a 3.3V device. Do not connect its power pin to 5V. The Uno uses
5V logic, so use appropriate level shifting on the Uno-to-RC522 signal lines
(SCK, MOSI, SDA/SS, and RST) to protect the reader.

## Upload

1. Install the **MFRC522** library (by GithubCommunity) in Arduino IDE.
2. Open `tagap_rc522_reader.ino`, select **Arduino Uno** and its USB port, then
   upload the sketch.
3. Start TAGAP. It will identify the reader by USB serial handshake and connect
   automatically; the reader uses **9600 baud**.
4. Scan a card. The Arduino prints `UID:` followed by the uppercase hexadecimal
   UID. It briefly sounds the buzzer. TAGAP also checks the RC522 chip response
   before considering the reader ready.

## Confirm the handshake manually

1. Close TAGAP so it releases the COM port, then open Arduino IDE **Serial
   Monitor** for the Arduino's port and choose **9600 baud**.
2. After reset, expect `TAGAP_READER/1;RC522=OK`. If it prints
   `TAGAP_READER/1;RC522=ERROR`, the Arduino is running the TAGAP firmware but
   cannot detect the RC522 over SPI.
3. Set the Serial Monitor line ending to **Newline**, type `TAGAP_PING`, and
   send it. The same `...RC522=OK` response confirms the ping/response handshake.
   A card scan should print `UID:` followed by hex characters.
4. Close Serial Monitor before starting TAGAP; only one application can own
   the COM port at a time.

If the reader is missing at startup, TAGAP keeps a reconnect dialog open. You
can retry after plugging it in or continue in **Simulation Mode**, where both
RFID and SMS are simulated and no real messages are sent.
