# Repeater-Optimierung: Messgrößen und fachliche Prüfbeispiele

**Status:** Diskussions- und Review-Dokument, keine implementierte automatische Optimierung. **Datenquelle:** ausschließlich die in MeshcoreStation ausgewählten Repeater-Beobachtungen. Stand: 17.10.2026.

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

## 3. Zuordnung Messgröße → Konfiguration → Review-Frage

| Einstellung | Beobachtbarer Anhaltspunkt | Fachliche Interpretation / Grenze | Empfehlung des Advisors |
| --- | --- | --- | --- |
| `loop.detect` | Wiederholte Digests, ähnliche Pfade, mehrfaches Auftreten in Pfaden | Wiederholung ist nicht automatisch ein Loop; Hash-Kollisionen möglich | **Prüfen**, nicht automatisch auf strict setzen |
| `flood.max` | Länge und Häufigkeit beobachteter Pfade; First/Middle/Final | Unbeobachtete entfernte Empfänger fehlen | Nur nach Prüfung der benötigten Reichweite testweise reduzieren |
| `flood.max.unscoped` | Scoped-Anteil und Pfade, soweit korrekt dekodiert | Keine globale Sicht auf Regionen und Zustellbedarf | Nur mit Kenntnis des regionalen Mesh-Designs ändern |
| `flood.max.advert` | Advertisement-Anteil, Pfadlängen der Adverts | Reichweitenverlust durch kleinere Hop-Grenze möglich | Expertenprüfung der Discovery-Reichweite |
| `flood.advert.interval` | Advertisement-Verkehr im Zeitverlauf | Nur beobachtete Adverts; Anteil der eigenen Aussendungen unklar | Längeres Intervall als Test bei auffälligem Overhead erwägen |
| `advert.interval` | Advertisement-Typen und Aktivitätsmuster | Lokale Adverts sind nicht zuverlässig isolierbar | Keine automatische Anpassung |
| `txdelay` | Hohe beobachtete Last, Wiederholungen und Pfadverteilung | Kein direkter Kollisions- oder Channel-Busy-Zähler | Nur kontrollierter Versuch, nicht aus Kopienzahl berechnen |
| `direct.txdelay` | Lokale Antwortpfade, sofern vorhanden | Keine zuverlässige Direct-TX-Fehlerquote | Ohne gezielte Tests keine Empfehlung |
| `rxdelay` | Pfadmuster | Kein direkter Nachweis für Nutzen eines RX-Delays | Experimentell, nur mit manueller Freigabe |
| `path.hash.mode` | Mehrdeutige Präfixe, Zahl bekannter Knoten | Mehrdeutigkeit hängt auch von der Kontaktliste ab | Hash-Größe und Netzkompatibilität fachlich prüfen |
| `multi.acks` | ACK-Paketart und Reply-Beobachtungen | Kein Nachweis für benötigte ACK-Redundanz | Community-Profil als Hypothese, nicht automatisch ändern |
| `cad` / `int.thresh` | Passive Lastspitzen | Kein gemessener Interferenz- oder CAD-Erfolg | Keine datenbasierte Änderung ohne Funkdiagnostik |
| `dutycycle` | Keine gemessene reale TX-Airtime | Gesetzliche/regionale Grenzen sind verbindlich | Nie aufgrund dieser Statistik erhöhen |
| Frequenz/BW/SF/CR/TX-Leistung | Keine ausreichenden Empfangsqualitäts-/Linkbudget-Daten | Netzkompatibilität, Reichweite und Regulierung betroffen | Keine automatische Änderung |
| `repeat` | Beobachtete Weiterleitungswege und aktive Stunden | Kein Traffic bedeutet nicht Nutzlosigkeit | Nicht automatisch deaktivieren |

## 4. Konkrete Fallbeispiele für die Expertenprüfung

**Alle Zahlen sind hypothetisch und keine validierten Schwellenwerte.**

### Fall A – viele identische Inhalte

- Zeitraum: 7 Tage; `copies=12.000`, `identified=10.000`, `unique=7.000`, `repeated=3.000`, `ratio=30 %`.
- Beobachtung: Die häufigsten Pfade und Paketarten zeigen, ob Wiederholungen auf wenige Inhalte oder Routen konzentriert sind.
- **Mögliche Empfehlung:** `loop.detect` prüfen, derzeitigen Wert auslesen und gezielt Pfade untersuchen.
- **Nicht zulässig:** „30 % Funkduplikate“ oder „`loop.detect=strict` löst 30 % der Last“ behaupten.
- **Expertenfragen:** Sind wiederholte Inhalte absichtliche Retransmits? Ist der Digest hinreichend eindeutig? Gibt es einen nachweisbaren Kreis im Pfad? Wie viele Kopien wurden wegen unvollständiger Daten ausgeschlossen?
- **Test:** Vorher/Nachher gleicher Beobachtungsdauer, gleiche Tageszeiten, zusätzlich manuelle Zustelltests.

### Fall B – hoher Advertisement-Anteil

- Zeitraum: 24 Stunden; 2.400 zugeordnete Kopien, davon 1.200 vom Typ Advertisement.
- **Mögliche Empfehlung:** `flood.advert.interval` und `flood.max.advert` als Review-Kandidaten anzeigen.
- **Nicht zulässig:** Die 1.200 Kopien dem eigenen Repeater als 1.200 Aussendungen zurechnen.
- **Expertenfragen:** Welcher Teil ist von fremden Knoten? Wie weit müssen Adverts gelangen? Welche Intervalle nutzt die lokale Community?
- **Test:** Nur eine Einstellung ändern; Sichtbarkeit neuer Knoten und beobachtete Advertisement-Pfade vergleichen.

### Fall C – viele mehrdeutige Zuordnungen

- Zeitraum: 7 Tage; 800 mehrdeutige Beobachtungen gegenüber 4.000 eindeutig zugeordneten Kopien.
- **Mögliche Empfehlung:** Identitätsauflösung/Kontaktliste prüfen; `path.hash.mode` mit Community-Konfiguration vergleichen.
- **Nicht zulässig:** Aus `ambiguous` direkt eine reale Hash-Kollision im Funknetz ableiten.
- **Expertenfragen:** Sind alle relevanten Repeater als Kontakte bekannt? Sind kurze Präfixe tatsächlich nicht eindeutig? Ist eine Änderung netzweit kompatibel?
- **Test:** Zuordnungsqualität vor/nach Aktualisierung der bekannten Repeater getrennt von Funkänderungen bewerten.

### Fall D – Rückgang der beobachteten Aktivität

- Zwei vollständige 7-Tage-Fenster: vorher 4.000, aktuell 2.200 unterschiedliche Digests; Trend -45 %.
- **Mögliche Empfehlung:** Ursachenanalyse statt unmittelbarer Konfigurationsänderung.
- **Nicht zulässig:** „Repeater hat 45 % Paketverlust“ oder „Repeater ist ausgefallen“.
- **Expertenfragen:** Wurde der Companion bewegt? Gab es Funkunterbrechungen, Collector-Drops, andere Nutzeraktivität, Ferien, Firmware-Updates oder geänderte Pfade?
- **Test:** Collector-Health, Aktivitätsstunden, Status/Telemetry und externe Gegenprobe kontrollieren.

### Fall E – hohe beobachtete Aktivität, vermeintliche Überlastung

- 24 Stunden: 18.000 Kopien, starke Abendspitzen, mehrere häufige Routen.
- **Mögliche Empfehlung:** `txdelay` und Flood-Grenzen **nur als Hypothesen** für Fachreview markieren.
- **Nicht zulässig:** Aus 18.000 beobachteten Kopien 18.000 Repeater-TX, Airtime oder Kollisionen berechnen.
- **Expertenfragen:** Ist die Last für das verwendete LoRa-Profil relevant? Gibt es tatsächliche Sende-/Kanalbelegungsdaten? Würde eine Hop-Reduktion wichtige Pfade unterbrechen?
- **Test:** Gezielt externe Funkdiagnostik und Zustelltests ergänzen; ohne diese keine numerische Einstellung empfehlen.

### Fall F – scheinbar nutzloser Repeater

- `active_hours=0` bei einem 24-Stunden-Fenster.
- **Mögliche Empfehlung:** „Keine Weiterleitung beobachtet; Messabdeckung prüfen“.
- **Nicht zulässig:** `repeat=off` empfehlen.
- **Expertenfragen:** War der Companion online? Liegt der Repeater auf beobachtbaren Pfaden? Existieren seltene, aber kritische Verbindungen? Ist die Auswahl seit 24 Stunden aktiv?

## 5. Bewertungsregeln für einen späteren Advisor

1. **Messqualität vor Empfehlung:** Teilfenster, Collector-Drops, Trimming, fehlende Digests und Mehrdeutigkeiten explizit anzeigen.
2. **Aktuelle Konfiguration lesen:** Nie Werte oder Firmware-Unterstützung annehmen. Fehlgeschlagene Reads bedeuten „unbekannt“.
3. **Beobachtung und Ursache trennen:** „Viele wiederholte Digests“ ist Messung; „Loop“ ist eine zu prüfende Hypothese.
4. **Konfidenz deklarieren:** *Beobachtung bestätigt*, *Hypothese zur Expertenprüfung*, *nicht beurteilbar*.
5. **Keine erfundenen Schwellen:** Grenzwerte erst anhand dokumentierter Messreihen und Expertenfeedback validieren.
6. **Community-Profil nicht blind übernehmen:** Profil mit Firmware, Region, Repeater-Rolle und benachbarten Netzen abgleichen.
7. **Änderungen einzeln testen:** Baseline sichern, eine Einstellung ändern, denselben Zeitraum beobachten und reale Zustelltests durchführen.
8. **Rollback vorbereiten:** Ursprüngliche Werte sichern, Änderung bestätigen, Rückweg dokumentieren; bei Timeout vor erneutem Schreiben zurücklesen.
9. **Rechtliche und Kompatibilitätsgrenzen beachten:** Dutycycle, Sendeleistung und Frequenz nicht durch statistische Heuristik erhöhen.
10. **Nur ausgewählter Repeater:** Keine Zusammenführung mehrerer Repeater zu einer vermeintlich globalen Netzmetrik.

## 6. Fragen an die fachliche Review-Runde

1. Welche Beobachtungen würden einen echten Flood-Loop ausreichend belegen?
2. Welche Repeater-Rollen benötigen welche Flood-Hop-Grenzen, und welche Erreichbarkeit muss garantiert bleiben?
3. Welche Community-Profile gelten für die verwendete Firmware und Region?
4. Welche Mindestbeobachtungsdauer und Mindestdatenqualität sind für Empfehlungen sinnvoll?
5. Welche zusätzlichen **tatsächlich remote verfügbaren** Telemetriedaten sollten wir historisieren?
6. Welche Tests belegen, dass weniger beobachtete Kopien nicht einfach weniger erfolgreiche Weiterleitung bedeuten?
7. Welche Einstellungen dürfen niemals automatisch vorgeschlagen oder übernommen werden?

## 7. Technische Referenzen

- [Passive Statistik](../meshcorestation/storage/passive_stats.py)
- [Usefulness-Zusammenfassung](../meshcorestation/storage/repeater_usefulness.py)
- [Repeater-Management](repeater-management.md)
- [Remote-Repeater-Steuerung](../meshcorestation/radio/repeater_control.py)
- [Unterstützte Konfigurationsfelder](../meshcorestation/radio/repeater_fields.py)
- [MeshCore Upstream CLI](https://github.com/meshcore-dev/MeshCore/blob/main/docs/cli_commands.md)

**Ergebnis:** Die bestehenden Messdaten erlauben eine nachvollziehbare Priorisierung von Prüf- und Testkandidaten, aber keine sichere automatische Ermittlung numerisch „optimaler“ Repeater-Parameter.
