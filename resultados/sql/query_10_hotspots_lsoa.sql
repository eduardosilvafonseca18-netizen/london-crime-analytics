WITH areas AS (
  SELECT year AS ano, borough AS bairro, lsoa_code, SUM(value) AS crimes,
         SUM(IF(major_category = 'Violence Against the Person', value, 0)) AS crimes_violencia_pessoa
  FROM `london-crime-ebac-20261002.london_crime_analytics.crimes_london` GROUP BY ano, bairro, lsoa_code
), ranks AS (
  SELECT *, ROW_NUMBER() OVER (PARTITION BY ano, bairro ORDER BY crimes DESC, lsoa_code) AS posicao,
         COUNT(*) OVER (PARTITION BY ano, bairro) AS lsoas_bairro,
         SUM(crimes) OVER (PARTITION BY ano, bairro) AS total_bairro
  FROM areas
)
SELECT *, SAFE_DIVIDE(crimes, total_bairro) AS participacao_bairro
FROM ranks
WHERE posicao <= GREATEST(1, CAST(CEIL(0.1 * lsoas_bairro) AS INT64))
ORDER BY ano, bairro, posicao
