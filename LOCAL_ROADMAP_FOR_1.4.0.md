Bitte prüfe und verbessere die Archive-Image-Verarbeitung von Meshive.

Beim Scannen meiner Bibliothek sind mehrere Probleme aufgefallen. Bitte analysiere zuerst die bestehende Implementierung vollständig und ändere anschließend Code, Tests und Dokumentation entsprechend. Verwende die tatsächlich im Repository vorhandenen Konfigurationsnamen und Strukturen und erfinde keine parallelen Mechanismen, wenn bereits passende vorhanden sind.

## Aktuell beobachtete Probleme

Beim Scan erscheinen unter anderem folgende Meldungen:

```text
archive_image_failed
Archive entry does not contain a valid image

archive_image_failed
Archive image exceeds the 40000000 pixel limit

archive_image_failed
Archive entry is not a supported image

archive_image_batch_failed
8 archive image(s) could not be extracted:
Archive command exceeded the 90 second limit

archive_image_batch_failed
12 archive image(s) could not be extracted:
Archive command exceeded the 90 second limit
```

Zusätzlich habe ich festgestellt, dass bei manchen Archiven nicht alle enthaltenen Bilder in Meshive importiert werden, obwohl für die fehlenden Bilder keinerlei Scan-Warnung oder Fehler angezeigt wird.

Das ist besonders problematisch, weil dadurch nicht erkennbar ist, ob Bilder wegen eines Limits, eines Filters, eines nicht unterstützten Formats, eines Fehlers oder aus einem anderen Grund fehlen.

## 1. Stille Bildverluste vollständig untersuchen

Prüfe die komplette Pipeline:

* Archive listing
* Erkennung möglicher Bilddateien
* Candidate selection
* Path-/Extension-Filter
* Größenlimits
* Gesamtgrößenbudget
* Candidate count limit
* Extraktion
* Timeout-Verhalten
* Bildvalidierung
* Formatvalidierung
* Pixel-Limit
* Generierung der WebP-Derivate
* Speichern im Cache
* Zuordnung zur Galerie

Finde alle Stellen, an denen ein potentielles Archivbild mit `continue`, `return False`, Filterung oder ähnlichem verworfen werden kann, ohne dass dieser Vorgang später nachvollziehbar ist.

Ein Bild darf nicht still verschwinden, wenn es grundsätzlich als möglicher Galerie-Kandidat erkannt wurde.

## 2. Aussagekräftigere Scan-Issues

Aktuelle Fehler wie:

```text
Archive entry does not contain a valid image
```

sind kaum hilfreich, weil nicht ersichtlich ist, welche Datei betroffen ist.

Erweitere Archive-Image-Issues deshalb mindestens um:

* Archive entry path / Dateiname
* Grund des Fehlers
* falls sinnvoll tatsächliches erkanntes Bildformat
* bei Pixel-Limit: Breite × Höhe und Pixelanzahl
* konfiguriertes Limit
* bei Größenlimit: tatsächliche Größe und Limit
* bei Timeout möglichst Archiv bzw. betroffene Kandidaten/Batches

Beispiel:

```text
renders/kaneda-front.jpg:
Archive entry does not contain a valid image
```

oder:

```text
renders/render01.jpg:
Archive image is 7680 × 5760 = 44,236,800 pixels.
Configured limit: 40,000,000 pixels.
```

Die Meldungen sollen diagnostisch nützlich sein, aber nicht unnötig riesig werden.

## 3. Übersprungene Kandidaten sichtbar machen

Nicht jeder bewusst übersprungene Kandidat muss ein einzelnes Warning-Issue erzeugen.

Statt hunderten Meldungen sollte Meshive pro Modell sinnvoll aggregieren.

Beispiel:

```text
archive_image_candidates_skipped

7 archive image(s) were not selected:
- 4 exceeded the candidate count limit
- 2 exceeded the per-entry size limit
- 1 exceeded the total extraction budget
```

Falls ein Pfad bewusst ausgeschlossen wird, z. B. Texture-/Material-Verzeichnisse oder `__MACOSX`, unterscheide zwischen:

* bewusst ignorierten Dateien, die erwartungsgemäß keine Galerie-Bilder sind
* potentiellen Galerie-Bildern, die aufgrund eines Schutzlimits oder technischen Problems übersprungen wurden

Normale Texture-Maps sollen die Scan-Issue-Liste nicht zuspammen.

## 4. Candidate-Limit semantisch überprüfen

Prüfe insbesondere, wie das maximale Candidate-/Image-Limit momentan funktioniert.

Falls Meshive aktuell beispielsweise zuerst maximal 12 Kandidaten auswählt und erst danach feststellt, dass einige davon kaputt, zu groß oder anderweitig unbrauchbar sind, entsteht folgendes Problem:

```text
20 Bilder vorhanden
12 Kandidaten ausgewählt
2 davon ungültig
=> nur 10 Bilder importiert
=> Bilder 13 und 14 werden nie ausprobiert
```

Das möchte ich vermeiden.

Das Limit sollte möglichst bedeuten:

> maximal N erfolgreich importierte Galerie-Bilder pro Modell

und nicht:

> maximal N Dateien überhaupt ausprobieren

Wenn Kandidaten während Extraktion oder Validierung scheitern, soll Meshive nach Möglichkeit weitere geeignete Kandidaten nachziehen, bis:

* das gewünschte Maximum erfolgreicher Bilder erreicht wurde,
* keine Kandidaten mehr vorhanden sind,
* oder ein anderes Sicherheitsbudget erreicht wurde.

Achte dabei darauf, dass dadurch keine Schutzmechanismen umgangen werden.

## 5. Mehrere Archive pro Modell

Prüfe auch Modelle mit mehreren Archiven.

Ein globales Limit pro Modell ist grundsätzlich sinnvoll, aber die Reihenfolge der Archive darf nicht dazu führen, dass das erste Archiv sämtliche Slots verbraucht und relevante Bilder aus späteren Archiven unbeabsichtigt nie berücksichtigt werden.

Bewerte die bestehende Sortier-/Auswahllogik und verbessere sie bei Bedarf.

Die Auswahl soll deterministisch bleiben.

## 6. Sicherheitslimits an meine Bibliothek anpassen

Die bisherigen Defaults erscheinen für hochwertige 3D-Modell-Archive teilweise zu konservativ.

Ich möchte ungefähr folgende Größenordnung:

* max. Galerie-Bilder pro Modell: 30
* max. Einzelbild: 64 MiB
* max. komprimiertes Einzelbild: 64 MiB
* Gesamtbudget für Archivbilder pro Modell: 256 MiB
* maximales Bild: 80 Megapixel
* Archive extraction timeout: 180 Sekunden
* Archive image extraction concurrency/threads: ungefähr 2, sofern die bestehende Architektur das sinnvoll unterstützt

Bitte prüfe die aktuell vorhandenen Defaults und Konfigurationsvariablen.

Ändere vorhandene Defaults sauber, statt neue redundante Settings anzulegen.

Falls einzelne Werte aus Sicherheits-, RAM-, CPU- oder I/O-Gründen problematisch wären, behalte den sichereren Wert und dokumentiere nachvollziehbar warum.

Alle Limits müssen weiterhin konfigurierbar bleiben.

## 7. Timeout-Verhalten

Bei einigen großen CA3D-Archiven treten Fehler auf wie:

```text
8 archive image(s) could not be extracted:
Archive command exceeded the 90 second limit
```

oder:

```text
12 archive image(s) could not be extracted:
Archive command exceeded the 90 second limit
```

Prüfe insbesondere das Verhalten bei großen bzw. solid-komprimierten 7z-Archiven.

Falls bereits Batch-Splitting oder Retry-Logik existiert, überprüfe deren Verhalten sorgfältig.

Nicht einfach blind das Timeout erhöhen.

Ziel:

* möglichst effiziente Extraktion
* weiterhin begrenzte Ressourcen
* keine hängenden Scan-Prozesse
* nachvollziehbare Fehlermeldungen
* keine still verlorenen Bilder

Vermeide eine Implementierung, die für jedes einzelne Bild einen kompletten riesigen Solid-7z-Block erneut dekomprimiert, wenn dies effizienter gelöst werden kann.

## 8. Unterstützte und ungültige Bildformate

Unterscheide sauber zwischen:

```text
Archive entry does not contain a valid image
```

und:

```text
Archive entry is not a supported image
```

Bei `not supported` soll die Meldung möglichst das tatsächlich erkannte Format enthalten.

Beispiel:

```text
preview.jpg:
Detected image format TIFF is not supported.
Supported formats: JPEG, PNG, WEBP.
```

Bitte prüfe außerdem, welche Bildformate Pillow bzw. unsere bestehende Image-Pipeline bereits zuverlässig verarbeiten kann.

Unterstütze nicht einfach blind weitere Formate. Falls TIFF, AVIF oder andere Formate sinnvoll und sicher unterstützt werden können, bewerte das und implementiere es nur, wenn es zur bestehenden Architektur passt.

Dateiendung und tatsächlicher Dateiinhalt müssen weiterhin unabhängig voneinander validiert werden.

## 9. Sicherheit nicht verschlechtern

Die bestehende defensive Behandlung von Archivdateien muss erhalten bleiben.

Insbesondere weiterhin beachten:

* Path traversal
* manipulierte Archive
* extrem große Dateien
* decompression bombs
* Pixel bombs
* falsche Dateiendungen
* beschädigte Bilder
* Gesamtgrößenlimits
* Zeitlimits
* Nested archives, soweit relevant
* ausschließlich Meshive-managed Cache
* Library Sources bleiben read-only

Keine der Verbesserungen darf bedeuten, dass Sicherheitschecks einfach entfernt werden.

## 10. Scan-Zusammenfassung verbessern

Falls es zur bestehenden Architektur passt, wäre zusätzlich eine kompakte Statistik pro Modell bzw. Scan hilfreich:

```text
Archive images:
18 discovered
16 considered gallery candidates
14 imported successfully
1 invalid
1 exceeded pixel limit
2 intentionally ignored
```

Das muss nicht zwingend genau dieses UI-Format sein.

Wichtig ist, dass ein Administrator nachvollziehen kann:

* wie viele Bilder gefunden wurden
* wie viele als Kandidaten galten
* wie viele importiert wurden
* wie viele fehlgeschlagen sind
* wie viele aufgrund von Schutzlimits übersprungen wurden

Vermeide dabei redundante oder extrem große Scan-Issue-Listen.

## 11. Tests

Erweitere die Tests insbesondere für:

1. Archiv mit weniger Bildern als dem Limit
2. Archiv mit mehr Bildern als dem Limit
3. ungültiges JPG mit `.jpg`-Endung
4. unterstützte Endung, aber anderes tatsächliches Format
5. Bild über Pixel-Limit
6. Bild über Entry-Size-Limit
7. Überschreiten des Gesamtbudgets
8. Timeout bei Extraktion
9. teilweise fehlgeschlagener Batch
10. Nachziehen weiterer Kandidaten nach einem fehlgeschlagenen Bild
11. mehrere Archive pro Modell
12. deterministische Candidate-Auswahl
13. ausgeschlossene Texture-/Material-Pfade
14. keine Path-Traversal-Regression
15. keine Regression bei ZIP, 7z und RAR, soweit bereits unterstützt

Wichtig ist insbesondere ein Regressionstest für den aktuell beobachteten Fehler:

> Ein Archiv enthält mehr grundsätzlich geeignete Bilder als erfolgreich importiert werden, aber Meshive erzeugt keinerlei Information darüber, warum die übrigen Bilder fehlen.

Dieser Zustand darf nach der Änderung nicht mehr still auftreten.

## 12. Dokumentation

Aktualisiere die vorhandene Archive-Image-/Resource-Limit-Dokumentation mit:

* unterstützten Formaten
* Candidate-Auswahlregeln
* neuen/default Limits
* Bedeutung der einzelnen Limits
* Timeout-Verhalten
* Verhalten bei mehreren Archiven
* Unterschied zwischen ignored / skipped / failed
* Auswirkungen auf CPU, RAM, Storage-I/O und Scan-Zeit

## Vorgehensweise

Bitte zuerst:

1. aktuelle Implementierung vollständig nachvollziehen,
2. tatsächliche Ursache(n) des stillen Überspringens identifizieren,
3. relevante Tests lesen,
4. einen kurzen Implementierungsplan erstellen,
5. danach die Änderungen durchführen.

Versuche dabei bestehende Funktionen und Abstraktionen weiterzuverwenden.

Keine unnötige Neuarchitektur.

Am Ende bitte:

* die gefundenen Ursachen nennen,
* alle geänderten Dateien auflisten,
* erklären, wie Candidate-Auswahl und Limits danach funktionieren,
* erwähnen, welche Defaults geändert wurden,
* Tests ausführen und Ergebnisse nennen,
* auf verbleibende Edge Cases oder Performance-Risiken hinweisen.

## 13. Inkrementeller Abgleich zwischen Archiv und bestehendem Image-Cache

Ein weiteres wichtiges Ziel ist, bereits gescannte Modelle mit vorhandenen Archive-Images effizient erneut überprüfen zu können.

Beispiel:

```text
Model A

Archiv:
20 geeignete Galerie-Bilder

aktueller Meshive-Cache:
12 Galerie-Bilder
```

Meshive soll erkennen können, dass 8 Bilder fehlen, ohne zunächst alle 20 Bilder erneut aus dem Archiv zu extrahieren und alle Derivate neu zu generieren.

### Ziel

Implementiere, soweit es zur bestehenden Architektur passt, einen inkrementellen Archive-Image-Reconciliation-Mechanismus.

Der normale Ablauf soll möglichst sein:

```text
Archive listing lesen
        ↓
Soll-Zustand der Galerie bestimmen
        ↓
vorhandenen Cache-/Manifest-Zustand vergleichen
        ↓
unveränderte Bilder wiederverwenden
        ↓
nur fehlende/geänderte Bilder extrahieren
        ↓
nur dafür neue Derivate erzeugen
        ↓
veraltete Cache-Einträge entfernen
```

Ein vollständiger Rebuild aller Archive-Images soll nicht der Standardweg sein.

### 13.1 Kein erneutes Extrahieren nur zum Vergleichen

Der Vergleich soll zunächst ausschließlich anhand von Daten erfolgen, die ohne Extraktion der eigentlichen Bilder verfügbar sind.

Nutze nach Möglichkeit Informationen aus dem Archive-Listing wie:

* Archive entry path
* unkomprimierte Größe
* komprimierte Größe
* CRC, falls vom Archivformat/Tool zuverlässig verfügbar
* Timestamp, falls sinnvoll
* Archiv-Fingerprint
* andere bereits vorhandene stabile Entry-Metadaten

Das eigentliche Bild soll für den Soll-/Ist-Vergleich nicht extrahiert werden müssen.

Insbesondere soll Meshive NICHT:

```text
20 Bilder extrahieren
20 Bilder dekodieren
20 WebPs neu erzeugen
danach feststellen, dass 12 davon bereits vorhanden waren
```

wenn der bestehende Zustand zuverlässig wiederverwendet werden kann.

### 13.2 Cache-Manifest / Source-Mapping

Prüfe, welche Metadaten Meshive derzeit bereits für generierte Archive-Images speichert.

Falls noch kein ausreichend detailliertes Mapping vorhanden ist, erweitere die bestehende Cache-Metadatenstruktur sinnvoll.

Für ein generiertes Galerie-Bild sollte Meshive nach Möglichkeit nachvollziehen können:

```text
Model
Archive
Archive fingerprint
Archive entry path
Entry fingerprint / CRC / relevante Metadaten
generierte Cache-Dateien
Image dimensions
Source format
Cache/schema version
```

Nicht zwangsläufig alle Angaben müssen gespeichert werden, wenn sie redundant sind.

Ziel ist eine robuste Zuordnung:

```text
dieses gecachte WebP
        ↕
dieser konkrete Archive-Entry
```

Vermeide eine unnötig komplexe neue Datenbankstruktur, falls die vorhandene Architektur dies bereits sauber abbilden kann.

### 13.3 Entry-Identität

Verwende für den Vergleich die stärkste zuverlässig verfügbare Identität.

Bevorzugte Reihenfolge ungefähr:

1. stabiler Entry-Hash/CRC aus dem Archiv-Listing, falls verfügbar und zuverlässig
2. Entry path + Größe + weitere verfügbare Metadaten
3. Archiv-Fingerprint + Entry path
4. anderer vorhandener sicherer Mechanismus

Verlasse dich nicht ausschließlich auf Dateinamen, falls die vorhandene Implementierung stärkere Informationen liefern kann.

Es ist nicht erforderlich, jedes Quellbild neu zu hashen, wenn dafür erst eine vollständige Extraktion nötig wäre.

### 13.4 Soll-Zustand neu berechnen

Bei einem Rescan soll Meshive aus dem Archive-Listing erneut bestimmen:

```text
welche Archive-Entries wären mit den AKTUELLEN Regeln Galerie-Bilder?
```

Danach soll dieser Soll-Zustand mit dem Cache abgeglichen werden.

Beispiel:

```text
Archiv enthält:
image01.jpg
...
image20.jpg

Cache enthält:
image01.jpg
...
image12.jpg

Soll-Zustand:
image01.jpg
...
image20.jpg

Ergebnis:
12 reusable
8 missing
```

Dann sollen ausschließlich:

```text
image13.jpg
...
image20.jpg
```

extrahiert und verarbeitet werden.

### 13.5 Änderungen an Candidate-Regeln müssen einen Abgleich auslösen

Sehr wichtig:

Ein unveränderter Archiv-Fingerprint darf nicht automatisch bedeuten:

> Archive-Images müssen niemals wieder betrachtet werden.

Beispiel:

Bisher:

```text
MESHIVE_ARCHIVE_IMAGE_MAX_CANDIDATES=12
```

Archiv enthält 20 Bilder.

Cache enthält deshalb nur 12.

Später wird das Limit geändert auf:

```text
30
```

Das Archiv selbst wurde nicht verändert.

Meshive muss trotzdem erkennen:

```text
alte Auswahlregel: maximal 12
neue Auswahlregel: maximal 30

=> Archive-Image-Reconciliation erforderlich
```

Speichere oder berechne deshalb einen geeigneten:

```text
selection policy fingerprint
```

oder einen vergleichbaren Versionierungsmechanismus.

Dieser sollte relevante Änderungen berücksichtigen, beispielsweise:

* Candidate count
* unterstützte Formate
* Pfadfilter
* Auswahl-/Sortierlogik
* relevante Größenlimits
* andere Regeln, die beeinflussen, welche Bilder importiert werden

Nicht jede Änderung eines Laufzeitparameters muss zwangsläufig einen kompletten Cache invalidieren.

Entscheide sinnvoll, welche Settings tatsächlich den gewünschten Soll-Zustand beeinflussen.

### 13.6 Cache-Versionierung

Falls sich die Archive-Image-Pipeline strukturell ändert, sollte außerdem eine kleine Cache-/Pipeline-Version vorhanden sein.

Beispielsweise konzeptionell:

```text
archive_image_cache_version
archive_image_selection_version
```

Nicht zwingend genau mit diesen Namen.

Damit soll Meshive erkennen können:

```text
Cache wurde mit einer alten Selektionslogik erzeugt
→ Soll-Zustand erneut bestimmen
```

ohne grundsätzlich alle Bilder neu generieren zu müssen.

### 13.7 Bereits vorhandene Bilder wiederverwenden

Wenn ein Source-Entry unverändert ist und seine benötigten Cache-Derivate vollständig vorhanden sind:

```text
NICHT erneut extrahieren
NICHT erneut dekodieren
NICHT erneut WebP erzeugen
```

Stattdessen vorhandenen Cache weiterverwenden.

Das sollte auch für große Archive gelten.

### 13.8 Fehlende Cache-Dateien reparieren

Der Reconciliation-Schritt soll zusätzlich erkennen können:

```text
Manifest sagt Bild vorhanden
aber Cache-Datei fehlt
```

Dann soll ausschließlich dieses Bild neu erzeugt werden.

Beispiel:

```text
20 Source-Images
20 Einträge im Manifest
19 Cache-Dateien vorhanden

=> nur 1 Source-Image erneut extrahieren/generieren
```

Es ist nicht nötig, bei jedem normalen Scan sämtliche vorhandenen WebPs vollständig zu dekodieren.

Eine schnelle Existenz-/Metadatenprüfung reicht im normalen Fast Path aus, sofern kein konkreter Hinweis auf beschädigte Cache-Dateien besteht.

### 13.9 Veraltete Bilder entfernen

Der Soll-/Ist-Abgleich muss auch in die andere Richtung funktionieren.

Beispiel:

```text
Cache:
20 Bilder

aktueller Soll-Zustand:
18 Bilder
```

Dann sollen die zwei nicht mehr benötigten Meshive-managed Cache-Einträge sauber entfernt werden.

Mögliche Ursachen:

* Source-Image wurde aus Archiv entfernt
* Archive wurde ersetzt
* Auswahlregel wurde geändert
* Format ist nicht mehr unterstützt
* Candidate-Auswahl hat sich geändert

Dabei niemals Dateien innerhalb der Library Sources verändern.

Nur Meshive-managed Cache darf bereinigt werden.

### 13.10 Mehrere Archive berücksichtigen

Der Reconciliation-Mechanismus muss auch bei einem Modell mit mehreren Archiven funktionieren.

Beispiel:

```text
Model A
├── base.7z
└── bonus.7z
```

Der Cache muss nachvollziehen können, aus welchem Archiv und welchem Entry ein Bild stammt.

Änderungen an `bonus.7z` sollen nach Möglichkeit nicht dazu führen, dass unveränderte Bilder aus `base.7z` neu erzeugt werden.

### 13.11 Archive-Fingerprint sinnvoll nutzen

Falls Meshive bereits Archive-Fingerprints verwendet, integriere den neuen Mechanismus darin, statt eine parallele Invalidierungslogik einzuführen.

Optimal wäre ein schneller Pfad wie:

```text
Archive unchanged
Selection policy unchanged
Manifest consistent
Cache files present

=> nichts tun
```

Ein zweiter Pfad:

```text
Archive unchanged
Selection policy changed

=> Archive listing verwenden
=> Soll-Zustand neu berechnen
=> Cache abgleichen
=> nur Differenz verarbeiten
```

Und:

```text
Archive changed

=> neues Listing
=> Entries vergleichen
=> unveränderte Entries nach Möglichkeit behalten
=> geänderte/neue Entries selektiv regenerieren
=> entfernte Entries aus Cache entfernen
```

### 13.12 Alte Cache-Einträge ohne ausreichende Metadaten

Berücksichtige Upgrades bestehender Meshive-Installationen.

Es wird bereits Archive-Images im Cache geben, die möglicherweise noch kein neues Source-Manifest besitzen.

Implementiere einen sicheren Migrations-/Fallback-Pfad.

Bevorzuge:

* vorhandene Metadaten wiederverwenden, wenn eine eindeutige Zuordnung möglich ist
* keinen kompletten Rebuild erzwingen, wenn das vermeidbar ist

Falls bei alten Cache-Einträgen keine zuverlässige Source-Zuordnung möglich ist, darf einmalig ein selektiver oder vollständiger Rebuild für das betroffene Modell nötig sein.

Dieser Fallback soll sauber und nachvollziehbar sein.

### 13.13 Solid-komprimierte 7z-Archive

Berücksichtige besonders große solid-komprimierte 7z-Archive.

Wenn beispielsweise nur 8 von 20 Bildern fehlen:

```text
12 bereits gültig gecacht
8 fehlen
```

soll Meshive nicht unnötig alle 20 erneut extrahieren.

Gleichzeitig soll die Extraktionsstrategie für die 8 fehlenden Bilder möglichst effizient gebatcht werden, damit ein großer Solid-Block nicht unnötig für jedes einzelne Bild separat mehrfach dekomprimiert wird.

Prüfe deshalb, wie die bestehende Batch-/Timeout-Logik mit der neuen inkrementellen Verarbeitung zusammenspielt.

### 13.14 Reconciliation-Statistik

Der Scan sollte einen kompakten diagnostischen Zustand erzeugen können, z. B.:

```text
Archive image reconciliation:

20 desired
12 already cached and reusable
8 missing
8 extracted
8 generated
0 failed
0 stale
```

Oder bei einem späteren Scan:

```text
20 desired
20 reusable
0 extracted
0 generated
```

Solche Informationen müssen nicht zwangsläufig als permanente Warning-Issues gespeichert werden.

Debug-/Scan-Statistik oder eine andere geeignete vorhandene Administrationsstruktur ist ausreichend.

Wichtig ist, dass sich nachvollziehen lässt, ob Meshive tatsächlich den Fast Path verwendet.

### 13.15 Performance-Ziel

Der häufigste Fall soll sehr billig sein:

```text
Library rescan
Archive unverändert
Cache vollständig
Regeln unverändert
```

Dabei soll möglichst nur:

* Fingerprint-/Metadatenprüfung
* gegebenenfalls Archive listing
* Cache-Manifest-Abgleich
* Existenzprüfung der benötigten Cache-Dateien

stattfinden.

Keine unnötige:

* Bildextraktion
* Bilddekodierung
* WebP-Generierung
* große temporäre Datei
* vollständige Archivdekompression

### 13.16 Keine falsche Optimierung

Performance darf nicht zu stillen Inkonsistenzen führen.

Wenn Meshive nicht sicher feststellen kann, ob ein Cache-Eintrag noch zum Source-Entry passt, soll es diesen Entry lieber selektiv neu erzeugen.

Aber:

> Unsicherheit bei einem einzelnen Bild darf nicht automatisch einen Rebuild aller Bilder des Modells auslösen, wenn sich die übrigen Entries zuverlässig verifizieren lassen.

## Zusätzliche Tests für den inkrementellen Cache-Abgleich

Ergänze die bereits geforderten Tests zusätzlich mindestens um:

16. Archiv mit 20 Bildern, Cache enthält nur 12 → nur 8 werden extrahiert/generiert

17. Archiv mit 20 Bildern, Cache enthält alle 20 → keine Bildextraktion

18. Candidate-Limit ändert sich von 12 auf 30 bei unverändertem Archiv → fehlende Bilder werden erkannt

19. unverändertes Source-Image mit vorhandenem Cache → Derivat wird wiederverwendet

20. einzelnes Source-Image geändert → nur dieses Bild wird neu erzeugt, soweit Entry-Metadaten dies zuverlässig erkennen lassen

21. Source-Image aus Archiv entfernt → zugehöriger Cache-Eintrag wird entfernt

22. einzelne Cache-Datei fehlt → nur dieses Bild wird regeneriert

23. mehrere Archive pro Modell → Änderung eines Archivs invalidiert nicht unnötig unveränderte Bilder des anderen

24. alter Cache ohne neues Manifest → definierter Migrations-/Fallback-Pfad

25. Selection-Policy-Version ändert sich → Reconciliation erfolgt ohne pauschalen Full Rebuild

26. unverändertes Archiv + unveränderte Policy + vollständiger Cache → Fast Path ohne Extraction

27. inkrementelle Extraktion aus solid-komprimiertem 7z bleibt gebatcht und verursacht keine unnötige Einzelbild-Dekompression

28. Archive-Image-Reconciliation darf Library Sources niemals verändern

## Ergänzung zum Abschlussbericht

Nenne am Ende zusätzlich:

* welche Metadaten Meshive künftig pro Source-Image speichert
* wie Source-Entries und Cache-Dateien zugeordnet werden
* wann ein Archive-Listing erforderlich ist
* wann überhaupt keine Archive-Extraktion erfolgt
* wann nur einzelne Bilder neu erzeugt werden
* wodurch ein kompletter Rebuild ausgelöst wird
* wie Änderungen an Candidate-/Selection-Regeln erkannt werden
* wie bestehende alte Cache-Einträge migriert werden
* welche Optimierung speziell für solid-komprimierte 7z-Archive verwendet wird

Das zentrale Ziel lautet:

> Der Archive-Image-Cache soll ein inkrementell synchronisierter Soll-/Ist-Zustand sein und kein Cache, der bei jeder Unsicherheit komplett neu aufgebaut werden muss.

Ein Modell mit 20 geeigneten Archivbildern und 12 bereits korrekten gecachten Bildern soll im Normalfall ausschließlich die fehlenden 8 Bilder extrahieren und generieren.

## 14. Unterschiedliche Scan-Modi einführen

Die aktuelle Scan-Architektur soll so erweitert werden, dass Administratoren gezielt auswählen können, wie tief ein Scan durchgeführt wird.

Aktuell kann ein vollständiger Scan sehr lange dauern, obwohl eventuell nur die Bilder eines oder zweier Modelle repariert werden sollen.

Ziel ist deshalb, mehrere klar definierte Scan-Modi anzubieten.

Bitte prüfe zuerst die bestehende Scan-Architektur und integriere diese Modi möglichst in den vorhandenen Scanner, statt mehrere voneinander unabhängige Scan-Implementierungen zu erstellen.

Die Modi sollen möglichst dieselben Parsing-, Reconciliation- und Image-Funktionen wiederverwenden.

### 14.1 Full Scan + Full Image Reconciliation

Bezeichnung im UI beispielsweise:

```text
Full scan
```

oder eindeutiger:

```text
Full scan + image check
```

Verhalten:

```text
Alle Library Sources
        ↓
alle Modelle entdecken
        ↓
alle bekannten und neuen Modelle prüfen
        ↓
Metadaten neu gegen Library-Zustand abgleichen
        ↓
Archive-Image-Sollzustand für jedes Modell prüfen
        ↓
Cache/Manifest mit Archiv vergleichen
        ↓
nur notwendige Bilder extrahieren/regenerieren
```

Wichtig:

"Full" soll NICHT automatisch bedeuten:

```text
alle gecachten Bilder löschen
alle Bilder erneut extrahieren
alle WebPs erneut erzeugen
```

Auch bei einem Full Scan soll der zuvor beschriebene inkrementelle Image-Reconciliation-Mechanismus verwendet werden.

Beispiel:

```text
4000 Modelle vorhanden

3998 Modelle:
Archive unverändert
Cache vollständig
Selection policy unverändert

=> Image Fast Path
=> keine Extraktion

2 Modelle:
fehlende/geänderte Bilder

=> nur diese Bilder reparieren
```

Der Full Scan prüft also alles, verarbeitet aber trotzdem nur tatsächliche Differenzen.

Dieser Modus ist gedacht für:

* vollständige Konsistenzprüfung
* Änderungen an Parsing-Regeln
* Änderungen an Library-Inhalten
* Änderungen an Archive-Image-Auswahlregeln
* größere Meshive-Upgrades
* manuelle Integritätsprüfung

### 14.2 Full Model Scan + Missing Images Only

Zweiter Modus:

```text
Full scan — missing images only
```

oder eine ähnlich verständliche Bezeichnung.

Verhalten:

```text
alle Modelle prüfen
        ↓
Metadaten normal aktualisieren
        ↓
bei Modellen MIT bereits vorhandenen Bildern:
keine vollständige Archive-Image-Reconciliation
        ↓
bei Modellen OHNE Bilder:
Archive prüfen und Bilder erzeugen
```

Dieser Modus soll schneller sein als der vollständige Image-Reconciliation-Scan.

Gedacht beispielsweise für:

* neue Meshive-Installation
* Bibliothek vollständig neu einlesen
* Bilder nur für bislang bildlose Modelle nachholen
* große Bibliothek, bei der bestehende Bilder bewusst nicht überprüft werden sollen

Wichtig:

Definiere eindeutig, was "ohne Bilder" bedeutet.

Zum Beispiel:

```text
model.gallery_image_count == 0
```

oder der entsprechende bestehende Mechanismus.

Ein Modell mit:

```text
Archiv: 20 Bilder
Cache: 12 Bilder
```

soll bei diesem Modus NICHT automatisch auf 20 aufgefüllt werden, solange es bereits gültige Bilder besitzt.

Dafür ist der vollständige Image-Reconciliation-Modus gedacht.

### 14.3 Incremental Scan — New Models Only

Dritter Modus:

```text
Incremental scan
```

Verhalten:

```text
Library durchsuchen
        ↓
bereits bekannte Modelle möglichst billig erkennen
        ↓
bekannte unveränderte Modelle überspringen
        ↓
nur neue Modelle vollständig einlesen
        ↓
Metadaten erzeugen
        ↓
Archive-Images extrahieren/generieren
```

Bereits bekannte Modelle sollen bei diesem Modus möglichst nicht:

* erneut geparst
* vollständig validiert
* auf Archive-Images geprüft
* mit dem Image-Cache reconciled
* mit WebP-Verarbeitung belastet

werden.

Dieser Modus soll der schnelle Standardscan für den Alltag sein.

Typischer Anwendungsfall:

```text
Library enthält 4000 bekannte Modelle
10 neue Modelle wurden hinzugefügt

Incremental scan:

4000 bekannte Modelle schnell übersprungen
10 neue Modelle vollständig verarbeitet
```

Das Ziel ist eine sehr deutliche Verkürzung der Scan-Zeit.

### 14.4 Erkennung bereits bekannter Modelle

Prüfe, wie Meshive bekannte Modelle derzeit identifiziert und welche Fingerprints bereits vorhanden sind.

Der Incremental Scan soll nicht nur anhand des angezeigten Modellnamens entscheiden.

Nutze möglichst vorhandene stabile Informationen wie:

* Source
* Pfad
* Model fingerprint
* Archive fingerprint
* Directory fingerprint
* relevante bestehende DB-Identifiers

Verwende vorhandene Mechanismen, wenn diese bereits existieren.

Keine parallele Fingerprint-Infrastruktur erzeugen, wenn Meshive bereits eine geeignete besitzt.

### 14.5 Verhalten bei gelöschten Modellen

Definiere ausdrücklich, wie der Incremental Scan mit Modellen umgehen soll, die aus der Library entfernt wurden.

Ein "new models only"-Scan darf nicht versehentlich dafür sorgen, dass gelöschte Modelle für immer als vorhanden gelten.

Falls die Erkennung gelöschter Modelle billig möglich ist, soll sie Bestandteil des Incremental Scan bleiben.

Wenn dafür eine vollständige Enumeration der Library nötig ist, ist das akzeptabel.

Wichtig ist die Unterscheidung zwischen:

```text
Library-Einträge enumerieren
```

und:

```text
jedes bekannte Modell vollständig neu verarbeiten
```

Das erste darf weiterhin stattfinden.

Das zweite soll vermieden werden.

---

## 15. Zusätzlicher Modus: Image Reconciliation / Media Repair

Zusätzlich zu den drei obigen Modi soll geprüft werden, ob ein eigener schneller Modus sinnvoll implementiert werden kann:

```text
Image reconciliation
```

oder:

```text
Repair archive images
```

Dieser Modus ist für den Fall gedacht:

> Die Modelle und Metadaten sind korrekt, aber Archive-Images bzw. deren Cache sollen überprüft oder repariert werden.

Verhalten:

```text
bekannte Modelle verwenden
        ↓
keine unnötige vollständige Metadata-Neuverarbeitung
        ↓
Archive listings / Image-Manifeste prüfen
        ↓
Soll-/Ist-Zustand des Image-Caches vergleichen
        ↓
fehlende/geänderte Bilder selektiv reparieren
```

Dieser Modus soll insbesondere von der zuvor beschriebenen inkrementellen Image-Reconciliation profitieren.

Beispiel:

```text
Model A:
20 desired
12 cached
=> 8 erzeugen

Model B:
18 desired
18 cached
=> nichts tun

Model C:
15 desired
15 cached
1 Cache-Datei fehlt
=> 1 regenerieren
```

Dieser Scan wäre deutlich geeigneter als ein vollständiger Library-Scan, wenn ausschließlich Archive-Images betroffen sind.

Wenn diese Funktion sauber implementierbar ist, halte ich sie für einen gewünschten Bestandteil.

---

## 16. Einzelnes Modell gezielt neu scannen

In der Admin-Detailansicht eines Modells soll eine Aktion hinzugefügt werden, beispielsweise:

```text
Rescan this model
```

oder:

```text
Rescan model
```

Diese Aktion soll ausschließlich dieses konkrete Modell neu prüfen.

Sie darf keinen globalen Library-Scan starten.

### 16.1 Standardverhalten

Beim normalen:

```text
Rescan model
```

soll folgendes passieren:

```text
Source-Pfad des Modells prüfen
        ↓
Metadaten neu parsen
        ↓
Archive neu listen
        ↓
Image-Sollzustand bestimmen
        ↓
Cache reconciliieren
        ↓
nur notwendige Bilder reparieren
        ↓
Model-Datensatz aktualisieren
```

Dabei weiterhin vorhandene Cache-Bilder wiederverwenden, wenn sie unverändert sind.

### 16.2 Force-Rebuild für ein Modell

Zusätzlich wäre für Administratoren eine explizite Aktion sinnvoll:

```text
Rebuild model images
```

Diese Aktion darf für genau dieses Modell bewusst:

```text
Archive-Image-Manifest neu aufbauen
Source-Bilder erneut extrahieren
Galerie-Derivate neu erzeugen
veraltete Meshive-Cache-Dateien entfernen
```

Dieser Modus ist für Fälle gedacht, in denen:

* Cache beschädigt ist
* Manifest inkonsistent ist
* Bildverarbeitung geändert wurde
* ein Administrator bewusst eine komplette Neuerzeugung möchte

Wichtig:

Das ist ein expliziter Force-Rebuild.

Der normale "Rescan model"-Button soll weiterhin möglichst inkrementell arbeiten.

### 16.3 Bestätigung

Ein normaler inkrementeller Model-Rescan benötigt keine dramatische Warnung.

Bei:

```text
Rebuild model images
```

sollte das UI dagegen klar darauf hinweisen, dass alle gecachten Archive-Images dieses Modells neu erzeugt werden.

Library Sources bleiben selbstverständlich read-only.

---

## 17. Optional: Mehrere Modelle gezielt neu scannen

Falls es ohne große UI-Komplexität möglich ist, soll geprüft werden, ob in der Admin-Modellliste eine Mehrfachauswahl sinnvoll ergänzt werden kann.

Beispielsweise:

```text
☑ Model A
☑ Model B
☑ Model C

Actions:
Rescan selected models
Reconcile images
```

Dies wäre hilfreich, wenn beispielsweise 5–20 bekannte problematische Modelle repariert werden sollen.

Es soll dabei KEIN globaler Scan erforderlich sein.

Dieser Punkt ist optional und soll nicht zu einer großen Neuarchitektur der Catalogue-UI führen.

---

## 18. Empfohlene Scan-Modi im UI

Versuche die Anzahl der Optionen übersichtlich zu halten.

Eine mögliche Struktur wäre:

### Incremental scan

```text
Process new models only.
Known models are skipped whenever possible.
Images are generated for new models.
```

Soll der schnelle Standardfall sein.

### Full scan

```text
Check all models and reconcile metadata and archive images.
Existing valid image cache entries are reused.
```

Für vollständige Konsistenzprüfungen.

### Full scan — missing images only

```text
Check all models, but extract archive images only for models that currently have no images.
```

Für eine schnelle Möglichkeit, bildlose Modelle aufzufüllen.

### Reconcile images

```text
Check archive image state for existing models and repair only missing or changed cached images.
```

Für gezielte Media-/Cache-Reparatur.

Bitte bessere UI-Bezeichnungen verwenden, falls die bestehende Meshive-Terminologie andere Namen nahelegt.

Wichtig ist die klare Semantik und nicht der exakte Wortlaut.

---

## 19. Scan-Matrix

Das gewünschte Verhalten lässt sich ungefähr so zusammenfassen:

| Operation                         | Incremental            | Full         | Full missing-images  | Image reconciliation    |
| --------------------------------- | ---------------------- | ------------ | -------------------- | ----------------------- |
| Library enumerieren               | ja                     | ja           | ja                   | soweit nötig            |
| neue Modelle erkennen             | ja                     | ja           | ja                   | optional                |
| bekannte Modelle neu parsen       | nein, wenn unverändert | ja           | ja                   | nein, soweit vermeidbar |
| Metadaten aktualisieren           | neue Modelle           | alle         | alle                 | nur falls nötig         |
| vorhandene Galerie prüfen         | nein                   | ja           | nur `0 images`       | ja                      |
| Cache reconcile                   | neue Modelle           | alle Modelle | nur bildlose Modelle | alle relevanten Modelle |
| vorhandene Bilder wiederverwenden | ja                     | ja           | ja                   | ja                      |
| unnötige Re-Extraktion vermeiden  | ja                     | ja           | ja                   | ja                      |

Passe diese Matrix an die tatsächliche bestehende Architektur an, wenn einzelne Operationen technisch anders aufgeteilt sind.

---

## 20. Fast Paths explizit implementieren

Bitte achte darauf, dass die Modi nicht nur unterschiedliche UI-Bezeichnungen für denselben teuren Scan darstellen.

Es sollen echte Fast Paths vorhanden sein.

Beispiel Incremental Scan:

```text
known model
+
source identity unchanged

=> skip expensive model processing
```

Beispiel Image Reconciliation:

```text
model metadata already known
+
archive fingerprint unchanged
+
selection policy unchanged
+
manifest complete
+
cache files present

=> skip immediately
```

Beispiel Full Scan:

```text
metadata geprüft
+
archive unchanged
+
cache consistent

=> keine Image-Extraktion
```

Instrumentiere bzw. teste diese Fast Paths so, dass nachweisbar ist, dass unnötige Arbeit tatsächlich nicht ausgeführt wird.

---

## 21. Scan-Fortschritt und Statistik

Die Scan-Übersicht sollte erkennen lassen, welcher Modus läuft.

Beispiel:

```text
Scan mode: Incremental

Models discovered: 4012
Known models skipped: 4000
New models processed: 12

Archive images:
86 generated
0 reconciled for skipped models
```

Full Scan beispielsweise:

```text
Scan mode: Full

Models checked: 4012
Models changed: 7
Models unchanged: 4005

Archive images:
3978 models reused fast path
21 images generated
3 images failed
```

Image-Reconciliation:

```text
Scan mode: Image reconciliation

Models checked: 4012
Models already consistent: 3995
Models repaired: 17

Images reused: 48132
Images generated: 84
Images removed as stale: 6
Images failed: 2
```

Die Statistiken müssen nicht genau so aussehen, sollen aber deutlich machen, ob die jeweiligen Optimierungen tatsächlich funktionieren.

---

## 22. Tests für unterschiedliche Scan-Modi

Ergänze die Tests um mindestens:

29. Incremental Scan mit 100 bekannten und 2 neuen Modellen → nur 2 vollständig verarbeiten

30. Incremental Scan erzeugt Archive-Images für neue Modelle

31. Incremental Scan verarbeitet vorhandene unveränderte Modelle nicht erneut

32. Full Scan prüft bekannte Modelle erneut

33. Full Scan verwendet trotzdem vorhandene unveränderte Image-Cache-Einträge

34. Full Missing-Images Scan erzeugt Images für ein Modell mit 0 Bildern

35. Full Missing-Images Scan lässt ein Modell mit bereits vorhandenen Bildern unangetastet

36. Image-Reconciliation aktualisiert ein Modell mit 12/20 gecachten Bildern auf 20, ohne die vorhandenen 12 neu zu generieren

37. Image-Reconciliation mit vollständig konsistentem Cache verursacht keine Extraktion

38. `Rescan model` verarbeitet ausschließlich das ausgewählte Modell

39. `Rescan model` verwendet unveränderte gecachte Bilder wieder

40. `Rebuild model images` regeneriert bewusst alle Archive-Images dieses einen Modells

41. Model-Rescan startet keinen globalen Library-Scan

42. Änderung an einem einzelnen Modell beeinträchtigt keine anderen Modelle

43. Scan-Modus wird korrekt in Status/Progress gespeichert bzw. angezeigt

44. Abbruch eines gezielten Model-Rescans hinterlässt keinen inkonsistenten Cache

---

## 23. Scan-API und interne Architektur

Bitte implementiere die unterschiedlichen Modi nicht als zahlreiche kopierte Scanner.

Bevorzuge eine gemeinsame Scan-Pipeline mit expliziter Policy bzw. Scan-Mode-Konfiguration.

Konzeptionell beispielsweise:

```text
ScanMode.INCREMENTAL
ScanMode.FULL
ScanMode.FULL_MISSING_IMAGES
ScanMode.IMAGE_RECONCILIATION
```

und für ein einzelnes Modell gegebenenfalls:

```text
scan_model(...)
```

mit entsprechenden Optionen.

Die konkreten Namen sollen sich an der bestehenden Meshive-Codebasis orientieren.

Ziel:

* gemeinsame Discovery
* gemeinsames Parsing
* gemeinsame Image-Reconciliation
* gemeinsame Sicherheitsmechanismen
* unterschiedliche Policies/Fast Paths

Keine duplizierte Scan-Logik.

---

## 24. Wichtigste Performance-Anforderung

Ein globaler Scan darf nicht mehr notwendig sein, nur weil ein Administrator die Bilder eines einzelnen bekannten Modells reparieren möchte.

Folgende Operation soll möglich sein:

```text
Admin öffnet Model A
        ↓
Rescan model
        ↓
nur Model A wird geprüft
        ↓
12 von 20 Bildern bereits gültig
        ↓
12 werden wiederverwendet
        ↓
8 werden extrahiert/generiert
        ↓
fertig
```

Alle anderen tausenden Modelle der Library dürfen dadurch nicht erneut verarbeitet werden.

Genau dieser Anwendungsfall soll durch Tests abgesichert werden.

---

## 25. Abschlussbewertung

Bitte bewerte nach Analyse der bestehenden Architektur zusätzlich, ob die vier globalen Scan-Modi wirklich sinnvoll getrennt werden sollten oder ob sich einzelne Modi technisch sauber zusammenfassen lassen.

Prioritäten sind:

1. klare Semantik für den Administrator
2. minimale unnötige Arbeit
3. keine stillen Bildverluste
4. inkrementelle Reparatur
5. Wiederverwendung vorhandener Cache-Daten
6. gezielter Scan einzelner Modelle
7. wartbarer Code ohne duplizierte Scanner

Wenn eine geringfügig andere Aufteilung technisch klarer ist, darfst du sie vorschlagen und begründen, bevor du sie implementierst.
