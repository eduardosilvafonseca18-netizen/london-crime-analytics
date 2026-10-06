SELECT COALESCE(SUM(n - 1), 0) AS registros_duplicados,
       COUNT(*) AS grupos_duplicados
FROM (
  SELECT lsoa_code, borough, major_category, minor_category, year, month,
         COUNT(*) AS n
  FROM `bigquery-public-data.london_crime.crime_by_lsoa`
  GROUP BY lsoa_code, borough, major_category, minor_category, year, month
  HAVING COUNT(*) > 1
)
