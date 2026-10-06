SELECT COUNT(*) AS registros, SUM(value) AS crimes,
       COUNTIF(lsoa_code IS NULL OR TRIM(lsoa_code) = '') AS lsoa_invalido,
       COUNTIF(borough IS NULL OR TRIM(borough) = '') AS bairro_invalido,
       COUNTIF(major_category IS NULL OR TRIM(major_category) = '') AS categoria_invalida,
       COUNTIF(minor_category IS NULL OR TRIM(minor_category) = '') AS subcategoria_invalida,
       COUNTIF(value IS NULL OR value < 0) AS valor_invalido,
       COUNTIF(year IS NULL OR year NOT BETWEEN 1900 AND 2099
            OR month IS NULL OR month NOT BETWEEN 1 AND 12) AS periodo_invalido,
       COUNTIF(value = 0) AS registros_zero,
       MIN(year) AS primeiro_ano, MAX(year) AS ultimo_ano,
       COUNT(DISTINCT borough) AS bairros,
       COUNT(DISTINCT lsoa_code) AS lsoas,
       COUNT(DISTINCT major_category) AS categorias
FROM `bigquery-public-data.london_crime.crime_by_lsoa`
