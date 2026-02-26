# OpenConstructionEstimate

**Construction Work Items, Components & Resources**

---

**Formatos disponibles**

| Format | Description |
|--------|-------------|
| Excel (.xlsx) | Formato universal para análisis de datos |
| Parquet (.parquet) | Formato columnar para Big Data y ML |
| CSV (.csv) | Formato de texto universal |

---

## Acerca de la base de datos

La industria moderna de la construcción en Eurasia y la región de Asia-Pacífico se basa en un ecosistema unificado de estandarización técnica que sirve como lenguaje de ingeniería común para más de 10 economías en desarrollo dinámico.

La base de datos DDC CWICR (Construction Work Items, Components & Resources) es un intento de armonizar estándares, creando un espacio regulatorio sin fisuras para la gestión de proyectos de capital en múltiples idiomas. La base de datos cubre todo el espectro de trabajos de construcción: desde movimientos de tierra y hormigón hasta operaciones de instalación especializadas.

## Fuentes de datos

DDC CWICR se basa en estándares oficiales de costos de construcción de países euroasiáticos que están disponibles públicamente. La base de datos fue desarrollada en estrecha colaboración con estimadores y especialistas en construcción de diferentes países, lo que nos permitió tener en cuenta los aspectos prácticos del trabajo con datos. Los datos se han sistematizado en una estructura unificada, armonizados metodológicamente y presentados en 9 versiones de idioma y 9 versiones de precios regionales para uso internacional.

## Desarrollo histórico

La metodología de estandarización basada en recursos de los trabajos de construcción se ha desarrollado y mejorado continuamente desde la década de 1920, desde las primeras normas de producción hasta los libros de referencia digitales modernos. A lo largo de un siglo, el sistema ha evolucionado desde cálculos manuales hasta bases de datos legibles por máquina, preservando el principio fundamental: el registro preciso de los recursos físicos por unidad de producción de construcción.

La versión moderna integra datos históricos con precios de mercado actuales. En los mercados locales, sistemas similares se adaptan y se conocen bajo códigos nacionales: ENIR, GESN, FER, NRR, ESN, AzDTN, ShNQK, MKS ChT, SNT, BNbD, Dinh Muc, Ding'e.

## Metodología Resource-Based Costing

El valor clave del Resource-Based Costing es la separación de la tecnología de producción inmutable del componente financiero volátil: se basa en los "primeros principios" físicos de la construcción: normas estándar para costos de mano de obra, tiempo de máquina y consumo de materiales. Estas normas permanecen prácticamente sin cambios independientemente del país donde se realice la construcción.

Esto permite una fijación de precios transparente, elimina los márgenes ocultos y permite una auditoría profunda (Deep-Dive Audit) de las inversiones. Como resultado, DDC CWICR sirve no solo como un libro de referencia, sino como una herramienta fundamental de gestión de riesgos que se ha convertido en el estándar de facto de la industria para la macrorregión durante el último siglo.

## Estadísticas de la base de datos

- **55.719** elementos de trabajo y tarifas
- **27.672** recursos únicos
- **10+** países de aplicación


## Estructura de datos

La base de datos contiene 85 columnas organizadas en grupos lógicos:

### Jerarquía de clasificación
*10 columnas*

category_type, collection_code/name, department_code/name, section_name, subsection_code/name

### Tarifa (Work Item)
*11 columnas*

rate_code, rate_original_name, rate_unit, row_type, flags is_material/is_labor/is_machine/is_abstract

### Recursos
*7 columnas*

resource_code, resource_name, resource_unit, resource_quantity, resource_price_per_unit, resource_cost

### Mano de obra
*11 columnas*

count_workers/engineers/machinists, labor_hours por categoría, cost_of_working_hours

### Maquinaria y equipos
*12 columnas*

machine_class, personnel_machinist_grade, electricity_consumption_kwh, electricity_cost

### Variantes de precio
*16 columnas*

price_est_min/max/median/mean, position_count, tech_group

### Masa
*3 columnas*

mass_name, mass_value, mass_unit

## Casos de uso

- **Benchmarking de costos** — Comparar costos entre regiones
- **Indexación de precios** — Seguir dinámicas
- **Localización** — Adaptar a condiciones locales
- **Pipelines ETL/BI** — Extraer y transformar datos
- **Entrenamiento IA/ML** — Entrenar modelos
- **Integración CAD (BIM) 5D** — Asignación automática de tarifas
- **Estimación de licitaciones** — Estimaciones rápidas
- **Cálculo de CO2** — Calcular huella de carbono
- **Auditoría profunda** — Auditoría técnica


## Cobertura geográfica

La metodología y la base de datos se aplican en varias adaptaciones en las siguientes regiones:

- **Eurasia Central (CEI)**: Bielorrusia, Kazajistán, Kirguistán, Rusia, Tayikistán, Turkmenistán, Uzbekistán
- **Cáucaso**: Armenia, Azerbaiyán, Georgia
- **Europa del Este**: Moldavia, Ucrania
- **Asia Oriental (Sistema de cuotas)**: China (Ding'e), Mongolia (BNbD), Vietnam (Dinh Muc)
- **Proyectos internacionales**: Bangladesh, Egipto, Turquía
- **Aplicación histórica (1950-1990)**: Bulgaria, Checoslovaquia, Hungría


## Colaboración y desarrollo

Estamos abiertos al diálogo con la comunidad profesional. Su experiencia en el uso de la base de datos en proyectos reales ayuda a mejorar la plataforma y expandir sus capacidades. Comparta casos de uso, sugiera mejoras y participe en discusiones.

- **GitHub**: [github.com/datadrivenconstruction](https://github.com/datadrivenconstruction)
- **Telegram**: [t.me/datadrivenconstruction](https://t.me/datadrivenconstruction)
- **LinkedIn**: [linkedin.com/company/datadrivenconstruction](https://linkedin.com/company/datadrivenconstruction)


## Consultoría y formación

Trabajamos con las principales agencias de construcción, ingeniería, consultoría y empresas tecnológicas de todo el mundo para ayudarles a implementar principios de datos abiertos, automatizar el procesamiento CAD/BIM y construir pipelines ETL robustos.

Si desea probar esta solución con sus propios datos, o está interesado en adaptar el flujo de trabajo a tareas de proyectos reales, no dude en contactarnos. Nuestro equipo ofrece talleres prácticos, proporciona consultoría estratégica y desarrolla prototipos adaptados a procesos de proyectos reales.

Apoyamos activamente a las organizaciones que buscan soluciones prácticas para la transformación digital y la interoperabilidad, centrándonos en los desafíos de calidad de datos y clasificación, e impulsando la adopción de flujos de trabajo abiertos y automatizados.

Contáctenos para una consulta gratuita donde discutiremos sus desafíos y demostraremos cómo la automatización n8n puede transformar sus operaciones. Comuníquese por correo electrónico a info@datadrivenconstruction.io o visite nuestro sitio web datadrivenconstruction.io para obtener más información sobre nuestros servicios.



## Apoya el proyecto

Si encuentra útiles nuestras herramientas y bases de datos y le gustaría ver más aplicaciones para la industria de la construcción, por favor dé una estrella a nuestros repositorios en GitHub. Esto ayuda al proyecto a crecer y le permite recibir notificaciones sobre nuevas versiones.

Basándose en DDC CWICR, puede construir pipelines y flujos de trabajo automatizados para la integración con CAD (BIM), sistemas de licitación y plataformas BI. Nuevos flujos de trabajo, herramientas y soluciones listas para usar se publican regularmente en GitHub y el sitio web del proyecto. Suscríbase a las actualizaciones para ser el primero en acceder a nuevas versiones.

- ⭐ **CAD (BIM) Data Agents & Workflows + AI**: [github.com/datadrivenconstruction/cad2data-Revit-IFC-DWG-DGN-pipeline-with-conversion-validation-qto](https://github.com/datadrivenconstruction/cad2data-Revit-IFC-DWG-DGN-pipeline-with-conversion-validation-qto)
- ⭐ **OpenConstructionEstimate DDC CWICR**: [github.com/datadrivenconstruction/OpenConstructionEstimate-DDC-CWICR](https://github.com/datadrivenconstruction/OpenConstructionEstimate-DDC-CWICR)


## Versiones de idiomas

La documentación está disponible en 9 idiomas:

- **Árabe / العربية** (Dubái) — Medio Oriente
- **Chino / 中文** (Shanghái) — Asia Oriental
- **Alemán / Deutsch** (Berlín) — Europa Central
- **Inglés / English** (Toronto) — Norteamérica
- **Español** (Barcelona) — Iberia
- **Francés / Français** (París) — Europa Occidental
- **Hindi / हिन्दी** (Mumbai) — Asia del Sur
- **Portugués / Português** (São Paulo) — Latinoamérica
- **Ruso / Русский** (San Petersburgo) — CEI


## Recursos

- **Ejemplo de uso:** https://openconstructionestimate.com
- **Website:** https://datadrivenconstruction.io


---

### Libera el poder de los datos en la construcción 🚀

Pasa a la gestión de datos de ciclo completo donde solo permanecen datos estructurados unificados y procesos y donde 🔓 tus datos son tuyos

---

*[Artem Boiko, 2025](https://www.linkedin.com/in/boikoartem/)*
