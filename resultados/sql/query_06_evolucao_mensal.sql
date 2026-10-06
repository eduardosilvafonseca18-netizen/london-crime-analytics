SELECT data_mes, ano, mes, bairro, categoria_original, crimes, registros_origem
FROM `london-crime-ebac-20261002.london_crime_analytics.crimes_mensais_bairro_categoria`
ORDER BY data_mes, bairro, categoria_original
