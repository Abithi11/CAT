# Smart Rental Tracking System

## Background:
In industries like construction and mining, companies often rent machinery and tools instead of owning them through our registered dealers. However, managing these rentals - tracking where the equipment is, who's using it, when its due to return and predicting upcoming demand - is still largely manual or spreadsheet based.

This results in:
* Equipment being lost or unaccounted for.
* Delays and downtime due to misallocation.
* Unexpected rental extension and costs

## Challenge:
**Design a smart asset rental tracking system that can help companies:**
* Track and monitor rented equipment in real time.
* Predict demand, flag under-utilized assets and optimize rentals.
* Log usage and conditions.

## Expected outcomes:
* **Asset Dashboard:** List of all rented equipment with live status. (You can assume that the data is real time)
* **Check in/Check out system:** based on QR code/RFID simulation/user entry
* **Usage Logging:** Runtime hours, Fuel usage, Location, Idle hours etc.
* **Summary** of total rented hours, usage per site, downtime.
* **Overdue alerts and notification:** Remind users when return time is approaching.
* **Demand Forecasting:** Help companies pre-position equipment by predicting which tools/machines will be needed at certain sites/times.
* **Anomaly Detection:** Use the historical data to detect any misuse of assets eg) long idle hours, unassigned equipment etc.

| Equipment ID | Type | Site ID | Check-In Date | Check-Out Date | Engine Hours/Day | Idle Hours/Day | Rental Days | Last Operator ID |
|---|---|---|---|---|---|---|---|---|
| EQX1001 | Excavator | S003 | 2025-04-01 | 2025-04-16 | 1.5 | 10 | 15 | OP101 |
| EQX1002 | Crane | NULL | 2025-03-10 | 2025-03-30 | 0 | 11 | 20 | NULL |
| EQX1003 | Bulldozer | S002 | 2025-02-15 | 2025-03-11 | 7.5 | 0.5 | 25 | OP203 |
| EQX1004 | Excavator | S004 | 2025-05-05 | 2025-05-15 | 2 | 9 | 10 | OP106 |
| EQX1005 | Bulldozer | S006 | 2025-01-01 | 2025-01-31 | 8 | 0 | 30 | OP301 |
| EQX1006 | Grader | S001 | 2025-04-05 | 2025-04-23 | 3 | 6 | 18 | OP114 |
| EQX1007 | Excavator | NULL | 2025-03-20 | 2025-04-01 | 0 | 12 | 12 | NULL |
