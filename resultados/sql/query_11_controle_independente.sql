SELECT year AS ano, SUM(value) AS crimes, COUNT(*) AS registros_origem,
       COUNT(DISTINCT month) AS meses_disponiveis
FROM `bigquery-public-data.london_crime.crime_by_lsoa` GROUP BY ano ORDER BY ano
