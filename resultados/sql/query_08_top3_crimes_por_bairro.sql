WITH anuais AS (
  SELECT ano, bairro, categoria_original, SUM(crimes) AS crimes
  FROM `london-crime-ebac-20261002.london_crime_analytics.crimes_mensais_bairro_categoria` GROUP BY ano, bairro, categoria_original
)
SELECT *, ROW_NUMBER() OVER (PARTITION BY ano, bairro
              ORDER BY crimes DESC, categoria_original) AS posicao
FROM anuais
QUALIFY posicao <= 3
ORDER BY ano, bairro, posicao
