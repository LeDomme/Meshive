Wir entwickeln Meshive, eine selbst gehostete Webanwendung zur Verwaltung
einer großen Sammlung archivierter 3D-Modelle.

Ausgangslage:
- mindestens 4.000 Modelle
- insgesamt etwa 3,42 TB und steigend
- bestehende Struktur:
  Creator / Collection oder Franchise / ModelName
- in jedem Modellordner befinden sich normalerweise:
  - genau ein stark komprimiertes Archiv als 7z, ZIP oder RAR
  - mindestens eine Bilddatei
- die Archive dürfen nicht dauerhaft entpackt werden

Kernfunktionen:
- Galerie- beziehungsweise Ordneransicht mit Vorschaubildern
- Suche nach Modellnamen, Creator, Franchise oder Collection
- Detailseite für jedes Modell
- Inhalt eines Archivs anzeigen, ohne es vollständig zu entpacken
- vollständiges Archiv herunterladen
- lokale Benutzerverwaltung ohne öffentliche Registrierung
- Zugriff auf Modelle und Downloads nur nach Anmeldung
- Docker-Deployment mit Unterstützung für Traefik
- vorhandene Bibliothek read-only einbinden
- keine Veränderung der vorhandenen Dateien und Ordner
- mehrere dynamisch konfigurierbare Bibliotheksquellen
- konfigurierbare Pfad- und Namensregeln je Quelle
- manuelle und rekursive Custom Tags

Bestätigter Stack:
- FastAPI
- SQLite mit FTS5
- Vue 3 mit TypeScript
- ein Meshive-Laufzeitcontainer hinter Traefik
- Englisch als initiale Oberflächensprache

Die Architektur, das Datenmodell, die Repository-Struktur, der MVP-Umfang und
die technischen Entscheidungen wurden abgestimmt und liegen im Ordner `docs/`.
