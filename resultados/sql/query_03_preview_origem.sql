SELECT lsoa_code, borough, major_category, minor_category, value, year, month
FROM `bigquery-public-data.london_crime.crime_by_lsoa`
ORDER BY year, month, borough, lsoa_code, major_category, minor_category
LIMIT 10
