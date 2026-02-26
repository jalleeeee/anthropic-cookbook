# OpenConstructionEstimate

**Construction Work Items, Components & Resources**

---

**Verfügbare Formate**

| Format | Description |
|--------|-------------|
| Excel (.xlsx) | Universelles Format für Datenanalyse |
| Parquet (.parquet) | Spaltenformat für Big Data und ML |
| CSV (.csv) | Universelles Textformat |

---

## Über die Datenbank

Die moderne Bauindustrie in Eurasien und im asiatisch-pazifischen Raum stützt sich auf ein einheitliches Ökosystem technischer Normung, das als gemeinsame Ingenieursprache für mehr als 10 dynamisch wachsende Volkswirtschaften dient.

Die DDC CWICR-Datenbank (Construction Work Items, Components & Resources) ist ein Versuch zur Harmonisierung von Standards und schafft einen nahtlosen regulatorischen Raum für das Kapitalprojektmanagement in mehreren Sprachen. Die Datenbank deckt das gesamte Spektrum der Bauarbeiten ab: von Erdarbeiten und Betonarbeiten bis hin zu spezialisierten Montagearbeiten.

## Datenquellen

DDC CWICR basiert auf offiziellen Baukostenstandards aus eurasischen Ländern, die öffentlich zugänglich sind. Die Datenbank wurde in enger Zusammenarbeit mit Kalkulatoren und Bauspezialisten aus verschiedenen Ländern entwickelt, was es ermöglichte, praktische Aspekte der Datenarbeit zu berücksichtigen. Die Daten wurden in eine einheitliche Struktur systematisiert, methodisch harmonisiert und in 9 Sprachversionen sowie 9 regionalen Preisversionen für den internationalen Einsatz bereitgestellt.

## Historische Entwicklung

Die Methodik der ressourcenbasierten Normung von Bauarbeiten wird seit den 1920er Jahren kontinuierlich weiterentwickelt und verbessert — von den ersten Produktionsnormen bis zu modernen digitalen Nachschlagewerken. Im Laufe eines Jahrhunderts hat sich das System von manuellen Berechnungen zu maschinenlesbaren Datenbanken entwickelt, wobei das grundlegende Prinzip erhalten blieb: die genaue Erfassung physischer Ressourcen pro Einheit der Bauleistung.

Die moderne Version integriert historische Daten mit aktuellen Marktpreisen. Auf lokalen Märkten sind ähnliche Systeme unter nationalen Bezeichnungen bekannt: ENIR, GESN, FER, NRR, ESN, AzDTN, SchNQK, MKS TschT, SNT, BNbD, Dinh Muc, Ding'e.

## Resource-Based Costing Methodik

Der Schlüsselwert des Resource-Based Costing liegt in der Trennung der unveränderlichen Produktionstechnologie von der volatilen finanziellen Komponente: Es basiert auf den physikalischen "ersten Prinzipien" des Bauens — Standardnormen für Arbeitskosten, Maschinenzeit und Materialverbrauch. Diese Normen bleiben praktisch unverändert, unabhängig davon, in welchem Land gebaut wird.

Dies ermöglicht transparente Preisgestaltung, eliminiert versteckte Aufschläge und erlaubt ein Deep-Dive Audit von Investitionen. Dadurch dient DDC CWICR nicht nur als Nachschlagewerk, sondern als fundamentales Risikomanagement-Tool, das im letzten Jahrhundert zum De-facto-Industriestandard für die Makroregion geworden ist.

## Datenbankstatistik

- **55.719** Arbeiten und Einheitspreise
- **27.672** einzigartige Ressourcen
- **10+** Anwendungsländer


## Datenstruktur

Die Datenbank enthält 85 Spalten, die in logische Gruppen organisiert sind:

### Klassifikationshierarchie
*10 Spalten*

category_type, collection_code/name, department_code/name, section_name, subsection_code/name

### Einheitspreis (Work Item)
*11 Spalten*

rate_code, rate_original_name, rate_unit, row_type, Flags is_material/is_labor/is_machine/is_abstract

### Ressourcen
*7 Spalten*

resource_code, resource_name, resource_unit, resource_quantity, resource_price_per_unit, resource_cost

### Arbeit
*11 Spalten*

count_workers/engineers/machinists, labor_hours nach Kategorie, cost_of_working_hours

### Maschinen & Geräte
*12 Spalten*

machine_class, personnel_machinist_grade, electricity_consumption_kwh, electricity_cost

### Preisvarianten
*16 Spalten*

price_est_min/max/median/mean, position_count, tech_group

### Masse
*3 Spalten*

mass_name, mass_value, mass_unit

## Anwendungsfälle

- **Kostenbenchmarking** — Kostenvergleich zwischen Regionen
- **Preisindexierung** — Dynamik verfolgen
- **Lokalisierung** — Anpassung an lokale Bedingungen
- **ETL/BI-Pipelines** — Daten extrahieren und transformieren
- **KI/ML-Training** — Modelle trainieren
- **CAD (BIM) 5D-Integration** — Automatische Preiszuweisung
- **Ausschreibungsschätzung** — Schnelle Schätzungen
- **CO2-Berechnung** — CO2-Fußabdruck berechnen
- **Deep-Dive Audit** — Technisches Audit


## Geografische Abdeckung

Die Methodik und Datenbank werden in verschiedenen Anpassungen in folgenden Regionen angewendet:

- **Zentraleurasien (GUS)**: Belarus, Kasachstan, Kirgisistan, Russland, Tadschikistan, Turkmenistan, Usbekistan
- **Kaukasus**: Armenien, Aserbaidschan, Georgien
- **Osteuropa**: Moldawien, Ukraine
- **Ostasien (Quota-System)**: China (Ding'e), Mongolei (BNbD), Vietnam (Dinh Muc)
- **Internationale Projekte**: Bangladesch, Ägypten, Türkei
- **Historische Anwendung (1950-1990)**: Bulgarien, Tschechoslowakei, Ungarn


## Zusammenarbeit und Entwicklung

Wir sind offen für den Dialog mit der Fachwelt. Ihre Erfahrungen bei der Nutzung der Datenbank in realen Projekten helfen, die Plattform zu verbessern und ihre Möglichkeiten zu erweitern. Teilen Sie Anwendungsfälle, schlagen Sie Verbesserungen vor und beteiligen Sie sich an Diskussionen.

- **GitHub**: [github.com/datadrivenconstruction](https://github.com/datadrivenconstruction)
- **Telegram**: [t.me/datadrivenconstruction](https://t.me/datadrivenconstruction)
- **LinkedIn**: [linkedin.com/company/datadrivenconstruction](https://linkedin.com/company/datadrivenconstruction)


## Beratung und Schulung

Wir arbeiten mit führenden Bau-, Ingenieur-, Beratungsunternehmen und Technologiefirmen weltweit zusammen, um ihnen bei der Implementierung von Open-Data-Prinzipien, der Automatisierung der CAD/BIM-Verarbeitung und dem Aufbau robuster ETL-Pipelines zu helfen.

Wenn Sie diese Lösung mit Ihren eigenen Daten testen möchten oder daran interessiert sind, den Workflow an reale Projektaufgaben anzupassen, kontaktieren Sie uns gerne. Unser Team bietet praktische Workshops, strategische Beratung und entwickelt Prototypen, die auf reale Projektprozesse zugeschnitten sind.

Wir unterstützen aktiv Organisationen, die praktische Lösungen für die digitale Transformation und Interoperabilität suchen, wobei wir uns auf Datenqualität und Klassifizierungsherausforderungen konzentrieren und die Einführung offener und automatisierter Workflows vorantreiben.

Kontaktieren Sie uns für eine kostenlose Beratung, bei der wir Ihre Herausforderungen besprechen und demonstrieren, wie n8n-Automatisierung Ihre Abläufe transformieren kann. Erreichen Sie uns per E-Mail unter info@datadrivenconstruction.io oder besuchen Sie unsere Website datadrivenconstruction.io, um mehr über unsere Dienstleistungen zu erfahren.



## Projekt unterstützen

Wenn Sie unsere Tools und Datenbanken nützlich finden und mehr Anwendungen für die Bauindustrie sehen möchten, geben Sie bitte unseren Repositories auf GitHub einen Stern. Dies hilft dem Projekt zu wachsen und ermöglicht es Ihnen, Benachrichtigungen über neue Releases zu erhalten.

Basierend auf DDC CWICR können Sie automatisierte Pipelines und Workflows für die Integration mit CAD (BIM), Ausschreibungssystemen und BI-Plattformen erstellen. Neue Workflows, Tools und fertige Lösungen werden regelmäßig auf GitHub und der Projektwebsite veröffentlicht. Abonnieren Sie Updates, um als Erster Zugang zu neuen Releases zu erhalten.

- ⭐ **CAD (BIM) Data Agents & Workflows + AI**: [github.com/datadrivenconstruction/cad2data-Revit-IFC-DWG-DGN-pipeline-with-conversion-validation-qto](https://github.com/datadrivenconstruction/cad2data-Revit-IFC-DWG-DGN-pipeline-with-conversion-validation-qto)
- ⭐ **OpenConstructionEstimate DDC CWICR**: [github.com/datadrivenconstruction/OpenConstructionEstimate-DDC-CWICR](https://github.com/datadrivenconstruction/OpenConstructionEstimate-DDC-CWICR)


## Sprachversionen

Die Dokumentation ist in 9 Sprachen verfügbar:

- **Arabisch / العربية** (Dubai) — Naher Osten
- **Chinesisch / 中文** (Shanghai) — Ostasien
- **Deutsch** (Berlin) — Mitteleuropa
- **Englisch / English** (Toronto) — Nordamerika
- **Spanisch / Español** (Barcelona) — Iberien
- **Französisch / Français** (Paris) — Westeuropa
- **Hindi / हिन्दी** (Mumbai) — Südasien
- **Portugiesisch / Português** (São Paulo) — Lateinamerika
- **Russisch / Русский** (St. Petersburg) — GUS


## Ressourcen

- **Anwendungsbeispiel:** https://openconstructionestimate.com
- **Website:** https://datadrivenconstruction.io


---

### Erschließen Sie die Macht der Daten im Bauwesen 🚀

Wechseln Sie zum Full-Cycle-Datenmanagement, wo nur einheitliche strukturierte Daten & Prozesse bleiben und wo 🔓 Ihre Daten Ihnen gehören

---

*[Artem Boiko, 2025](https://www.linkedin.com/in/boikoartem/)*
