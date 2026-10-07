# Battery display

Both charts use a fixed 3.0–4.2 V scale for a standard 1S LiPo. This is a chart scale, not a charging/discharging safety setting. It does not change the radio, charger, readings, polling, or scheduled reports.

The displayed percentage is an approximate voltage-based indicator. The implementation interpolates between the generic points below. They are a MeshcoreStation display heuristic, not a calibrated curve for your particular cell. Charging, load, temperature, aging, and cell chemistry can shift the result. A measured fuel-gauge state of charge would be preferable if available.

| Voltage | Estimate |
| --- | --- |
| 3.00 V | 0% |
| 3.30 V | 2% |
| 3.50 V | 5% |
| 3.60 V | 10% |
| 3.70 V | 20% |
| 3.75 V | 30% |
| 3.80 V | 40% |
| 3.85 V | 50% |
| 3.90 V | 60% |
| 3.95 V | 70% |
| 4.00 V | 80% |
| 4.10 V | 90% |
| 4.20 V | 100% |

Missing readings have no percentage. Voltages outside 3.0–4.2 V retain their actual numeric value and are labeled outside the estimate range; red edge markers identify them on the fixed-scale chart. They are not silently converted to 0% or 100%. Failed readings and long sampling gaps still break the line.

The curve is centralized in `meshcorestation/web/assets/ab_battery.js`. Stored measurements remain unchanged. The main panel refreshes saved history every 15 seconds, without issuing extra radio requests.

Background on standard single-cell voltage and the distinction between voltage and a fuel gauge:
- https://learn.sparkfun.com/tutorials/photon-battery-shield-hookup-guide/all
- https://docs.sparkfun.com/SparkFun_Thing_Plus_RA6M5/hardware_overview/
