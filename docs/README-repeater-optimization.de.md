# Repeater Optimizer in V4

Die Startseite enthält einen eigenen Bereich **Repeater Optimizer** mit drei
unabhängig aufklappbaren Unterbereichen. Alle verwenden den in Repeater Management
ausgewählten Repeater. Geschlossene Bereiche laden keine neuen Ansichten.

- **Repeater Statistics** zeigt lokal empfangene, passive Beobachtungen und Charts.
- **Optimization Analysis** zeigt Rollen, Nachbarn, Hop-Limit-Analysen, Empfehlungen
  und Vorher/Nachher-Vergleiche. Nachbarabfragen sind standardmäßig manuell;
  vorhandene ausdrücklich aktivierte Zeitpläne bleiben erhalten.
- **Repeater Network Monitoring** zeigt externe Analyzer-Beobachtungen. Die Funktion
  ist experimentell, ohne separate Aktivierung verfügbar und nicht live verifiziert.

Für geschützte Analyseaktionen **Connect as administrator** verwenden, anmelden und
im Verwaltungsfenster **Return to Optimization Analysis** wählen. Änderungen müssen
bestätigt werden; aktuelle Werte werden vorher geprüft und danach zurückgelesen.
Es gibt keine automatische Anwendung von Empfehlungen. **Disconnect administrator**
beendet die Sitzung. Beim Wechsel des Repeaters wird die alte Sitzung verworfen.

Aktivierung, Speichergrenzen, Aufbewahrung und bestätigtes Löschen der Optimizerdaten
bleiben in Settings verfügbar. Deaktivieren löscht die zugehörigen Optimizerdaten;
Telemetrie und allgemeine lokale Statistiken bleiben unabhängig.

Externe Daten werden nur beim Öffnen oder mit **Refresh Now** geladen. Der Cache
ist fünf Minuten gültig; bei Fehlern bleibt der letzte erfolgreiche Stand sichtbar.
Es gibt kein Hintergrund-Polling und keine zusätzlichen Funkanfragen. HTTP 403 /
Cloudflare 1010 bedeutet nicht verfügbare Daten, nicht fehlende Netzaktivität.
Die Verfügbarkeit in der Anwendung gewährt keine Zugriffsrechte beim Anbieter;
Zugriffsbeschränkungen und Nutzungsbedingungen bleiben verbindlich.

Details: [Externe Daten und Grenzen](network-monitoring.md),
[Architektur und Tests](architecture.md), [Verwaltung](repeater-management.md).
V4 wird ausschließlich auf `v4.0.0` veröffentlicht; `main` bleibt V3.
