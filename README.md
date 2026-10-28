# TradeX

ระบบช่วยเทรด XAUUSD / BTCUSD บน MT5 แนว ICT/SMC (ดูกราฟหลักใน TradingView)
1. **ตัวสแกนสัญญาณ** อ่านราคาจาก MT5 แล้วแจ้งเข้า LINE (`scan.bat`)
2. **หน้าเช็กกราฟ** ดูว่าระบบมองเห็นโครงสร้างอะไร (`run.bat`)
3. บอทเทรดบัญชีทดลอง (กำลังทำ)

## กฎสัญญาณ v1 (ต้องครบทุกข้อ)
1. ทิศทาง: โครงสร้าง H1 (BOS/CHoCH ล่าสุด) และ D1 ต้องไม่สวนทาง
2. เวลา: แท่งที่ปิดล่าสุดอยู่ใน Kill zone London หรือ New York
3. M15 เพิ่งเกิด BOS/CHoCH ตามทิศทาง (ไม่เกิน 24 แท่ง)
4. การวิ่งนั้นทิ้ง FVG หรือ Order Block ไว้ในโซน Discount (ฝั่งซื้อ) / Premium (ฝั่งขาย)
5. ราคาย้อนกลับมาแตะโซนนั้น
6. SL ตั้งเลยโซนไปเล็กน้อย, TP คือ swing ฝั่งตรงข้าม (liquidity) และต้องได้ RR อย่างน้อย 1:2

ตัวเลขปรับได้ในส่วน `"signals"` ของ `config.json` ทุกสัญญาณถูกบันทึกลง `signals.csv` เพื่อวัดความแม่นภายหลัง
สัญญาณเป็นผลจากกฎอัตโนมัติ ใช้ประกอบการตัดสินใจเท่านั้น

## ตั้งค่า LINE (ทำครั้งเดียว)
1. เข้า https://manager.line.biz สร้าง LINE Official Account (ฟรี)
2. ในหน้าบัญชี OA ไปที่ ตั้งค่า → Messaging API → กดเปิดใช้งาน (สร้าง Provider ชื่ออะไรก็ได้)
3. เข้า https://developers.line.biz/console เลือก Channel ที่เพิ่งสร้าง
   - แท็บ **Messaging API** เลื่อนลงล่างสุด กด Issue **Channel access token** แล้วคัดลอก
   - แท็บ **Basic settings** เลื่อนลงหา **Your user ID** (ขึ้นต้นด้วย U) แล้วคัดลอก
4. สแกน QR ในแท็บ Messaging API เพื่อเพิ่ม OA เป็นเพื่อนใน LINE ของคุณ
5. ใส่ค่าใน `config.json`:
   ```json
   "line": { "channel_access_token": "ค่าที่คัดลอก", "user_id": "Uxxxxxxxx" }
   ```
6. ทดสอบ: เปิด Command Prompt ในโฟลเดอร์นี้ แล้วพิมพ์ `.venv\Scripts\python -m server.scanner --test-line`

แพ็กเกจฟรีของ LINE OA มีโควตาส่งข้อความต่อเดือนจำกัด (ดูได้ในหน้า OA Manager) พอสำหรับแจ้งสัญญาณวันละไม่กี่ครั้ง
**อย่าส่ง config.json ให้ใคร** เพราะมี token ของ LINE อยู่

## สิ่งที่แสดงบนกราฟ
- **BOS / CHoCH** (เส้นทึบ = BOS, เส้นประ = CHoCH) นับเมื่อแท่งเทียน *ปิด* ทะลุ swing
- **FVG** ที่ยังไม่ถูกเติมเต็ม
- **Order Block** (+OB / -OB) แท่งตรงข้ามแท่งสุดท้ายก่อนเกิด BOS/CHoCH ที่ยังไม่ถูกทำลาย
- **Premium / Discount** จาก swing high/low ล่าสุด พร้อมเส้น EQ 50%
- **Kill zone** London (LDN) และ New York (NY) ปรับตามเวลาออมแสงของนิวยอร์กให้อัตโนมัติ
- เวลาบนกราฟเป็นเวลาไทย (UTC+7)

## ติดตั้งบนคอม Windows
1. ติดตั้ง [Python 3.11 ขึ้นไป](https://www.python.org/downloads/) (ติ๊ก "Add python.exe to PATH" ตอนติดตั้ง)
2. เปิด MT5 แล้วล็อกอินบัญชี **Demo** ไว้
3. ใน MT5 ไปที่ Tools → Options → Expert Advisors แล้วติ๊ก **Allow algorithmic trading**
4. ดาวน์โหลดโค้ดนี้ (ปุ่ม Code → Download ZIP) แล้วแตกไฟล์
5. ดับเบิลคลิก `scan.bat` (ตัวสแกนสัญญาณ) หรือ `run.bat` (หน้าเช็กกราฟที่ http://localhost:8000) ครั้งแรกจะติดตั้งแพ็กเกจให้เอง
6. แก้ไฟล์ `config.json` ที่สร้างขึ้น:
   - `"source": "mt5"` เพื่อใช้ราคาจริงจาก MT5 (ค่าเริ่มต้น `"sim"` คือราคาจำลองสำหรับทดสอบเท่านั้น)
   - `"symbols"` ใส่ชื่อสัญลักษณ์ตามที่เห็นใน Market Watch ของ MT5 เช่น Exness บัญชี Standard มักเป็น `XAUUSDm`, `BTCUSDm`
   - `"server_utc_offset_hours"` เวลาเซิร์ฟเวอร์ของโบรกห่างจาก UTC กี่ชั่วโมง (Exness = 0)
7. ปิดหน้าต่างดำแล้วดับเบิลคลิกใหม่

ถ้ามุมขวาบนเขียนว่า **SIM (ราคาจำลอง)** แปลว่ายังไม่ได้ต่อ MT5 ราคาที่เห็นเป็นของปลอม

## สำหรับนักพัฒนา
```
pip install -r requirements.txt
TRADEX_SOURCE=sim python -m uvicorn server.app:app --port 8000
python -m pytest
```
- `server/datasource.py` ดึงแท่งเทียนจาก MT5 (หรือข้อมูลจำลอง)
- `server/smc.py` คำนวณ swing, BOS/CHoCH, FVG, OB, premium/discount, kill zone
- `server/app.py` เว็บเซิร์ฟเวอร์ + WebSocket ส่งข้อมูลทุก 1 วินาที
- `server/signals.py` กฎหาสัญญาณ, `server/notify.py` ส่ง LINE, `server/scanner.py` วนสแกนทุก 30 วินาที
- `web/` หน้ากราฟ (TradingView Lightweight Charts v4.1.3, Apache-2.0)

> ตอนนี้ระบบแค่แจ้งสัญญาณ ยังไม่มีการส่งคำสั่งซื้อขาย
