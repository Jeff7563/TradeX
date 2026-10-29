# TradeX

ระบบช่วยเทรด XAUUSD / BTCUSD บน MT5 แนว ICT/SMC (ดูกราฟหลักใน TradingView)
1. **ตัวสแกนสัญญาณ** อ่านราคาจาก MT5 แล้วแจ้งเข้า LINE (`scan.bat`)
2. **หน้าเช็กกราฟ** ดูว่าระบบมองเห็นโครงสร้างอะไร (`run.bat`)
3. **บอทเทรด** เข้าออเดอร์ตามสัญญาณบนบัญชี **Demo** (ปิดไว้เป็นค่าเริ่มต้น)

## กฎสัญญาณ v1 (ต้องครบทุกข้อ)
1. ทิศทาง: โครงสร้าง H1 (BOS/CHoCH ล่าสุด) และ D1 ต้องไม่สวนทาง
2. เวลา: แท่งที่ปิดล่าสุดอยู่ใน Kill zone London หรือ New York
3. M15 เพิ่งเกิด BOS/CHoCH ตามทิศทาง (ไม่เกิน 24 แท่ง)
4. การวิ่งนั้นทิ้ง FVG หรือ Order Block ไว้ในโซน Discount (ฝั่งซื้อ) / Premium (ฝั่งขาย)
5. ราคาย้อนกลับมาแตะโซนนั้น
6. SL ตั้งเลยโซนไปเล็กน้อย, TP คือ swing ฝั่งตรงข้าม (liquidity) และต้องได้ RR อย่างน้อย 1:2

ตัวเลขปรับได้ในส่วน `"signals"` ของ `config.json` ทุกสัญญาณถูกบันทึกลง `signals.csv` เพื่อวัดความแม่นภายหลัง
สัญญาณเป็นผลจากกฎอัตโนมัติ ใช้ประกอบการตัดสินใจเท่านั้น

## ทดสอบย้อนหลัง (Backtest)
เปิด MT5 ค้างไว้ แล้วดับเบิลคลิก `backtest.bat` ระบบจะดึงราคาจริงย้อนหลังประมาณ 1 ปี (M15) แล้วจำลองการเทรดตามกฎ
- เข้าที่ราคาเปิดของแท่งถัดไป, ถ้าแท่งเดียวชนทั้ง SL และ TP นับเป็นแพ้, หักค่าสเปรดทุกไม้
- ผลเป็นหน่วย **R** (1R = เงินที่เสี่ยงต่อไม้) เช่น +10R ที่เสี่ยง 0.5%/ไม้ ≈ +5%
- รายงาน: win rate, กำไรรวม, profit factor, drawdown, แพ้ติดกัน, ผลครึ่งแรก/ครึ่งหลัง, ถ้าสเปรดกว้าง 2 เท่า, Monte Carlo, แยกตาม Kill zone และรายเดือน
- ทุกไม้บันทึกใน `backtest_trades.csv` (เปิดด้วย Excel ได้)
- ถ้าได้แท่งน้อยกว่าที่ขอ ให้เปิดกราฟ M15 ใน MT5 แล้วเลื่อนย้อนไปเรื่อยๆ ให้โหลดประวัติก่อน หรือเพิ่ม Tools → Options → Charts → Max bars in chart

ดูผลแล้วถ้า profit factor ต่ำกว่า 1 หรือครึ่งแรก/ครึ่งหลังต่างกันมาก แปลว่ากฎยังไม่พร้อมใช้เงินจริง

## เทียบหลายชุดกฎ (optimize)
ดับเบิลคลิก `optimize.bat` (เปิด MT5 ค้างไว้, ใช้เวลาประมาณ 10–20 นาที) ระบบจะทดสอบกฎ 54 แบบ:
เข้า M15/M5 × โซน FVG/OB/ทั้งคู่ × TP liquidity/2R/3R × มี/ไม่มี liquidity sweep (SL ที่โซนหรือที่ไส้ sweep)
- เลือกชุดที่ดีที่สุดจาก**ครึ่งแรก**ของข้อมูล แล้วดูผลใน**ครึ่งหลัง**ที่ไม่เคยเห็น ชุดที่ผ่านทั้งสองครึ่งจะมีเครื่องหมาย ✓
- ผลสรุปอยู่ใน `optimize_report.txt` และทุกชุดอยู่ใน `optimize_results.csv`
- ถ้ามีชุดที่ผ่าน ระบบจะพิมพ์ค่าที่ใส่ใน `"signals"` ของ config.json ให้ แต่ต้องทดสอบบน Demo ต่ออีกก่อน

## ตรวจความแม่นห้องซิก Telegram
ดับเบิลคลิก `channel_check.bat` (เปิด MT5 ค้างไว้) ระบบจะอ่านหน้าเว็บสาธารณะของช่อง (t.me/s/ชื่อช่อง ไม่ต้องล็อกอิน Telegram) ย้อนหลัง 90 วัน
แล้วเอาทุกซิกที่มี จุดเข้า/TP/SL ไปเทียบกับราคา M1 จริงจาก MT5
- เข้าทันทีถ้าราคาอยู่ในโซนเข้าตอนโพสต์ ไม่งั้นรอราคามาถึงโซนไม่เกิน 4 ชม. (ถ้าวิ่งไป TP1 ก่อนนับว่าเข้าไม่ได้)
- แท่งที่ชนทั้ง SL และ TP นับเป็นโดน SL ก่อน, หักสเปรด
- สรุป: % ชน TP1/TP2/TP3 ก่อน SL, ผลเป็น R ถ้าปิดหมดที่ TP1 หรือแบ่งปิด 3 ส่วน
- ผลอยู่ใน `channel_report.txt` และทุกซิกพร้อมลิงก์โพสต์ใน `channel_trades.csv`
- ช่องอื่น: `channel_check.bat ชื่อช่อง --days 120`
- ตรวจได้เฉพาะโพสต์ที่ยังไม่ถูกลบ

## เปิดบอทเทรด (บัญชี Demo)
ใน `config.json` ส่วน `"trading"`:
```json
"trading": {
  "enabled": true,
  "allow_live": false,
  "risk_percent": 0.5,
  "max_positions_per_symbol": 1,
  "max_trades_per_day": 3,
  "daily_loss_limit_percent": 2.0,
  "max_slippage_points": 30
}
```
- `enabled` เปิด/ปิดการเข้าออเดอร์ (ปิด = แจ้ง LINE อย่างเดียว)
- `allow_live` ต้องเป็น `false` ไว้ บอทจะเข้าออเดอร์เฉพาะบัญชี **Demo** ถ้าล็อกอินบัญชีจริงบอทจะไม่ยิงออเดอร์
- `risk_percent` เสี่ยงกี่ % ของเงินต่อไม้ บอทคำนวณ lot จากระยะ SL ให้เอง
- จำกัดไม้ต่อวัน, ออเดอร์ต่อสัญลักษณ์ และหยุดทั้งวันเมื่อขาดทุนถึง `daily_loss_limit_percent`
- ทุกออเดอร์ตั้ง SL/TP ที่โบรกตั้งแต่ตอนเปิด บันทึกลง `trades.csv` และแจ้งผลเข้า LINE
- ยังไม่มีระบบหลบข่าวแรง (CPI, NFP, FOMC) ช่วงข่าวแนะนำให้ปิด `scan.bat` ไว้ก่อน

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
- `server/signals.py` กฎหาสัญญาณ, `server/notify.py` ส่ง LINE, `server/scanner.py` วนสแกนทุก 30 วินาที, `server/executor.py` ส่งออเดอร์ + คุมความเสี่ยง, `server/backtest.py` ทดสอบย้อนหลัง, `server/optimize.py` เทียบหลายชุดกฎแบบ train/test, `server/channel_check.py` ตรวจห้องซิก Telegram
- `web/` หน้ากราฟ (TradingView Lightweight Charts v4.1.3, Apache-2.0)

> บอทเข้าออเดอร์เฉพาะบัญชี Demo จนกว่าจะผ่านการทดสอบ
