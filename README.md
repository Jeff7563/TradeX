# TradeX

กราฟเรียลไทม์ XAUUSD / BTCUSD จาก MT5 พร้อมจุด ICT/SMC อัตโนมัติ
(ส่วนแรกของระบบ: กราฟ → สัญญาณแจ้ง LINE → บอทเทรดบัญชีทดลอง)

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
5. ดับเบิลคลิก `run.bat` ครั้งแรกจะติดตั้งแพ็กเกจให้เอง แล้วเปิดเบราว์เซอร์ที่ http://localhost:8000
6. แก้ไฟล์ `config.json` ที่สร้างขึ้น:
   - `"source": "mt5"` เพื่อใช้ราคาจริงจาก MT5 (ค่าเริ่มต้น `"sim"` คือราคาจำลองสำหรับทดสอบเท่านั้น)
   - `"symbols"` ใส่ชื่อสัญลักษณ์ตามที่เห็นใน Market Watch ของ MT5 เช่น Exness บัญชี Standard มักเป็น `XAUUSDm`, `BTCUSDm`
   - `"server_utc_offset_hours"` เวลาเซิร์ฟเวอร์ของโบรกห่างจาก UTC กี่ชั่วโมง (Exness = 0)
7. ปิดหน้าต่างดำแล้วดับเบิลคลิก `run.bat` ใหม่

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
- `web/` หน้ากราฟ (TradingView Lightweight Charts v4.1.3, Apache-2.0)

> ระบบนี้ใช้เพื่อการวิเคราะห์และทดสอบ ยังไม่มีการส่งคำสั่งซื้อขาย
