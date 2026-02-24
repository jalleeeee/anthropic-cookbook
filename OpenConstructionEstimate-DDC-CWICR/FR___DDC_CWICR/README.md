# OpenConstructionEstimate

**Construction Work Items, Components & Resources**

---

**Formats disponibles**

| Format | Description |
|--------|-------------|
| Excel (.xlsx) | Format universel pour l'analyse de données |
| Parquet (.parquet) | Format colonnaire pour le Big Data et ML |
| CSV (.csv) | Format texte universel |

---

## À propos de la base de données

L'industrie moderne de la construction en Eurasie et dans la région Asie-Pacifique repose sur un écosystème unifié de normalisation technique qui sert de langage d'ingénierie commun pour plus de 10 économies en développement dynamique.

La base de données DDC CWICR (Construction Work Items, Components & Resources) est une tentative d'harmonisation des normes, créant un espace réglementaire transparent pour la gestion des projets d'investissement dans plusieurs langues. La base de données couvre tout le spectre des travaux de construction : des terrassements et du béton aux opérations d'installation spécialisées.

## Sources des données

DDC CWICR est construit sur les normes officielles des coûts de construction des pays eurasiatiques qui sont accessibles au public. La base de données a été développée en étroite collaboration avec des estimateurs et des spécialistes de la construction de différents pays, ce qui nous a permis de prendre en compte les aspects pratiques du travail avec les données. Les données ont été systématisées en une structure unifiée, harmonisées méthodologiquement et présentées en 9 versions linguistiques et 9 versions de prix régionales pour une utilisation internationale.

## Développement historique

La méthodologie de normalisation basée sur les ressources des travaux de construction n'a cessé de se développer et de s'améliorer depuis les années 1920 — des premières normes de production aux ouvrages de référence numériques modernes. Au cours d'un siècle, le système a évolué des calculs manuels aux bases de données lisibles par machine tout en préservant le principe fondamental : l'enregistrement précis des ressources physiques par unité de production de construction.

La version moderne intègre les données historiques avec les prix actuels du marché. Sur les marchés locaux, des systèmes similaires sont adaptés et connus sous des codes nationaux : ENIR, GESN, FER, NRR, ESN, AzDTN, ShNQK, MKS ChT, SNT, BNbD, Dinh Muc, Ding'e.

## Méthodologie Resource-Based Costing

La valeur clé du Resource-Based Costing réside dans la séparation de la technologie de production immuable de la composante financière volatile : elle est basée sur les "premiers principes" physiques de la construction — normes standards pour les coûts de main-d'œuvre, le temps machine et la consommation de matériaux. Ces normes restent pratiquement inchangées quel que soit le pays où la construction est effectuée.

Cela permet une tarification transparente, élimine les majorations cachées et permet un audit approfondi (Deep-Dive Audit) des investissements. En conséquence, DDC CWICR sert non seulement d'ouvrage de référence, mais aussi d'outil fondamental de gestion des risques qui est devenu la norme industrielle de facto pour la macro-région au cours du siècle dernier.

## Statistiques de la base de données

- **55 719** éléments de travail et tarifs
- **27 672** ressources uniques
- **10+** pays d'application


## Structure des données

La base de données contient 85 colonnes organisées en groupes logiques :

### Hiérarchie de classification
*10 colonnes*

category_type, collection_code/name, department_code/name, section_name, subsection_code/name

### Tarif (Work Item)
*11 colonnes*

rate_code, rate_original_name, rate_unit, row_type, drapeaux is_material/is_labor/is_machine/is_abstract

### Ressources
*7 colonnes*

resource_code, resource_name, resource_unit, resource_quantity, resource_price_per_unit, resource_cost

### Main-d'œuvre
*11 colonnes*

count_workers/engineers/machinists, labor_hours par catégorie, cost_of_working_hours

### Machines & Équipements
*12 colonnes*

machine_class, personnel_machinist_grade, electricity_consumption_kwh, electricity_cost

### Variantes de prix
*16 colonnes*

price_est_min/max/median/mean, position_count, tech_group

### Masse
*3 colonnes*

mass_name, mass_value, mass_unit

## Cas d'utilisation

- **Benchmarking des coûts** — Comparer les coûts entre régions
- **Indexation des prix** — Suivre les dynamiques
- **Localisation** — Adapter aux conditions locales
- **Pipelines ETL/BI** — Extraire et transformer les données
- **Formation IA/ML** — Entraîner des modèles
- **Intégration CAD (BIM) 5D** — Attribution automatique des tarifs
- **Estimation d'appel d'offres** — Estimations rapides
- **Calcul CO2** — Calculer l'empreinte carbone
- **Audit approfondi** — Audit technique


## Couverture géographique

La méthodologie et la base de données sont appliquées dans diverses adaptations dans les régions suivantes :

- **Eurasie centrale (CEI)**: Biélorussie, Kazakhstan, Kirghizistan, Russie, Tadjikistan, Turkménistan, Ouzbékistan
- **Caucase**: Arménie, Azerbaïdjan, Géorgie
- **Europe de l'Est**: Moldavie, Ukraine
- **Asie de l'Est (Système de quotas)**: Chine (Ding'e), Mongolie (BNbD), Vietnam (Dinh Muc)
- **Projets internationaux**: Bangladesh, Égypte, Turquie
- **Application historique (1950-1990)**: Bulgarie, Tchécoslovaquie, Hongrie


## Collaboration et développement

Nous sommes ouverts au dialogue avec la communauté professionnelle. Votre expérience dans l'utilisation de la base de données dans des projets réels aide à améliorer la plateforme et à étendre ses capacités. Partagez des cas d'utilisation, proposez des améliorations et participez aux discussions.

- **GitHub**: [github.com/datadrivenconstruction](https://github.com/datadrivenconstruction)
- **Telegram**: [t.me/datadrivenconstruction](https://t.me/datadrivenconstruction)
- **LinkedIn**: [linkedin.com/company/datadrivenconstruction](https://linkedin.com/company/datadrivenconstruction)


## Conseil et formation

Nous travaillons avec des agences de construction, d'ingénierie, de conseil et des entreprises technologiques de premier plan dans le monde entier pour les aider à mettre en œuvre les principes des données ouvertes, à automatiser le traitement CAD/BIM et à construire des pipelines ETL robustes.

Si vous souhaitez tester cette solution avec vos propres données, ou si vous êtes intéressé par l'adaptation du workflow aux tâches de projets réels, n'hésitez pas à nous contacter. Notre équipe propose des ateliers pratiques, fournit des conseils stratégiques et développe des prototypes adaptés aux processus de projets réels.

Nous soutenons activement les organisations à la recherche de solutions pratiques pour la transformation numérique et l'interopérabilité, en nous concentrant sur les défis de qualité des données et de classification, et en favorisant l'adoption de workflows ouverts et automatisés.

Contactez-nous pour une consultation gratuite où nous discuterons de vos défis et démontrerons comment l'automatisation n8n peut transformer vos opérations. Contactez-nous par e-mail à info@datadrivenconstruction.io ou visitez notre site web datadrivenconstruction.io pour en savoir plus sur nos services.



## Soutenir le projet

Si vous trouvez nos outils et bases de données utiles et souhaitez voir plus d'applications pour l'industrie de la construction, veuillez mettre une étoile à nos dépôts sur GitHub. Cela aide le projet à se développer et vous permet de recevoir des notifications sur les nouvelles versions.

Basé sur DDC CWICR, vous pouvez construire des pipelines et des workflows automatisés pour l'intégration avec CAD (BIM), les systèmes d'appels d'offres et les plateformes BI. De nouveaux workflows, outils et solutions prêtes à l'emploi sont régulièrement publiés sur GitHub et le site web du projet. Abonnez-vous aux mises à jour pour être le premier à accéder aux nouvelles versions.

- ⭐ **CAD (BIM) Data Agents & Workflows + AI**: [github.com/datadrivenconstruction/cad2data-Revit-IFC-DWG-DGN-pipeline-with-conversion-validation-qto](https://github.com/datadrivenconstruction/cad2data-Revit-IFC-DWG-DGN-pipeline-with-conversion-validation-qto)
- ⭐ **OpenConstructionEstimate DDC CWICR**: [github.com/datadrivenconstruction/OpenConstructionEstimate-DDC-CWICR](https://github.com/datadrivenconstruction/OpenConstructionEstimate-DDC-CWICR)


## Versions linguistiques

La documentation est disponible en 9 langues :

- **Arabe / العربية** (Dubaï) — Moyen-Orient
- **Chinois / 中文** (Shanghai) — Asie de l'Est
- **Allemand / Deutsch** (Berlin) — Europe centrale
- **Anglais / English** (Toronto) — Amérique du Nord
- **Espagnol / Español** (Barcelone) — Ibérie
- **Français** (Paris) — Europe de l'Ouest
- **Hindi / हिन्दी** (Mumbai) — Asie du Sud
- **Portugais / Português** (São Paulo) — Amérique latine
- **Russe / Русский** (Saint-Pétersbourg) — CEI


## Ressources

- **Exemple d'utilisation:** https://openconstructionestimate.com
- **Website:** https://datadrivenconstruction.io


---

### Libérez la puissance des données dans la construction 🚀

Passez à la gestion des données en cycle complet où seules les données structurées unifiées et les processus restent et où 🔓 vos données vous appartiennent

---

*[Artem Boiko, 2025](https://www.linkedin.com/in/boikoartem/)*
