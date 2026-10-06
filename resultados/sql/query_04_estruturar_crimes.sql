CREATE TABLE IF NOT EXISTS `london-crime-ebac-20261002.london_crime_analytics.crimes_london`
CLUSTER BY year, borough, major_category, lsoa_code
OPTIONS(description='Cópia da base pública London Crime. Contagem mensal por LSOA e subcategoria. Zeros preservados.')
AS SELECT lsoa_code, borough, major_category, minor_category, value, year, month,
          DATE(year, month, 1) AS data_mes
FROM `bigquery-public-data.london_crime.crime_by_lsoa`
