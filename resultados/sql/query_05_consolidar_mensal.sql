CREATE TABLE IF NOT EXISTS `london-crime-ebac-20261002.london_crime_analytics.crimes_mensais_bairro_categoria`
CLUSTER BY ano, bairro, categoria_original
OPTIONS(description='Grão único: mês, borough e major_category; SUM(value) como crimes.')
AS SELECT data_mes, year AS ano, month AS mes, borough AS bairro,
          major_category AS categoria_original, SUM(value) AS crimes,
          COUNT(*) AS registros_origem
FROM `london-crime-ebac-20261002.london_crime_analytics.crimes_london`
GROUP BY data_mes, ano, mes, bairro, categoria_original
