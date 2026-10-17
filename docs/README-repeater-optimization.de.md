# Repeater-Optimierung: Messgrößen und fachliche Prüfbeispiele

**Status:** Advisor mit bestätigten manuellen Änderungen; keine automatische Optimierung. **Datenquelle:** ausschließlich die in MeshcoreStation ausgewählten Repeater-Beobachtungen. Stand: 17.10.2026.

## 1. Was MeshcoreStation tatsächlich aufzeichnet

Die passive Statistik in `meshcorestation/storage/passive_stats.py` verarbeitet empfangene Funkpakete des verbundenen Companion-Geräts, **sofern der ausgewählte Repeater in einem auswertbaren Pfad vorkommt**. Sie liest keine internen RX-/TX-Zähler des Repeaters aus. Die Zuordnung erfolgt über Pfad-Hash-Präfixe; unbekannte oder mehrdeutige Zuordnungen werden gesondert behandelt. Direkte Pfade ohne Forwarding-Historie, Trace-Pakete und nicht auswertbare Pfade gehen nicht in die Beobachtungen ein.

Die Datenbank `repeater-statistics.db` hält maximal 30 Tage bzw. 200.000 Beobachtungen. Ansichten: 24 Stunden, 7 Tage, 30 Tage. Ein Wechsel des ausgewählten Repeaters startet die Erfassung für das neue Ziel; alte Datensätze sind nicht automatisch ein vollständiger Beobachtungszeitraum.

| Verfügbare Größe | Implementierung / Bedeutung | Aussage für Empfehlungen |
| --- | --- | --- |
| `copies` | Anzahl gültiger, eindeutig zugeordneter beobachteter Paketkopien mit ausgewähltem Repeater im Pfad | Aktivität des Repeaters in **beobachteten Pfaden**, nicht Gesamt-RX oder -TX |
| `unique` | Unterschiedliche Payload-Digests der identifizierbaren Kopien | Maß für beobachtete Vielfalt, **keine** Anzahl erfolgreich zugestellter Nachrichten |
| `repeated`, `ratio` | `COUNT(digest) - COUNT(DISTINCT digest)`; Anteil an identifizierbaren Kopien | Hinweis auf mehrfach beobachtete Inhalte; kein Beweis für Funk-Loops oder vermeidbare Wiederholungen |
| `unidentified` | Kopien ohne berechenbaren Digest | Einschränkung der Wiederholungsanalyse |
| `ambiguous` | Beobachtungen mit nicht eindeutiger Zuordnung | Qualität und Vollständigkeit der Zuordnung |
| `timeline` | Kopien und unterschiedliche Digests je Stunde (24h) bzw. Tag (7/30 Tage) | Lastspitzen, Tagesmuster, Vorher/Nachher-Vergleich |
| `types` | Paketarten, z. B. Request, Response, Direct text, ACK, Advertisement, Group text, Control | Verkehrsprofil; keine getrennte interne Sende-/Empfangszählung |
| `roles` | `First`, `Middle`, `Final`: Position des Repeaters im beobachteten Pfad | Einordnung der Pfadrolle; Kategorien können bei wiederholtem Auftreten überlappen |
| `scoped` | Anzahl beobachteter Kopien mit entsprechendem Route-Type | Indiz für scoped/unscoped-Verteilung; genaue Protokollsemantik prüfen |
| `routes` | 20 häufigste beobachtete Pfade mit Häufigkeit | Pfadmuster und alternative Wege, keine vollständige Topologie |
| `previous`, `following` | Bis zu 30 häufige Vorgänger/Nachfolger im Pfad | Benachbarte Pfadpositionen; nicht automatisch direkte RF-Nachbarn |
| `usefulness.unique` | Unterschiedliche identifizierte Inhalte | Aktivitätsindikator |
| `usefulness.active_hours` / `activity` | Stunden mit beobachteter Aktivität | Zeitliche Präsenz, nicht Verfügbarkeit des Repeaters |
| `usefulness.routes` / `neighbors` | Unterschiedliche Pfade / eindeutig zugeordnete angrenzende Pfadknoten | Vielfalt beobachteter Weiterleitungswege |
| `usefulness.trend` | Veränderung gegenüber vorherigem gleich langem Fenster, nur bei geeigneter Datenlage | Entwicklung; Änderungen können durch Nutzerverkehr statt Konfiguration entstehen |
| `usefulness.replies` | Anteil der lokal erfassten Command-Replies, deren beobachteter Pfad den Repeater enthält | Beitrag zu diesen **lokalen** Antworten, keine End-to-End-Erfolgsquote |
| `health`, `partial` | Collector-Heartbeat, Drop-Zähler, Fehler, gekürzte Daten, Teilfenster, Radio-Status | Vertrauenswürdigkeit und Abdeckung der Analyse |

**Wichtige Einschränkung:** Die Kennzahl `ratio` zählt gleiche Digests auch bei unterschiedlichen Pfaden. Sie ist kein validierter Duplicate-/Loop-Prozentsatz. Das Sammeln beginnt nur bei aktiver Auswahl und sieht nur die beim Companion eintreffenden Pakete. Paketverluste und nicht empfangene Aussendungen bleiben unsichtbar.

## 2. Zusätzlich abrufbare Repeater-Daten – derzeit nicht als historische Messreihe gespeichert

Die Repeater-Verwaltung (`meshcorestation/radio/repeater_control.py`) unterstützt `status`, `telemetry` und `neighbors` über Remote-Anfragen, sofern Firmware und Berechtigungen es zulassen. Antworten haben einen Abfragezeitpunkt. Die tatsächlich gelieferten Felder variieren je nach Firmware. Eine regelmäßige Historisierung dieser Antworten ist im passiven Statistikmodul **nicht** implementiert.

Die Verwaltung kann aktuelle Konfigurationswerte per `read` abrufen. Dazu gehören u. a. `repeat`, `flood.max`, `flood.max.unscoped`, `flood.max.advert`, `advert.interval`, `flood.advert.interval`, `loop.detect`, `path.hash.mode`, `txdelay`, `direct.txdelay`, `rxdelay`, `multi.acks`, `cad`, `int.thresh`, `dutycycle` und Funkparameter. Nicht unterstützte Werte bleiben unbekannt; sie dürfen nicht geraten werden. Remote-Konsole ist **kein** kontinuierliches serielles Log. Firmware-seitig nur seriell verfügbare Zähler dürfen nicht als remote verfügbar angenommen werden.

**Nicht durch die passive Statistik belegt:** tatsächliche Sendezeit/Airtime, Kanalbelegung, interne TX-/RX-Paketzähler, CRC-/PHY-Fehler, Queue-Tiefe, kollisionsbedingte Verluste, vollständige RSSI-/SNR-Verteilungen, ACK-Erfolgsquote und Ende-zu-Ende-Zustellung. Daraus abgeleitete Aussagen sind ohne zusätzliche instrumentierte Daten unzulässig.

## 3. Implementierter Advisor (3.0.2rc3)

Der Advisor kann nach ausdrücklicher Bestätigung ausgewählte Einstellungen ändern.
Er verwendet dieselbe Admin-Sitzung, Feldvalidierung und Schreib-/Leseprüfung wie
Repeater Management. Die Sitzungsschlüssel verlassen das Verwaltungsfenster nicht.
Vor jeder Änderung werden die Werte erneut gelesen. Abweichungen vom geprüften
Ausgangswert verhindern die Änderung; bei einem unbestätigten Ergebnis stoppt die
verbleibende Auswahl. Bereits bestätigte Änderungen werden nicht automatisch
zurückgesetzt. Der Advisor überschreibt keine ungespeicherten Formulareingaben.

Die Auswertung läuft zentral auf dem Server. Die Datenbankabfrage liest nur die
benötigten Summen in einer konsistenten Transaktion, nicht die vollständige
Statistikansicht. Ein Wechsel zwischen 24 Stunden, 7 und 30 Tagen aktualisiert die
Daten sofort. Unvollständige Erfassungsfenster, verworfene Beobachtungen, gekürzte
Historie, veralteter Collector-Heartbeat und eine getrennte Funkverbindung werden
als Einschränkungen angezeigt. Auch ausreichende Beobachtungen sind kein Beweis
für optimale Konfiguration oder erfolgreiche Ende-zu-Ende-Zustellung.

### Referenzen und Herkunft

Prüfdatum: **17.10.2026**. Die vorhandenen Werte 16 / 3 / 6 Hops, 240 Minuten,
48 Stunden und `minimal` bleiben als **vorläufige, editierbare Referenzen** erhalten.
Ihre ursprüngliche gemeinsame Herleitung als deutscher Community-Standard konnte
nicht nachvollzogen werden. Daher werden sie nicht als allgemeine Empfehlung
bezeichnet.

- [Offizielle CLI-Dokumentation](https://github.com/meshcore-dev/MeshCore/blob/main/docs/cli_commands.md): Befehlssemantik und Wertebereiche; nennt 3 unscoped Hops als Beispiel, nicht als universelles Optimum.
- [Offizieller Release-Beitrag zu 1.16](https://blog.meshcore.io/2026/06/06/release-1-16-0): erklärt getrennte Limits für unscoped Traffic und Adverts. Firmware-Defaults sind keine standortbezogenen Empfehlungen.

### Historie und Wiederherstellen

`data/repeater-advisor-history.db` speichert maximal 1000 Advisor-Änderungen,
inklusive Ausgangswert, Zielwert, Rücklesewert und Status. Pro Repeater zeigt die UI
die letzten 50 Einträge. Passwörter und Sitzungsschlüssel werden nicht gespeichert.
Ein vor dem Senden angelegter Eintrag bleibt bei Prozessabbruch als unbekanntes
Ergebnis sichtbar. Änderungen aus Android oder der normalen Konsole sind nicht
Teil dieser Historie.

„Review restore“ ist nur für verifizierte Änderungen verfügbar. Es setzt nach
Bestätigung den früheren Wert zurück, sofern der aktuelle Wert noch dem damaligen
Rücklesewert entspricht und der frühere Wert gültig ist. Bei späteren Änderungen
muss neu gelesen und manuell geprüft werden. Ein Restore ist eine neue protokollierte
Änderung, kein blindes Rollback.

### Entwicklung und Veröffentlichung

Vor Bearbeitung `main` abrufen und neue Änderungen in diesen Feature-Branch mergen.
Versionsbasis wie `main` beibehalten, nur RC-Zähler erhöhen. Release `3.0.2rc3` enthält die Advisor-Verbesserungen und die Änderungen aus
`main` 3.0.2 einschließlich optional gespeicherter Repeater-Passwörter.
Weitere Veröffentlichungen nur nach ausdrücklicher Aufforderung.

### 3.0.2rc4

Fortschritt pro Einstellungsabfrage und zeitnahe Meldung bei fehlender Verbindung
zum Verwaltungsfenster. Der Advisor öffnet in einem frischen Fenster. Zurück führt
zur Repeater-Verwaltung mit bestehender Sitzung. Der separate Advisor-Link unter
„My repeater statistics“ wurde entfernt.
